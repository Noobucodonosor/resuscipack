"""Pipeline ibrida Lossless `PDF → Markdown` (`resuscipack-md v1`, ADR-0006).

Cascata a 4 stadi (`TemporaryDirectory` obbligatorio, sorgenti `STRICT READ-ONLY`):
- Stadio 0: Router deterministico di pagina (`classify_pdf_page`) + split verticale 2-up.
- Stadio 1: Estrazione di massa e ritaglio figure lossless (Baidu `PP-Structure` / `pdftotext` a colonne).
- Stadio 2: Quality Gate deterministico (`evaluate_page_quality_gate`) a €0.
- Stadio 3: Structured Vision LLM chirurgico (`transcribe_page_structured_vision`) solo dove il Gate segnala rischi.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .normalizer import clean_ocr_markdown
from .ocr_ingest import (
    DEFAULT_GCP_PROJECT,
    DEFAULT_VISION_MODEL,
    _get_gcloud_token,
    _repair_json_latex_escapes,
    _resolve_tool,
    _strip_json_fences,
    get_pdf_page_dimensions,
    is_landscape_2up,
)

RESUSCIPACK_MD_PAGE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": [
        "printed_page",
        "running_header",
        "section_title",
        "block_role",
        "body_markdown",
        "footnotes",
        "marginalia",
        "boxes",
        "figures",
        "tables_html",
        "continues_on_next_page",
    ],
    "properties": {
        "printed_page": {"type": "STRING"},
        "running_header": {"type": "STRING"},
        "section_title": {"type": "STRING"},
        "block_role": {"type": "STRING", "enum": ["body", "paratext", "index", "bibliography", "glossary"]},
        "body_markdown": {"type": "STRING"},
        "footnotes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["id", "text"],
                "properties": {
                    "id": {"type": "STRING"},
                    "text": {"type": "STRING"},
                },
            },
        },
        "marginalia": {"type": "ARRAY", "items": {"type": "STRING"}},
        "boxes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["title", "body"],
                "properties": {
                    "title": {"type": "STRING"},
                    "body": {"type": "STRING"},
                },
            },
        },
        "figures": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["label", "caption", "internal_labels"],
                "properties": {
                    "label": {"type": "STRING"},
                    "caption": {"type": "STRING"},
                    "internal_labels": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "tables_html": {"type": "ARRAY", "items": {"type": "STRING"}},
        "continues_on_next_page": {"type": "BOOLEAN"},
    },
}

_FOOTNOTE_DEF_RE = re.compile(r"(?m)^\[\^([A-Za-z0-9_.\-]+)\]:\s*(.+)$")
_FOOTNOTE_REF_RE = re.compile(r"\[\^([A-Za-z0-9_.\-]+)\](?!:)")
_GARBLED_CONTROL_RE = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]")
_GUTTER_GAP_RE = re.compile(r"\S\s{6,}\S")


def count_pdf_page_images(doc_path: Path, page_num: int) -> int:
    """Conta in modo read-only le immagini raster incorporate nella pagina tramite `pdfimages -list`."""
    try:
        pdfimages = _resolve_tool("pdfimages", "/opt/homebrew/bin/pdfimages")
    except FileNotFoundError:
        return 0
    proc = subprocess.run(
        [pdfimages, "-list", "-f", str(page_num), "-l", str(page_num), str(doc_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return 0
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    data_lines = [ln for ln in lines if re.match(r"^\d+\s+\d+\s+", ln)]
    return len(data_lines)


def classify_pdf_page(doc_path: Path, page_num: int) -> Dict[str, Any]:
    """Stadio 0 (€0): classifica una pagina PDF e decide se serve split 2-up e quale motore usare."""
    if not doc_path.exists():
        raise FileNotFoundError(f"PDF non trovato: {doc_path}")

    w_pts, h_pts = get_pdf_page_dimensions(doc_path, page_num=page_num)
    two_up = is_landscape_2up(w_pts, h_pts)
    image_count = count_pdf_page_images(doc_path, page_num)

    pdftotext = _resolve_tool("pdftotext", "/opt/homebrew/bin/pdftotext")
    proc_txt = subprocess.run(
        [pdftotext, "-f", str(page_num), "-l", str(page_num), str(doc_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    raw_txt = proc_txt.stdout or ""
    cleaned_txt = clean_ocr_markdown(raw_txt)
    non_ws_chars = len(re.sub(r"\s+", "", cleaned_txt))

    # Verifica layout a colonne sul testo nativo con -layout
    proc_lay = subprocess.run(
        [pdftotext, "-layout", "-f", str(page_num), "-l", str(page_num), str(doc_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    lay_lines = [ln for ln in (proc_lay.stdout or "").splitlines() if ln.strip()]
    gutter_lines = sum(1 for ln in lay_lines if _GUTTER_GAP_RE.search(ln))
    gutter_ratio = (gutter_lines / len(lay_lines)) if lay_lines else 0.0

    is_scanned_like = non_ws_chars < 180 or (image_count >= 1 and non_ws_chars < 400 and two_up)
    if two_up:
        kind = "scanned_2up" if is_scanned_like else "native_2up_or_2col"
    elif is_scanned_like:
        kind = "scanned_1col"
    elif gutter_ratio >= 0.25:
        kind = "native_2col"
    else:
        kind = "native_1col"

    return {
        "page_num": int(page_num),
        "width_pts": w_pts,
        "height_pts": h_pts,
        "is_landscape_2up": two_up,
        "native_non_ws_chars": non_ws_chars,
        "embedded_images": image_count,
        "layout_gutter_ratio": round(gutter_ratio, 3),
        "page_kind": kind,
        "raw_native_text": cleaned_txt,
    }


def extract_portrait_2col_text(doc_path: Path, page_num: int, *, dpi: int = 300) -> str:
    """Estrae a €0 colonna sinistra poi colonna destra da una pagina PDF nativa a 2 colonne."""
    w_pts, h_pts = get_pdf_page_dimensions(doc_path, page_num=page_num)
    pdftotext = _resolve_tool("pdftotext", "/opt/homebrew/bin/pdftotext")
    scale = dpi / 72.0
    w_px = max(1, int(round(w_pts * scale)))
    h_px = max(1, int(round(h_pts * scale)))
    half_w = w_px // 2
    cols: List[str] = []
    for x_off, cw in ((0, half_w), (half_w, w_px - half_w)):
        proc = subprocess.run(
            [
                pdftotext,
                "-f", str(page_num),
                "-l", str(page_num),
                "-r", str(dpi),
                "-x", str(x_off),
                "-y", "0",
                "-W", str(cw),
                "-H", str(h_px),
                str(doc_path),
                "-",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        t = clean_ocr_markdown(proc.stdout or "")
        if t.strip():
            cols.append(t.strip())
    return "\n\n".join(cols)


def _safe_anchor_id(printed_page: str, raw_id: str) -> str:
    pg_slug = re.sub(r"[^A-Za-z0-9]+", "", str(printed_page or "x")) or "x"
    id_slug = re.sub(r"[^A-Za-z0-9_\-]+", "", str(raw_id or "1")) or "1"
    return f"p{pg_slug}-{id_slug}"


def assemble_canonical_markdown(
    page_payload: Mapping[str, Any],
    *,
    figure_urls: Optional[Sequence[str]] = None,
) -> str:
    """Stadio 3b (€0): assembla deterministicamente Markdown `resuscipack-md v1` lossless."""
    printed_page = str(page_payload.get("printed_page") or "").strip()
    running_header = str(page_payload.get("running_header") or "").strip()
    section_title = str(page_payload.get("section_title") or "").strip()
    body = str(page_payload.get("body_markdown") or "").strip()
    footnotes = page_payload.get("footnotes") or []
    marginalia = page_payload.get("marginalia") or []
    boxes = page_payload.get("boxes") or []
    figures = page_payload.get("figures") or []
    tables_html = page_payload.get("tables_html") or []
    continues = bool(page_payload.get("continues_on_next_page"))

    parts: List[str] = []
    meta_bits: List[str] = []
    if printed_page:
        meta_bits.append(f"p. {printed_page}")
    if running_header:
        meta_bits.append(f"header: {running_header}")
    if meta_bits:
        parts.append(f"<!-- {' | '.join(meta_bits)} -->")

    if section_title:
        parts.append(f"## {section_title}")

    # Normalizza eventuali riferimenti [^1] nel corpo all'ancora univoca [^p<pg>-1]
    id_map: Dict[str, str] = {}
    for idx, fn in enumerate(footnotes, start=1):
        raw_id = str((fn or {}).get("id") or idx).strip()
        anchor = _safe_anchor_id(printed_page, raw_id)
        id_map[raw_id] = anchor

    def _replace_ref(match: re.Match[str]) -> str:
        tok = match.group(1)
        if tok in id_map:
            return f"[^{id_map[tok]}]"
        if tok.startswith("p") and "-" in tok:
            return match.group(0)
        return f"[^{_safe_anchor_id(printed_page, tok)}]"

    if body:
        parts.append(_FOOTNOTE_REF_RE.sub(_replace_ref, body))

    for idx, fig in enumerate(figures):
        f_obj = fig or {}
        label = str(f_obj.get("label") or f"Figura {idx + 1}").strip()
        caption = str(f_obj.get("caption") or "").strip()
        internal_labels = [str(x).strip() for x in (f_obj.get("internal_labels") or []) if str(x).strip()]
        img_url = figure_urls[idx] if (figure_urls and idx < len(figure_urls)) else ""
        if img_url:
            alt = f"{label}: {caption}" if caption else label
            parts.append(f"![{alt}]({img_url})")
        else:
            parts.append(f"> [!figure] **{label}**" + (f" — {caption}" if caption else ""))
        if internal_labels:
            parts.append(f"> *Etichette interne figura:* {', '.join(internal_labels)}")

    for tbl in tables_html:
        tbl_s = str(tbl or "").strip()
        if tbl_s:
            parts.append(tbl_s)

    for box in boxes:
        b_obj = box or {}
        b_title = str(b_obj.get("title") or "Riquadro").strip()
        b_body = str(b_obj.get("body") or "").strip()
        if b_body:
            quoted_lines = "\n".join(f"> {ln}" for ln in b_body.splitlines())
            parts.append(f"> [!box] **{b_title}**\n{quoted_lines}")

    for marg in marginalia:
        m_txt = str(marg or "").strip()
        if m_txt:
            parts.append(f"> [!margin] {m_txt}")

    if footnotes:
        fn_lines: List[str] = []
        for idx, fn in enumerate(footnotes, start=1):
            fn_obj = fn or {}
            raw_id = str(fn_obj.get("id") or idx).strip()
            anchor = id_map.get(raw_id) or _safe_anchor_id(printed_page, raw_id)
            fn_txt = " ".join(str(fn_obj.get("text") or "").split()).strip()
            if fn_txt:
                fn_lines.append(f"[^{anchor}]: {fn_txt}")
        if fn_lines:
            parts.append("\n".join(fn_lines))

    if continues:
        parts.append("<!-- continues_on_next_page: true -->")

    return "\n\n".join(p for p in parts if p).strip() + "\n"


def evaluate_page_quality_gate(
    markdown_text: str,
    *,
    expected_figure_count: int = 0,
) -> Dict[str, Any]:
    """Stadio 2 (€0): Quality Gate deterministico su pagina convertita."""
    txt = str(markdown_text or "").strip()
    issues: List[str] = []

    if len(re.sub(r"\s+", "", txt)) < 40:
        issues.append("pagina_vuota_o_troppo_corta")

    if _GARBLED_CONTROL_RE.search(txt):
        issues.append("caratteri_corrotti_o_controllo")

    # Bilanciamento blocchi display LaTeX $$...$$
    display_delims = len(re.findall(r"(?<!\\)\$\$", txt))
    if display_delims % 2 != 0:
        issues.append("latex_display_non_bilanciato")

    # Verifica coerenza note [^id] <-> [^id]:
    refs = set(_FOOTNOTE_REF_RE.findall(txt))
    defs = {m.group(1) for m in _FOOTNOTE_DEF_RE.finditer(txt)}
    missing_defs = sorted(refs - defs)
    orphan_defs = sorted(defs - refs)
    if missing_defs:
        issues.append(f"note_senza_definizione:{','.join(missing_defs[:4])}")
    if orphan_defs:
        issues.append(f"note_orfane_nel_testo:{','.join(orphan_defs[:4])}")

    # Euristica anti-mescolamento 2-up / doppia colonna (troppe righe con larghi spazi interni)
    non_empty_lines = [ln for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith(("|", "```", "<!--"))]
    if len(non_empty_lines) >= 6:
        gutter_hits = sum(1 for ln in non_empty_lines if _GUTTER_GAP_RE.search(ln))
        if gutter_hits / len(non_empty_lines) >= 0.25:
            issues.append("possibile_mescolamento_colonne_2up")

    # Copertura figure attese
    if expected_figure_count > 0:
        fig_markers = len(re.findall(r"!\[[^\]]*\]\(|> \[!figure\]", txt))
        if fig_markers < expected_figure_count:
            issues.append(f"figure_mancanti:{fig_markers}/{expected_figure_count}")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "route": "accept" if passed else "escalate_vision",
    }


def _resolve_gcp_project(explicit_project: Optional[str] = None) -> str:
    if explicit_project and explicit_project.strip():
        return explicit_project.strip()
    if DEFAULT_GCP_PROJECT.strip():
        return DEFAULT_GCP_PROJECT.strip()
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for ln in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                if k.strip() in {"GCP_PROJECT", "GOOGLE_CLOUD_PROJECT"} and v.strip():
                    return v.strip().strip("'\"")
    proc = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    proj = (proc.stdout or "").strip()
    if proj and proj != "(unset)":
        return proj
    raise RuntimeError(
        "GCP_PROJECT / GOOGLE_CLOUD_PROJECT non configurato (né .env né gcloud config)."
    )


def transcribe_page_structured_vision(
    jpeg_bytes: bytes,
    *,
    page_label: str,
    book_title: str = "",
    project_id: Optional[str] = None,
    model: str = DEFAULT_VISION_MODEL,
) -> Dict[str, Any]:
    """Stadio 3: trascrive una singola pagina immagine in JSON strutturato `resuscipack-md v1` via Vertex Vision."""
    proj = _resolve_gcp_project(project_id)
    mdl = (model or DEFAULT_VISION_MODEL).strip()
    token = _get_gcloud_token()

    instruction = (
        f"Converti la pagina {page_label!r} del libro {book_title!r} nel formato strutturato JSON `resuscipack-md v1`.\n"
        "REGOLE RIGIDE LOSSLESS:\n"
        "1. Separa il titolo corrente (`running_header`) e il numero di pagina stampato (`printed_page`, romano o arabo) dal corpo.\n"
        "2. Preserva integrali lingua originale, corsivi (*...*), grassetti (**...**), greco antico politonico/diacritici, "
        "apici e pedici matematici/chimici ($...$ o $$...$$ con \\tag{...} se numerate; raddoppia sempre i backslash LaTeX nel JSON).\n"
        "3. Distingui rigorosamente gli apici matematici dai richiami di nota: inserisci i richiami nel corpo come [^1], [^2] "
        "e trascrivi il testo esatto di ogni nota a piè di pagina dentro `footnotes[]`.\n"
        "4. Isola glosse marginali in `marginalia[]`, riquadri/box in `boxes[]`, tabelle complesse in `tables_html[]`.\n"
        "5. Per ogni figura/diagramma/circuito/tavola presente, compila `figures[]` trascrivendo didascalia esatta (`caption`) "
        "e tutte le etichette/valori visibili dentro la figura (`internal_labels`).\n"
        "6. Imposta `continues_on_next_page=true` se l'ultima frase o dimostrazione continua oltre la fine della pagina.\n"
    )

    body = json.dumps(
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": instruction},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": base64.b64encode(jpeg_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseSchema": RESUSCIPACK_MD_PAGE_SCHEMA,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode("utf-8")

    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{proj}"
        f"/locations/global/publishers/google/models/{mdl}:generateContent"
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": proj,
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    txt = raw["candidates"][0]["content"]["parts"][0]["text"]
    cleaned = _strip_json_fences(txt)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = json.loads(_repair_json_latex_escapes(cleaned))
    usage = raw.get("usageMetadata") or {}
    return {
        "payload": parsed,
        "markdown": assemble_canonical_markdown(parsed),
        "input_tokens": int(usage.get("promptTokenCount") or 0),
        "output_tokens": int(usage.get("candidatesTokenCount") or 0),
        "model": mdl,
    }
