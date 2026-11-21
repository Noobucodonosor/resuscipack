"""Pipeline append-only per OCR Vision (PDF e `.djvu`) e importazione pagine GCS (`TASK-CORPUS-04`).

Principi non negoziabili:
- STRICT READ-ONLY su `~/Desktop/PACK copy 4/source_pdf/`: qualsiasi file temporaneo
  (`pdftoppm`, `ddjvu`, `sips`, `gcloud storage cp`) vive esclusivamente in `TemporaryDirectory()`.
- Append-only reale su `pack_corpus.db`: i vecchi `block_pk` non vengono mai eliminati; sui volumi
  sotto-estratti i blocchi degradati vengono disattivati con `supersede_block()`.
- Attribuzione risorse Google Cloud (`enforcing-resource-attribution`): ogni invocazione `gcloud`
  propaga `CLOUDSDK_METRICS_ENVIRONMENT=datacloud.antigravity`.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .normalizer import (
    canonical_stem_key,
    classify_block_role,
    classify_surface_domain,
    clean_ocr_markdown,
    detect_language,
    estimate_bpe_tokens,
    make_block_uid,
    make_book_uid,
    normalize_for_match,
    parse_author_year,
)
from .schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db, supersede_block

DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "ocr_wave_manifest.json"
DEFAULT_FIGURES_DIR = Path(__file__).resolve().parents[2] / "data" / "corpus_figures"
DEFAULT_GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
DEFAULT_VISION_MODEL = "gemini-2.5-flash"
DEFAULT_GCS_OCR_PREFIX = os.getenv("RESUSCIPACK_GCS_OCR_PREFIX", f"gs://{DEFAULT_GCP_PROJECT}-unlimited-ocr/output")
DEFAULT_GCS_BATCH_PREFIX = os.getenv("RESUSCIPACK_GCS_BATCH_PREFIX", f"gs://{DEFAULT_GCP_PROJECT}-unlimited-ocr/m1_batch")

VISION_OCR_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["batch_id", "pages"],
    "properties": {
        "batch_id": {"type": "STRING"},
        "pages": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["pdf_page", "printed_page", "section_title", "block_role", "text"],
                "properties": {
                    "pdf_page": {"type": "INTEGER"},
                    "printed_page": {"type": "STRING"},
                    "section_title": {"type": "STRING"},
                    "block_role": {"type": "STRING", "enum": ["body", "paratext", "footnote"]},
                    "text": {"type": "STRING"},
                },
            },
        },
    },
}

_VISION_TOKEN_LOCK = threading.Lock()
_VISION_TOKEN_VALUE = ""
_VISION_TOKEN_TS = 0.0


def _gcloud_env() -> Dict[str, str]:
    env = os.environ.copy()
    existing = env.get("CLOUDSDK_METRICS_ENVIRONMENT", "").strip()
    if "datacloud.antigravity" not in existing.split():
        env["CLOUDSDK_METRICS_ENVIRONMENT"] = f"{existing} datacloud.antigravity".strip()
    return env


def _get_gcloud_token(*, force_refresh: bool = False) -> str:
    global _VISION_TOKEN_VALUE, _VISION_TOKEN_TS
    with _VISION_TOKEN_LOCK:
        now = time.monotonic()
        if not force_refresh and _VISION_TOKEN_VALUE and (now - _VISION_TOKEN_TS) < 1500:
            return _VISION_TOKEN_VALUE
        proc = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            env=_gcloud_env(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        tok = (proc.stdout or "").strip()
        if proc.returncode != 0 or not tok:
            raise RuntimeError(
                f"Impossibile ottenere access token gcloud per Vertex Vision (code={proc.returncode}): {proc.stderr[:220]}"
            )
        _VISION_TOKEN_VALUE = tok
        _VISION_TOKEN_TS = now
        return tok


def _resolve_tool(name: str, fallback: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    if Path(fallback).exists():
        return fallback
    raise FileNotFoundError(f"Strumento CLI richiesto non trovato: {name} (atteso anche in {fallback})")


def count_document_pages(doc_path: Path) -> int:
    """Restituisce il numero reale di pagine di un PDF (`pdfinfo`) o `.djvu` (`djvused`)."""
    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        pdfinfo = _resolve_tool("pdfinfo", "/opt/homebrew/bin/pdfinfo")
        proc = subprocess.run([pdfinfo, str(doc_path)], capture_output=True, text=True, check=True)
        m = re.search(r"^Pages:\s*(\d+)", proc.stdout, flags=re.MULTILINE)
        if not m:
            raise RuntimeError(f"Impossibile leggere il numero di pagine da pdfinfo su {doc_path}")
        return int(m.group(1))
    if suffix == ".djvu":
        djvused = _resolve_tool("djvused", "/opt/homebrew/bin/djvused")
        proc = subprocess.run([djvused, "-e", "n", str(doc_path)], capture_output=True, text=True, check=True)
        return int(proc.stdout.strip())
    raise ValueError(f"Formato documento non supportato per OCR: {doc_path.suffix}")


def parse_page_spec(spec: str, total_pages: int) -> List[int]:
    """Converte una specifica stile `'1-5,10,65-72'` in lista ordinata unica di numeri pagina 1-based."""
    pages: set[int] = set()
    for part in str(spec or "").split(","):
        p = part.strip()
        if not p:
            continue
        if "-" in p:
            a_s, b_s = p.split("-", 1)
            a, b = max(1, int(a_s)), min(total_pages, int(b_s))
            if a <= b:
                pages.update(range(a, b + 1))
        else:
            val = int(p)
            if 1 <= val <= total_pages:
                pages.add(val)
    return sorted(pages)


def render_pages_to_jpeg_bytes(
    doc_path: Path,
    page_numbers: Sequence[int],
    *,
    dpi: int = 150,
) -> List[Tuple[int, bytes]]:
    """Renderizza in modo read-only le pagine richieste (.pdf o .djvu) in JPEG in memoria usando TemporaryDirectory."""
    if not doc_path.exists():
        raise FileNotFoundError(f"Documento sorgente non trovato: {doc_path}")
    suffix = doc_path.suffix.lower()
    results: List[Tuple[int, bytes]] = []

    with tempfile.TemporaryDirectory(prefix="resuscipack_ocr_") as tmp_str:
        tmpdir = Path(tmp_str)
        if suffix == ".pdf":
            pdftoppm = _resolve_tool("pdftoppm", "/opt/homebrew/bin/pdftoppm")
            for pnum in page_numbers:
                prefix = tmpdir / f"p_{pnum:04d}"
                subprocess.run(
                    [pdftoppm, "-jpeg", "-r", str(dpi), "-f", str(pnum), "-l", str(pnum), str(doc_path), str(prefix)],
                    capture_output=True,
                    check=True,
                )
                generated = sorted(tmpdir.glob(f"p_{pnum:04d}*.jpg"))
                if not generated:
                    raise RuntimeError(f"pdftoppm non ha prodotto JPEG per pagina {pnum} di {doc_path.name}")
                results.append((int(pnum), generated[0].read_bytes()))
        elif suffix == ".djvu":
            ddjvu = _resolve_tool("ddjvu", "/opt/homebrew/bin/ddjvu")
            sips = _resolve_tool("sips", "/usr/bin/sips")
            for pnum in page_numbers:
                tiff_path = tmpdir / f"p_{pnum:04d}.tiff"
                jpg_path = tmpdir / f"p_{pnum:04d}.jpg"
                subprocess.run(
                    [ddjvu, "-format=tiff", f"-page={pnum}", str(doc_path), str(tiff_path)],
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    [sips, "-s", "format", "jpeg", "-s", "formatOptions", "80", str(tiff_path), "--out", str(jpg_path)],
                    capture_output=True,
                    check=True,
                )
                results.append((int(pnum), jpg_path.read_bytes()))
        else:
            raise ValueError(f"Formato non supportato per rendering immagini: {suffix}")

    return results


def get_pdf_page_dimensions(doc_path: Path, page_num: int = 1) -> Tuple[float, float]:
    """Legge le dimensioni `(width_pts, height_pts)` di una pagina PDF via `pdfinfo`."""
    if not doc_path.exists():
        raise FileNotFoundError(f"Documento PDF non trovato: {doc_path}")
    pdfinfo = _resolve_tool("pdfinfo", "/opt/homebrew/bin/pdfinfo")
    proc = subprocess.run(
        [pdfinfo, "-f", str(page_num), "-l", str(page_num), str(doc_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    m = re.search(r"Page(?:\s+\d+)?\s+size:\s*([0-9]+(?:\.[0-9]+)?)\s*x\s*([0-9]+(?:\.[0-9]+)?)", proc.stdout)
    if not m:
        raise RuntimeError(f"Dimensioni pagina non leggibili da pdfinfo per {doc_path.name} p.{page_num}")
    return float(m.group(1)), float(m.group(2))


def is_landscape_2up(width_pts: float, height_pts: float, ratio_threshold: float = 1.15) -> bool:
    """Rileva scansioni/PDF landscape 2-up (`width > height * 1.15`)."""
    return height_pts > 0 and width_pts > height_pts * ratio_threshold


def _parse_sips_dimensions(img_path: Path) -> Tuple[int, int]:
    sips = _resolve_tool("sips", "/usr/bin/sips")
    proc = subprocess.run(
        [sips, "-g", "pixelWidth", "-g", "pixelHeight", str(img_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    mw = re.search(r"pixelWidth:\s*(\d+)", proc.stdout)
    mh = re.search(r"pixelHeight:\s*(\d+)", proc.stdout)
    if not mw or not mh:
        raise RuntimeError(f"Dimensioni immagine non leggibili da sips: {img_path}")
    return int(mw.group(1)), int(mh.group(1))


def split_2up_pdf_pages_to_jpegs(
    doc_path: Path,
    page_numbers: Sequence[int],
    *,
    dpi: int = 150,
    overlap_px: int = 16,
    ratio_threshold: float = 1.15,
) -> List[Tuple[int, str, bytes]]:
    """Renderizza pagine PDF landscape 2-up dividendole verticalmente in `(page_num, 'L'|'R'|'full', jpeg_bytes)`
    esclusivamente dentro `TemporaryDirectory` (sorgente `STRICT READ-ONLY`)."""
    if not doc_path.exists():
        raise FileNotFoundError(f"Documento PDF non trovato: {doc_path}")
    pdftoppm = _resolve_tool("pdftoppm", "/opt/homebrew/bin/pdftoppm")
    sips = _resolve_tool("sips", "/usr/bin/sips")
    results: List[Tuple[int, str, bytes]] = []

    with tempfile.TemporaryDirectory(prefix="resuscipack_2up_") as tmp_str:
        tmpdir = Path(tmp_str)
        for pnum in page_numbers:
            prefix = tmpdir / f"full_{pnum:04d}"
            subprocess.run(
                [pdftoppm, "-jpeg", "-r", str(dpi), "-f", str(pnum), "-l", str(pnum), str(doc_path), str(prefix)],
                capture_output=True,
                check=True,
            )
            generated = sorted(tmpdir.glob(f"full_{pnum:04d}*.jpg"))
            if not generated:
                raise RuntimeError(f"pdftoppm non ha prodotto JPEG per pagina {pnum} di {doc_path.name}")
            full_img = generated[0]
            w_px, h_px = _parse_sips_dimensions(full_img)
            if not is_landscape_2up(float(w_px), float(h_px), ratio_threshold=ratio_threshold):
                results.append((int(pnum), "full", full_img.read_bytes()))
                continue

            half_w = w_px // 2
            left_w = min(w_px, half_w + max(0, int(overlap_px)))
            right_x = max(0, half_w - max(0, int(overlap_px)))
            right_w = w_px - right_x

            left_img = tmpdir / f"left_{pnum:04d}.jpg"
            right_img = tmpdir / f"right_{pnum:04d}.jpg"
            shutil.copy2(full_img, left_img)
            shutil.copy2(full_img, right_img)

            subprocess.run(
                [sips, "--cropOffset", "0", "0", "--cropToHeightWidth", str(h_px), str(left_w), str(left_img)],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [sips, "--cropOffset", "0", str(right_x), "--cropToHeightWidth", str(h_px), str(right_w), str(right_img)],
                capture_output=True,
                check=True,
            )
            results.append((int(pnum), "L", left_img.read_bytes()))
            results.append((int(pnum), "R", right_img.read_bytes()))

    return results


def extract_2up_pdf_text_columns(
    doc_path: Path,
    page_numbers: Sequence[int],
    *,
    dpi: int = 72,
    ratio_threshold: float = 1.15,
) -> List[Dict[str, Any]]:
    """Estrae testo a colonne separate (sinistra poi destra) da PDF nativi 2-up/2-colonne a €0 via `pdftotext`."""
    if not doc_path.exists():
        raise FileNotFoundError(f"Documento PDF non trovato: {doc_path}")
    pdftotext = _resolve_tool("pdftotext", "/opt/homebrew/bin/pdftotext")
    pages_out: List[Dict[str, Any]] = []
    seq = 1
    for pnum in page_numbers:
        w_pts, h_pts = get_pdf_page_dimensions(doc_path, page_num=pnum)
        scale = dpi / 72.0
        w_px = max(1, int(round(w_pts * scale)))
        h_px = max(1, int(round(h_pts * scale)))
        if not is_landscape_2up(w_pts, h_pts, ratio_threshold=ratio_threshold):
            proc = subprocess.run(
                [pdftotext, "-f", str(pnum), "-l", str(pnum), str(doc_path), "-"],
                capture_output=True,
                text=True,
                check=True,
            )
            txt = clean_ocr_markdown(proc.stdout or "")
            pages_out.append({"pdf_page": seq, "source_pdf_page": int(pnum), "side": "full", "printed_page": str(pnum), "text": txt})
            seq += 1
            continue

        half_w = w_px // 2
        for side, x_off, cw in (("L", 0, half_w), ("R", half_w, w_px - half_w)):
            proc = subprocess.run(
                [
                    pdftotext,
                    "-f", str(pnum),
                    "-l", str(pnum),
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
            txt = clean_ocr_markdown(proc.stdout or "")
            pages_out.append(
                {
                    "pdf_page": seq,
                    "source_pdf_page": int(pnum),
                    "side": side,
                    "printed_page": f"{pnum}{side}",
                    "text": txt,
                }
            )
            seq += 1
    return pages_out


def _strip_json_fences(raw_text: str) -> str:
    txt = raw_text.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


def _repair_json_latex_escapes(raw_json: str) -> str:
    """Ripara eventuali backslash LaTeX non raddoppiati dentro stringhe JSON (es. `\\sigma` -> `\\\\sigma`)."""
    return re.sub(r'\\(?![\\/"bfnrtu])', r'\\\\', raw_json)


def transcribe_pages_via_vertex_vision(
    page_images: Sequence[Tuple[int, bytes]],
    *,
    book_title: str,
    project_id: str = DEFAULT_GCP_PROJECT,
    model: str = DEFAULT_VISION_MODEL,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Trascrive un lotto (consigliato 1..4 pagine) JPEG tramite Gemini 2.5 Flash Vision su Vertex AI (`thinkingBudget=0`)."""
    if not page_images:
        return [], 0, 0

    proj = project_id or os.environ.get("GCP_PROJECT_ID", DEFAULT_GCP_PROJECT)
    mdl = model or os.environ.get("VERTEX_GEMINI_MODEL", DEFAULT_VISION_MODEL)
    online_locations = ("us-central1", "global", "europe-west1", "us-east4")

    page_list_str = ", ".join(str(p) for p, _ in page_images)
    instruction = (
        f"Stai trascrivendo pagine scansionate del volume: {book_title!r}.\n"
        f"Le immagini allegate corrispondono nell'ordine esatto ai numeri pagina PDF: [{page_list_str}].\n"
        "Rispondi SOLO con JSON valido nel formato:\n"
        '{"pages":[{"pdf_page":65,"printed_page":"73","section_title":"Libro I - Definizioni",'
        '"block_role":"body|paratext|footnote","text":"..."}]}\n'
        "REGOLE TASSATIVE:\n"
        "1. Trascrivi fedelmente tutto il testo stampato nella lingua originale dell'edizione (italiano/latino/inglese), "
        "ricucendo le parole spezzate a fine riga.\n"
        "2. Rendi le formule e notazioni matematiche in LaTeX pulito ($...$ o $$...$$) quando presenti; dentro le stringhe JSON "
        "raddoppia sempre i backslash LaTeX (es. \\\\frac, \\\\sigma) affinché il JSON resti valido.\n"
        "3. Rimuovi eventuali filigrane ripetitive come 'Cultura_in_Ita5', 'Cultura_in_Ita' o URL 'scribd.com'.\n"
        "4. Imposta block_role='paratext' su indici, sommari, bibliografie, frontespizi o pagine bianche; "
        "'body' sul testo sostantivo (definizioni, teoremi, dimostrazioni, commenti).\n"
        "5. Se una pagina ha figure geometriche, aggiungi una riga breve `[Figura geometrica: descrivi lettere/etichette visibili]`.\n"
        "6. Negli indici/tabelle NON trascrivere puntini di allineamento (`. . .` o `....`) né linee/trattini ripetuti: separa titolo e numero di pagina con un singolo spazio.\n"
    )

    parts: List[Dict[str, Any]] = [{"text": instruction}]
    for pnum, img_bytes in page_images:
        parts.append({"text": f"[INIZIO IMMAGINE PAGINA PDF {pnum}]"})
        parts.append(
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64.b64encode(img_bytes).decode("ascii"),
                }
            }
        )

    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseSchema": VISION_OCR_RESPONSE_SCHEMA,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode("utf-8")

    backoffs = (4.0, 12.0, 28.0, 55.0)
    last_err: Optional[Exception] = None
    for attempt in range(len(backoffs) + 1):
        loc = online_locations[attempt % len(online_locations)]
        host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
        url = (
            f"https://{host}/v1/projects/{proj}"
            f"/locations/{loc}/publishers/google/models/{mdl}:generateContent"
        )
        token = _get_gcloud_token(force_refresh=(attempt > 0))
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": proj,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            txt = raw["candidates"][0]["content"]["parts"][0]["text"]
            cleaned_txt = _strip_json_fences(txt)
            usage = raw.get("usageMetadata") or {}
            in_tok = int(usage.get("promptTokenCount") or 0)
            out_tok = int(usage.get("candidatesTokenCount") or 0)
            try:
                parsed = json.loads(cleaned_txt)
            except json.JSONDecodeError:
                try:
                    parsed = json.loads(_repair_json_latex_escapes(cleaned_txt))
                except json.JSONDecodeError:
                    if len(page_images) > 1:
                        mid = len(page_images) // 2
                        p_left, li, lo = transcribe_pages_via_vertex_vision(
                            page_images[:mid],
                            book_title=book_title,
                            project_id=project_id,
                            model=model,
                        )
                        p_right, ri, ro = transcribe_pages_via_vertex_vision(
                            page_images[mid:],
                            book_title=book_title,
                            project_id=project_id,
                            model=model,
                        )
                        return p_left + p_right, in_tok + li + ri, out_tok + lo + ro
                    # Pagina singola con JSON troncato (es. loop su puntini di indici/tabelle):
                    # recupero in testo semplice con anti-loop e stopSequences.
                    pnum_single, img_single = page_images[0]
                    plain_body = json.dumps(
                        {
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [
                                        {
                                            "text": (
                                                f"Trascrivi il testo della pagina {pnum_single} di {book_title!r} "
                                                "in testo semplice senza puntini di riempimento (. . .) o spazi ripetuti."
                                            )
                                        },
                                        {
                                            "inlineData": {
                                                "mimeType": "image/jpeg",
                                                "data": base64.b64encode(img_single).decode("ascii"),
                                            }
                                        },
                                    ],
                                }
                            ],
                            "generationConfig": {
                                "temperature": 0.2,
                                "maxOutputTokens": 4096,
                                "thinkingConfig": {"thinkingBudget": 0},
                                "stopSequences": [". . . . . .", "........", "________", "--------"],
                            },
                        }
                    ).encode("utf-8")
                    plain_req = urllib.request.Request(
                        url,
                        data=plain_body,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {token}",
                            "x-goog-user-project": proj,
                        },
                    )
                    with urllib.request.urlopen(plain_req, timeout=120) as p_resp:
                        p_raw = json.loads(p_resp.read().decode("utf-8"))
                    p_txt = (
                        ((p_raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
                    )[0].get("text", "")
                    p_txt = re.sub(r"(?:\.\s*){5,}", " ", p_txt).strip()
                    p_usage = p_raw.get("usageMetadata") or {}
                    p_in = in_tok + int(p_usage.get("promptTokenCount") or 0)
                    p_out = out_tok + int(p_usage.get("candidatesTokenCount") or 0)
                    role = classify_block_role(p_txt, "") if p_txt else "paratext"
                    return (
                        [
                            {
                                "pdf_page": int(pnum_single),
                                "printed_page": str(pnum_single),
                                "section_title": "",
                                "block_role": role,
                                "text": p_txt,
                            }
                        ],
                        p_in,
                        p_out,
                    )
            pages_out = parsed.get("pages") if isinstance(parsed, dict) else []
            norm_pages: List[Dict[str, Any]] = []
            for idx, p_obj in enumerate(pages_out or []):
                if isinstance(p_obj, Mapping):
                    d = dict(p_obj)
                    if len(pages_out) == len(page_images):
                        d["pdf_page"] = int(page_images[idx][0])
                    norm_pages.append(d)
            return norm_pages, in_tok, out_tok
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in {401, 429, 500, 503} and attempt < len(backoffs):
                time.sleep(backoffs[attempt] + random.uniform(0.0, 2.5))
                continue
            detail = exc.read().decode("utf-8", errors="ignore")[:260]
            raise RuntimeError(f"Vertex Vision HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            last_err = exc
            if attempt < len(backoffs):
                time.sleep(backoffs[attempt] + random.uniform(0.0, 2.5))
                continue
            raise RuntimeError(f"Errore Vertex Vision OCR: {exc}") from exc

    raise RuntimeError(f"Vertex Vision OCR fallito: {last_err}")


def _find_or_create_book(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_path: str,
    surface_domain: str,
    source_kind: str,
    total_pages: int,
    sample_text: str,
) -> Tuple[int, str]:
    ckey = canonical_stem_key(title)
    existing_rows = conn.execute(
        "SELECT book_pk, book_uid, title FROM books WHERE is_active = 1"
    ).fetchall()
    for row in existing_rows:
        if canonical_stem_key(str(row["title"])) == ckey:
            return int(row["book_pk"]), str(row["book_uid"])

    book_uid = make_book_uid(ckey or title, source_kind)
    row_by_uid = conn.execute(
        "SELECT book_pk, book_uid FROM books WHERE book_uid = ?",
        (book_uid,),
    ).fetchone()
    if row_by_uid is not None:
        return int(row_by_uid["book_pk"]), str(row_by_uid["book_uid"])

    author, year = parse_author_year(title)
    lang = detect_language(sample_text)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO books (
            book_uid, title, author, year, surface_domain, language,
            source_kind, source_path, page_count, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            book_uid,
            title,
            author,
            year,
            surface_domain,
            lang,
            source_kind,
            source_path,
            int(total_pages),
            now_iso,
        ),
    )
    return int(cur.lastrowid), book_uid


def ingest_ocr_pages_append_only(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_path: str,
    surface_domain: Optional[str] = None,
    source_kind: str = "vertex_vision_ocr",
    total_pages: int = 0,
    transcribed_pages: Sequence[Mapping[str, Any]],
    supersede_under_extracted: bool = False,
) -> Dict[str, Any]:
    """Inserisce in modalità append-only pagine trascritte in `blocks` (+ `books`), senza alterare
    alcuno dei `block_pk` preesistenti e disattivando eventuali vecchi blocchi degradati se richiesto."""
    cleaned_pages: List[Dict[str, Any]] = []
    for p in transcribed_pages:
        pdf_page = int(p.get("pdf_page") or p.get("page") or 0)
        raw_txt = str(p.get("text") or p.get("content") or "")
        cleaned = clean_ocr_markdown(raw_txt)
        if not cleaned or len(cleaned) < 20:
            continue
        sec_title = " ".join(str(p.get("section_title") or "").split()).strip()
        raw_role = str(p.get("block_role") or "").strip().lower()
        role = raw_role if raw_role in {"body", "footnote", "paratext"} else classify_block_role(cleaned, sec_title)
        printed_page = str(p.get("printed_page") or (str(pdf_page) if pdf_page > 0 else "")).strip()
        cleaned_pages.append(
            {
                "pdf_page": pdf_page,
                "printed_page": printed_page,
                "section_title": sec_title,
                "block_role": role,
                "content": cleaned,
            }
        )

    if not cleaned_pages:
        return {"book_pk": None, "blocks_inserted": 0, "blocks_skipped": 0, "blocks_superseded": 0}

    sample_txt = "\n\n".join(p["content"] for p in cleaned_pages[:4])
    eff_domain = surface_domain or classify_surface_domain(title, sample_txt)
    book_pk, book_uid = _find_or_create_book(
        conn,
        title=title,
        source_path=source_path,
        surface_domain=eff_domain,
        source_kind=source_kind,
        total_pages=total_pages or max(p["pdf_page"] for p in cleaned_pages),
        sample_text=sample_txt,
    )

    old_active_pks: List[int] = []
    if supersede_under_extracted:
        old_active_pks = [
            int(r[0])
            for r in conn.execute(
                """
                SELECT block_pk FROM blocks
                WHERE book_pk = ? AND is_active = 1
                  AND COALESCE(source_origin, '') NOT IN (
                      'gcs_baidu_ocr',
                      'vertex_vision_ocr',
                      'vertex_vision_batch',
                      'djvutxt_layer',
                      'pdftotext_tail'
                  )
                """,
                (book_pk,),
            ).fetchall()
        ]

    inserted_pks: List[int] = []
    skipped = 0
    for item in cleaned_pages:
        content = item["content"]
        norm_c = normalize_for_match(content)
        if not norm_c:
            skipped += 1
            continue
        pnum = item["pdf_page"]
        blk_uid = make_block_uid(book_uid, pnum, pnum, norm_c)
        exists = conn.execute(
            "SELECT block_pk FROM blocks WHERE block_uid = ?",
            (blk_uid,),
        ).fetchone()
        if exists is not None:
            skipped += 1
            continue

        cur = conn.execute(
            """
            INSERT INTO blocks (
                block_uid, book_pk, book_title, is_active, block_role,
                page_start, page_end, printed_page, section_title,
                content, norm_content, char_count, est_tokens, source_origin
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                blk_uid,
                book_pk,
                title,
                item["block_role"],
                pnum,
                pnum,
                item["printed_page"],
                item["section_title"],
                content,
                norm_c,
                len(content),
                estimate_bpe_tokens(content),
                source_kind,
            ),
        )
        inserted_pks.append(int(cur.lastrowid))

    superseded_count = 0
    if supersede_under_extracted and old_active_pks and inserted_pks:
        anchor_pk = inserted_pks[0]
        for old_pk in old_active_pks:
            if old_pk != anchor_pk:
                supersede_block(conn, old_pk, anchor_pk)
                superseded_count += 1

    conn.commit()
    return {
        "book_pk": book_pk,
        "book_uid": book_uid,
        "surface_domain": eff_domain,
        "inserted_block_pks": inserted_pks,
        "blocks_inserted": len(inserted_pks),
        "blocks_skipped": skipped,
        "blocks_superseded": superseded_count,
    }


def list_gcs_ocr_matches(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    gcs_prefix: str = DEFAULT_GCS_OCR_PREFIX,
) -> List[Dict[str, Any]]:
    """Trova quali volumi del manifesto risultano già elaborati dal runner Baidu su GCS."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["gcloud", "storage", "ls", f"{gcs_prefix.rstrip('/')}/"],
        env=_gcloud_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    gcs_by_ck: Dict[str, str] = {}
    for line in proc.stdout.splitlines():
        clean = line.strip().rstrip("/")
        if clean:
            name = clean.rsplit("/", 1)[-1]
            gcs_by_ck[canonical_stem_key(name)] = clean

    matches: List[Dict[str, Any]] = []
    for wname, wdata in manifest.get("waves", {}).items():
        for doc in wdata.get("documents", []):
            ck = canonical_stem_key(doc["title"])
            if ck in gcs_by_ck:
                matches.append(
                    {
                        "wave": wname,
                        "title": doc["title"],
                        "pages_needed": doc["pages_needed"],
                        "defect_category": doc["defect_category"],
                        "gcs_dir": gcs_by_ck[ck],
                    }
                )
    return matches


def get_book_active_pages(conn: sqlite3.Connection, title: str) -> Tuple[Optional[int], Optional[str], set[int]]:
    """Restituisce `(book_pk, book_uid, insieme_pagine_attive)` se il titolo canonico esiste in `books`."""
    ck = canonical_stem_key(title)
    for row in conn.execute("SELECT book_pk, book_uid, title FROM books WHERE is_active = 1").fetchall():
        if canonical_stem_key(str(row["title"])) == ck:
            bpk = int(row["book_pk"])
            pages = {
                int(r[0])
                for r in conn.execute(
                    "SELECT page_start FROM blocks WHERE book_pk = ? AND is_active = 1 AND page_start IS NOT NULL",
                    (bpk,),
                ).fetchall()
            }
            return bpk, str(row["book_uid"]), pages
    return None, None, set()


def _decode_djvu_bytes(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")


def extract_djvu_text_pages(doc_path: Path) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Estrae in sola lettura il layer testuale completo per pagina di un `.djvu` tramite `djvutxt`."""
    doc_path = Path(doc_path)
    tot_pages = count_document_pages(doc_path)
    djvutxt = _resolve_tool("djvutxt", "/opt/homebrew/bin/djvutxt")
    proc = subprocess.run([djvutxt, str(doc_path)], capture_output=True, check=True)
    chunks = proc.stdout.split(b"\x0c")
    if len(chunks) > tot_pages and chunks[-1].strip() == b"":
        chunks = chunks[:-1]

    pages_out: List[Dict[str, Any]] = []
    sparse_pages: List[int] = []
    if len(chunks) == tot_pages:
        for pnum, chunk in enumerate(chunks, start=1):
            txt = clean_ocr_markdown(_decode_djvu_bytes(chunk))
            if len(txt) < 25:
                sparse_pages.append(pnum)
            else:
                pages_out.append({"pdf_page": pnum, "printed_page": str(pnum), "text": txt})
    else:
        for pnum in range(1, tot_pages + 1):
            p_proc = subprocess.run([djvutxt, f"--page={pnum}", str(doc_path)], capture_output=True, check=True)
            txt = clean_ocr_markdown(_decode_djvu_bytes(p_proc.stdout))
            if len(txt) < 25:
                sparse_pages.append(pnum)
            else:
                pages_out.append({"pdf_page": pnum, "printed_page": str(pnum), "text": txt})
    return pages_out, sparse_pages


def ingest_djvu_document(
    conn: sqlite3.Connection,
    doc_path: Path,
    *,
    title: Optional[str] = None,
    supersede_under_extracted: bool = True,
) -> Dict[str, Any]:
    """Ingerisce in modalità append-only il testo reale contenuto nello strato `djvutxt` (0 € API)."""
    doc_path = Path(doc_path)
    eff_title = title or doc_path.stem
    tot_pages = count_document_pages(doc_path)
    parsed_pages, sparse_pages = extract_djvu_text_pages(doc_path)
    res = ingest_ocr_pages_append_only(
        conn,
        title=eff_title,
        source_path=str(doc_path),
        source_kind="djvutxt_layer",
        total_pages=tot_pages,
        transcribed_pages=parsed_pages,
        supersede_under_extracted=supersede_under_extracted,
    )
    return {
        **res,
        "total_pages": tot_pages,
        "text_pages_extracted": len(parsed_pages),
        "sparse_pages_count": len(sparse_pages),
        "sparse_pages": sparse_pages,
    }


def extract_pdf_embedded_text_pages(doc_path: Path, page_numbers: Sequence[int]) -> List[Dict[str, Any]]:
    """Estrae pagine specifiche da un PDF già dotato di layer testuale affidabile via `pdftotext`."""
    doc_path = Path(doc_path)
    pdftotext = _resolve_tool("pdftotext", "/opt/homebrew/bin/pdftotext")
    out: List[Dict[str, Any]] = []
    for pnum in sorted({int(p) for p in page_numbers}):
        proc = subprocess.run(
            [pdftotext, "-f", str(pnum), "-l", str(pnum), str(doc_path), "-"],
            capture_output=True,
            check=True,
        )
        txt = clean_ocr_markdown(proc.stdout.decode("utf-8", errors="ignore"))
        if len(txt) >= 25:
            out.append({"pdf_page": pnum, "printed_page": str(pnum), "text": txt})
    return out


def import_gcs_baidu_book(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_path: str,
    gcs_dir: str,
    total_pages: int = 0,
    supersede_under_extracted: bool = False,
    only_pages: Optional[Sequence[int]] = None,
    sync_images: bool = True,
    figures_dir: Path = DEFAULT_FIGURES_DIR,
) -> Dict[str, Any]:
    """Scarica temporaneamente i file `pages/page_*.md` e le figure `images/*` già presenti in GCS
    (0 € API Vision) e li ingerisce in modalità append-only dentro `pack_corpus.db`."""
    allowed_pages = {int(p) for p in only_pages} if only_pages is not None else None
    parsed_pages: List[Dict[str, Any]] = []

    ls_proc = subprocess.run(
        ["gcloud", "storage", "ls", f"{gcs_dir.rstrip('/')}/pages/*.md"],
        env=_gcloud_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if ls_proc.returncode != 0 or not ls_proc.stdout.strip():
        return {
            "book_pk": None,
            "book_uid": None,
            "blocks_inserted": 0,
            "blocks_skipped": 0,
            "blocks_superseded": 0,
            "pages_found_in_gcs": 0,
            "figures_synced": 0,
        }

    with tempfile.TemporaryDirectory(prefix="resuscipack_gcs_ocr_") as tmp_str:
        tmpdir = Path(tmp_str)
        pages_src = f"{gcs_dir.rstrip('/')}/pages/*.md"
        proc = subprocess.run(
            ["gcloud", "storage", "cp", pages_src, str(tmpdir)],
            env=_gcloud_env(),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Impossibile copiare pagine GCS da {pages_src}: {proc.stderr[:240]}")

        for md_file in sorted(tmpdir.glob("page_*.md")):
            m = re.search(r"page_(\d+)\.md$", md_file.name)
            pnum = int(m.group(1)) if m else 0
            if allowed_pages is not None and pnum not in allowed_pages:
                continue
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            parsed_pages.append({"pdf_page": pnum, "text": text})

    ingest_res = ingest_ocr_pages_append_only(
        conn,
        title=title,
        source_path=source_path,
        source_kind="gcs_baidu_ocr",
        total_pages=total_pages,
        transcribed_pages=parsed_pages,
        supersede_under_extracted=supersede_under_extracted,
    )

    figures_synced = 0
    book_uid = ingest_res.get("book_uid")
    if sync_images and book_uid:
        dest_dir = Path(figures_dir) / str(book_uid)
        if dest_dir.exists() and any(dest_dir.iterdir()):
            figures_synced = len(list(dest_dir.glob("*")))
        else:
            img_ls = subprocess.run(
                ["gcloud", "storage", "ls", f"{gcs_dir.rstrip('/')}/images/"],
                env=_gcloud_env(),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            img_lines = [ln.strip() for ln in img_ls.stdout.splitlines() if ln.strip()]
            if img_ls.returncode == 0 and img_lines:
                dest_dir.mkdir(parents=True, exist_ok=True)
                cp_img = subprocess.run(
                    ["gcloud", "storage", "cp", f"{gcs_dir.rstrip('/')}/images/*", str(dest_dir)],
                    env=_gcloud_env(),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if cp_img.returncode == 0:
                    figures_synced = len(list(dest_dir.glob("*")))

    return {
        **ingest_res,
        "pages_found_in_gcs": len(parsed_pages),
        "figures_synced": figures_synced,
    }


def _slug_for_gcs(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", canonical_stem_key(title)).strip("_")
    return f"{s[:48]}_{hashlib.sha1(title.encode('utf-8')).hexdigest()[:8]}" if s else hashlib.sha1(title.encode('utf-8')).hexdigest()[:12]


def prepare_vision_batch_jsonl(
    tasks: Sequence[Mapping[str, Any]],
    out_jsonl_path: Path | str,
    *,
    gcs_batch_prefix: str = DEFAULT_GCS_BATCH_PREFIX,
    pages_per_request: int = 4,
    dpi: int = 135,
    min_blank_bytes: int = 8000,
    upload_to_gcs: bool = True,
) -> Dict[str, Any]:
    """Renderizza in TemporaryDirectory i JPEG delle pagine PDF/DjVu mancanti, li carica su GCS
    e costruisce un JSONL nativo Vertex AI `batchPredictionJobs` (`fileData.fileUri`, -50%)."""
    out_path = Path(out_jsonl_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdftoppm = _resolve_tool("pdftoppm", "/opt/homebrew/bin/pdftoppm")
    manifest_map: Dict[str, Dict[str, Any]] = {}
    requests_written = 0
    pages_queued = 0
    blank_skipped = 0

    with out_path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            doc_path = Path(task["source_path"])
            title = str(task["title"])
            defect_cat = str(task["defect_category"])
            wanted_pages = sorted({int(p) for p in task["page_numbers"] if int(p) > 0})
            if not wanted_pages:
                continue

            slug = _slug_for_gcs(title)
            gcs_img_dir = f"{gcs_batch_prefix.rstrip('/')}/ocr_pages/{slug}"
            wanted_set = set(wanted_pages)

            with tempfile.TemporaryDirectory(prefix=f"vision_prep_{slug[:16]}_") as tmp_str:
                tmpdir = Path(tmp_str)
                rendered_files: List[Tuple[int, Path]] = []
                if doc_path.suffix.lower() == ".pdf":
                    # Rendering a blocchi contigui di 60 pagine per velocità (zero I/O sul sorgente)
                    ranges: List[Tuple[int, int]] = []
                    for p in wanted_pages:
                        if not ranges or p > ranges[-1][1] + 8 or (p - ranges[-1][0]) >= 60:
                            ranges.append((p, p))
                        else:
                            ranges[-1] = (ranges[-1][0], p)
                    for a, b in ranges:
                        prefix = tmpdir / "page"
                        subprocess.run(
                            [pdftoppm, "-jpeg", "-r", str(dpi), "-f", str(a), "-l", str(b), str(doc_path), str(prefix)],
                            capture_output=True,
                            check=True,
                        )
                    for jpg in sorted(tmpdir.glob("page-*.jpg")):
                        mm = re.search(r"page-(\d+)\.jpg$", jpg.name)
                        if not mm:
                            continue
                        pnum = int(mm.group(1))
                        if pnum not in wanted_set:
                            jpg.unlink(missing_ok=True)
                            continue
                        if jpg.stat().st_size < min_blank_bytes:
                            jpg.unlink(missing_ok=True)
                            blank_skipped += 1
                            continue
                        std_jpg = tmpdir / f"p{pnum:04d}.jpg"
                        jpg.rename(std_jpg)
                        rendered_files.append((pnum, std_jpg))
                else:
                    for pnum, jpg_bytes in render_pages_to_jpeg_bytes(doc_path, wanted_pages, dpi=dpi):
                        if len(jpg_bytes) < min_blank_bytes:
                            blank_skipped += 1
                            continue
                        std_jpg = tmpdir / f"p{pnum:04d}.jpg"
                        std_jpg.write_bytes(jpg_bytes)
                        rendered_files.append((pnum, std_jpg))

                rendered_files.sort(key=lambda x: x[0])
                if not rendered_files:
                    continue

                if upload_to_gcs:
                    subprocess.run(
                        ["gcloud", "storage", "cp", "-q", f"{tmpdir}/p*.jpg", f"{gcs_img_dir}/"],
                        env=_gcloud_env(),
                        capture_output=True,
                        text=True,
                        timeout=600,
                        check=True,
                    )

                step = max(1, min(int(pages_per_request), 4))
                for idx in range(0, len(rendered_files), step):
                    chunk = rendered_files[idx : idx + step]
                    p_nums = [p for p, _ in chunk]
                    bid = f"ocr_{slug}_{p_nums[0]:04d}_{p_nums[-1]:04d}"
                    manifest_map[bid] = {
                        "title": title,
                        "source_path": str(doc_path),
                        "defect_category": defect_cat,
                        "total_pages": int(task.get("total_pages") or 0),
                        "page_numbers": p_nums,
                    }
                    page_list_str = ", ".join(str(p) for p in p_nums)
                    instruction = (
                        f"batch_id='{bid}' | Volume: {title!r}.\n"
                        f"Le immagini allegate corrispondono nell'ordine esatto ai numeri PDF: [{page_list_str}].\n"
                        "Restituisci JSON valido secondo lo schema allegato:\n"
                        "1. Trascrivi fedelmente tutto il testo stampato nella lingua originale (ricucendo le parole spezzate a fine riga).\n"
                        "2. Formule in LaTeX pulito ($...$ o $$...$$).\n"
                        "3. Rimuovi filigrane ripetitive ('Cultura_in_Ita5', 'Cultura_in_Ita', 'scribd.com').\n"
                        "4. block_role='paratext' per indici/bibliografie/frontespizi/pagine vuote; 'body' per testo sostantivo; breve nota `[Figura: ...]` se presenti diagrammi.\n"
                        "5. Negli indici/tabelle NON trascrivere puntini di allineamento (`. . .` o `....`) né linee/trattini ripetuti: separa voce e numero pagina con un singolo spazio."
                    )
                    parts: List[Dict[str, Any]] = [{"text": instruction}]
                    for pnum, _jpg_path in chunk:
                        parts.append({"text": f"[PAGINA PDF {pnum}]"})
                        parts.append(
                            {
                                "fileData": {
                                    "mimeType": "image/jpeg",
                                    "fileUri": f"{gcs_img_dir}/p{pnum:04d}.jpg",
                                }
                            }
                        )
                    record = {
                        "request": {
                            "contents": [{"role": "user", "parts": parts}],
                            "generationConfig": {
                                "temperature": 0.0,
                                "maxOutputTokens": 8192,
                                "responseMimeType": "application/json",
                                "responseSchema": VISION_OCR_RESPONSE_SCHEMA,
                                "thinkingConfig": {"thinkingBudget": 0},
                            },
                        }
                    }
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    requests_written += 1
                    pages_queued += len(p_nums)

    manifest_path = out_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest_map, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "jsonl_path": str(out_path),
        "manifest_path": str(manifest_path),
        "requests_written": requests_written,
        "pages_queued": pages_queued,
        "blank_skipped": blank_skipped,
    }


def import_vision_batch_outputs(
    conn: sqlite3.Connection,
    predictions_paths: Sequence[Path | str] | Path | str,
    manifest_path: Path | str,
) -> Dict[str, Any]:
    """Importa le trascrizioni restituite da Vertex AI Multimodal Batch Vision in modalità append-only."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if isinstance(predictions_paths, (Path, str)):
        p = Path(predictions_paths)
        pred_files = sorted(p.glob("predictions*.jsonl")) if p.is_dir() else [p]
    else:
        pred_files = [Path(x) for x in predictions_paths]

    by_book_pages: Dict[str, List[Dict[str, Any]]] = {}
    by_book_meta: Dict[str, Dict[str, Any]] = {}
    seen_bids: set[str] = set()
    lines_read = 0
    lines_failed = 0
    in_tok = 0
    out_tok = 0

    for pf in pred_files:
        with pf.open("r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                lines_read += 1
                try:
                    obj = json.loads(s)
                    resp = obj.get("response") if isinstance(obj, Mapping) else obj
                    if not isinstance(resp, Mapping) or "candidates" not in resp:
                        lines_failed += 1
                        continue
                    usage = resp.get("usageMetadata") or {}
                    in_tok += int(usage.get("promptTokenCount") or 0)
                    out_tok += int(usage.get("candidatesTokenCount") or 0)
                    txt = resp["candidates"][0]["content"]["parts"][0]["text"]
                    cleaned_txt = _strip_json_fences(txt)
                    try:
                        parsed = json.loads(cleaned_txt)
                    except json.JSONDecodeError:
                        parsed = json.loads(_repair_json_latex_escapes(cleaned_txt))
                    bid = str(parsed.get("batch_id") or "").strip()
                    pages = list(parsed.get("pages") or [])
                    if bid not in manifest:
                        lines_failed += 1
                        continue
                    seen_bids.add(bid)
                    meta = manifest[bid]
                    req_pnums = meta["page_numbers"]
                    if len(pages) == len(req_pnums):
                        for idx, p_obj in enumerate(pages):
                            if isinstance(p_obj, dict):
                                p_obj["pdf_page"] = int(req_pnums[idx])
                    t_key = meta["title"]
                    by_book_meta[t_key] = meta
                    by_book_pages.setdefault(t_key, []).extend(pages)
                except Exception:
                    lines_failed += 1

    books_summary: List[Dict[str, Any]] = []
    tot_inserted = 0
    tot_superseded = 0
    for t_key, pages in by_book_pages.items():
        meta = by_book_meta[t_key]
        should_supersede = meta["defect_category"] in {
            "buco_b_cultura_in_ita5_or_silent_blank",
            "buco_c_under_extracted_pdf",
        }
        res = ingest_ocr_pages_append_only(
            conn,
            title=t_key,
            source_path=meta["source_path"],
            source_kind="vertex_vision_batch",
            total_pages=meta["total_pages"],
            transcribed_pages=pages,
            supersede_under_extracted=should_supersede,
        )
        tot_inserted += int(res["blocks_inserted"])
        tot_superseded += int(res["blocks_superseded"])
        books_summary.append({"title": t_key, **res})

    missing_batches = [manifest[k] for k in manifest if k not in seen_bids]
    batch_usd = (in_tok / 1e6) * 0.15 + (out_tok / 1e6) * 1.25
    return {
        "lines_read": lines_read,
        "lines_failed": lines_failed,
        "batches_expected": len(manifest),
        "batches_received": len(seen_bids),
        "missing_batches_count": len(missing_batches),
        "missing_batches": missing_batches,
        "books_ingested": len(books_summary),
        "total_blocks_inserted": tot_inserted,
        "total_blocks_superseded": tot_superseded,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "batch_eur": round(batch_usd * 0.92, 4),
    }


def run_vision_ocr_on_document(
    conn: sqlite3.Connection,
    *,
    doc_path: Path,
    page_numbers: Sequence[int],
    title: Optional[str] = None,
    pages_per_call: int = 4,
    dpi: int = 150,
    supersede_under_extracted: bool = False,
    workers: int = 1,
    vision_fn: Optional[
        Callable[[Sequence[Tuple[int, bytes]], str], Tuple[List[Dict[str, Any]], int, int]]
    ] = None,
) -> Dict[str, Any]:
    """Esegue OCR end-to-end (render immagine temporanea -> Vision -> append-only in `blocks`)."""
    doc_path = Path(doc_path)
    eff_title = title or doc_path.stem
    tot_pages = count_document_pages(doc_path)
    rendered = render_pages_to_jpeg_bytes(doc_path, page_numbers, dpi=dpi)

    all_transcribed: List[Dict[str, Any]] = []
    tot_in_tok = 0
    tot_out_tok = 0
    step = max(1, min(int(pages_per_call), 6))
    batches = [rendered[idx : idx + step] for idx in range(0, len(rendered), step)]

    if int(workers) > 1 and vision_fn is None and len(batches) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(int(workers), 8, len(batches))) as pool:
            results = list(
                pool.map(lambda b: transcribe_pages_via_vertex_vision(b, book_title=eff_title), batches)
            )
        for pages_out, in_tok, out_tok in results:
            tot_in_tok += in_tok
            tot_out_tok += out_tok
            all_transcribed.extend(pages_out)
    else:
        for batch in batches:
            if vision_fn is not None:
                pages_out, in_tok, out_tok = vision_fn(batch, eff_title)
            else:
                pages_out, in_tok, out_tok = transcribe_pages_via_vertex_vision(
                    batch,
                    book_title=eff_title,
                )
            tot_in_tok += in_tok
            tot_out_tok += out_tok
            all_transcribed.extend(pages_out)

    ingest_res = ingest_ocr_pages_append_only(
        conn,
        title=eff_title,
        source_path=str(doc_path),
        source_kind="vertex_vision_ocr",
        total_pages=tot_pages,
        transcribed_pages=all_transcribed,
        supersede_under_extracted=supersede_under_extracted,
    )
    usd = (tot_in_tok / 1e6) * 0.30 + (tot_out_tok / 1e6) * 2.50
    return {
        **ingest_res,
        "pages_requested": list(page_numbers),
        "pages_transcribed": len(all_transcribed),
        "input_tokens": tot_in_tok,
        "output_tokens": tot_out_tok,
        "estimated_eur": round(usd * 0.92, 5),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OCR append-only PDF/DjVu per i volumi muti di resuscipack.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--doc", type=Path, default=None, help="Percorso PDF o DjVu in sola lettura")
    parser.add_argument("--pages", type=str, default="1-4", help="Intervallo pagine 1-based, es. 65-72")
    parser.add_argument("--title", type=str, default=None)
    parser.add_argument("--list-gcs-matches", action="store_true", help="Elenca i volumi già pronti su GCS output/")
    args = parser.parse_args(argv)

    if args.list_gcs_matches:
        res = list_gcs_ocr_matches()
        print(json.dumps({"count": len(res), "matches": res}, indent=2, ensure_ascii=False))
        return 0

    if args.doc is None:
        parser.error("Specifica --doc <file.pdf|file.djvu> oppure --list-gcs-matches")

    tot = count_document_pages(args.doc)
    pnums = parse_page_spec(args.pages, tot)
    conn = init_corpus_db(args.db)
    try:
        res = run_vision_ocr_on_document(
            conn,
            doc_path=args.doc,
            page_numbers=pnums,
            title=args.title,
        )
    finally:
        conn.close()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
