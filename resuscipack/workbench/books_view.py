"""Loader e renderer editoriale per i *Nuovi Libri* continui e i 30 quesiti reali OFA (TASK-UI-02)."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..books.author_engine import DEFAULT_BOOKS_DIR, _clean_book_title_for_citation
from ..books.catalog import VOL1_CHAPTER_SPECS, VOL2_CHAPTER_SPECS
from ..curriculum.dag import DEFAULT_DAG_PATH, load_unified_dag
from ..curriculum.drills_sympy import PROOF_RUBRICS, generate_drill_set

VOLUMES_META: dict[str, dict[str, Any]] = {
    "vol1_ofa": {
        "volume_id": "vol1_ofa",
        "short_title": "Volume I",
        "title": "Dall'Ovvio al Simbolo",
        "subtitle": "Dalle radici del contare e dell'uguale all'ingresso universitario",
        "specs": VOL1_CHAPTER_SPECS,
    },
    "vol2_secai": {
        "volume_id": "vol2_secai",
        "short_title": "Volume II",
        "title": "I Ponti Nascosti di SecAI",
        "subtitle": "Dal discreto e dal calcolo fino a probabilità, crittografia, memoria e sicurezza web",
        "specs": VOL2_CHAPTER_SPECS,
    },
}

_PROOF_RUBRIC_META: dict[str, dict[str, str]] = {
    "sqrt2_irrational": {
        "id": "sqrt2_irrational",
        "title": "Dimostrazione a libro chiuso: irrazionalità della radice quadrata di 2",
        "prompt": "Dimostra per assurdo che √2 non è razionale esplicitando l'ipotesi di frazione ridotta ai minimi termini (MCD(a, b) = 1), la parità di a, quella di b e la contraddizione finale.",
    },
    "induction_sum_n": {
        "id": "induction_sum_n",
        "title": "Dimostrazione per induzione: somma dei primi n interi naturali",
        "prompt": "Dimostra che 1 + 2 + … + n = n(n + 1)/2 verificando il caso base, dichiarando l'ipotesi induttiva e completando il passo algebrico per n + 1.",
    },
    "hash_vs_encryption": {
        "id": "hash_vs_encryption",
        "title": "Confronto formale: funzione di hash e cifratura reversibile",
        "prompt": "Spiega la differenza tra funzione di hash unidirezionale a taglia fissa e cifratura invertibile tramite chiave, richiamando il principio dei cassetti per le collisioni.",
    },
}

_GRAPH_INVARIANT_META: dict[str, dict[str, Any]] = {
    "abs_shifted_log": {
        "id": "abs_shifted_log",
        "title": "Invarianti analitici della funzione y = |ln(x - 2)| + 1",
        "prompt": "Determina dominio, asintoto verticale, punto angoloso e andamento dei rami senza generare grafici preconfezionati.",
        "fields": [
            {"name": "domain_lower_bound", "label": "Estremo inferiore del dominio (x > …)", "placeholder": "2"},
            {"name": "vertical_asymptote_x", "label": "Asintoto verticale (x = …)", "placeholder": "2"},
            {"name": "cusp_x", "label": "Ascissa della cuspide", "placeholder": "3"},
            {"name": "cusp_y", "label": "Ordinata della cuspide", "placeholder": "1"},
            {"name": "probe_y_at_2_plus_e", "label": "Valore di y per x = 2 + e", "placeholder": "2"},
            {"name": "left_branch", "label": "Monotonia prima della cuspide", "options": ["decrescente", "crescente"]},
            {"name": "right_branch", "label": "Monotonia dopo la cuspide", "options": ["crescente", "decrescente"]},
        ],
    }
}

_NOTE_DEF_RE = re.compile(
    r"^\[\^(\d+)\]:\s*\[\s*block_pk\s*=\s*(\d+)\s*\|\s*block_uid\s*=\s*([A-Za-z0-9_:-]+)\s*\]\s*"
    r"«(.+?)»\s*(?:—|--|-)\s*(.+)$",
    flags=re.MULTILINE,
)
_INLINE_FN_RE = re.compile(r"\[\^(\d+)\](?!:)")
_IMG_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")


def _clean_source_label(raw_label: str) -> str:
    txt = str(raw_label or "").strip()
    txt = re.sub(r"\s*-\s*libgen(?:\.lc)?\b", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s*\(\s*,\s*", " (", txt)
    return " ".join(txt.split()).strip()


def _strip_internal_backtick_tags(text: str) -> str:
    """Rimuove sigle interne tecniche dalle note editoriali esposte al lettore."""
    cleaned = re.sub(r"\s*\(\s*`(?:drill_[a-z0-9_]+|[a-z0-9_]+)`\s*\)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(\s*`[A-Za-z0-9_.-]+`\s*\)", "", cleaned)
    return " ".join(cleaned.split()).strip()


def _parse_apparatus_sections(apparatus_md: str) -> dict[str, Any]:
    """Estrae le 3 sezioni dell'apparato delle fonti separandole senza codici interni visibili."""
    current = ""
    verificato_lines: list[str] = []
    ricostruzione_items: list[str] = []
    esercizi_items: list[str] = []

    for raw in apparatus_md.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            heading_low = line.lower()
            if "verificato" in heading_low:
                current = "verificato"
            elif "ricostruzione" in heading_low:
                current = "ricostruzione"
            elif "esercizi" in heading_low:
                current = "esercizi"
            else:
                current = ""
            continue
        if not line:
            continue
        if current == "verificato":
            verificato_lines.append(line)
        elif current == "ricostruzione" and line.startswith("- "):
            item = _strip_internal_backtick_tags(line[2:].strip())
            if item:
                ricostruzione_items.append(item)
        elif current == "esercizi" and line.startswith("- "):
            body_item = line[2:].strip()
            if "palestra simbolica" in body_item.lower():
                continue
            item = _strip_internal_backtick_tags(body_item)
            if item:
                esercizi_items.append(item)

    footnotes: list[dict[str, Any]] = []
    for fm in _NOTE_DEF_RE.finditer("\n".join(verificato_lines)):
        footnotes.append(
            {
                "num": int(fm.group(1)),
                "block_pk": int(fm.group(2)),
                "block_uid": fm.group(3).strip(),
                "quote": fm.group(4).strip(),
                "source_label": _clean_source_label(fm.group(5).strip()),
            }
        )

    return {
        "footnotes": footnotes,
        "ricostruzione": ricostruzione_items,
        "esercizi_originali": esercizi_items,
    }


def _format_inline_book(text: str, fn_by_num: Mapping[int, Mapping[str, Any]]) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)

    def _replace_fn(m: re.Match[str]) -> str:
        num = int(m.group(1))
        info = fn_by_num.get(num)
        if not info:
            return f'<sup class="fn-missing">{num}</sup>'
        quote_attr = html.escape(str(info["quote"]), quote=True)
        src_attr = html.escape(str(info["source_label"]), quote=True)
        return (
            f'<button type="button" class="fn-trigger" '
            f'data-note="{num}" data-block-pk="{int(info["block_pk"])}" '
            f'data-quote="{quote_attr}" title="{src_attr}" '
            f'aria-label="Apri pagina originale della nota {num}: {src_attr}">'
            f"{num}</button>"
        )

    return _INLINE_FN_RE.sub(_replace_fn, escaped)


def render_book_markdown_to_html(
    markdown_body: str,
    fn_by_num: Mapping[int, Mapping[str, Any]],
) -> str:
    """Compila il corpo di un capitolo continuo in HTML semantico compatibile con KaTeX."""
    math_tokens: list[str] = []

    def _stash_math(match: re.Match[str]) -> str:
        idx = len(math_tokens)
        math_tokens.append(html.escape(match.group(0), quote=False))
        return f"@@BOOK_MATH_{idx}@@"

    protected = re.sub(r"\$\$.*?\$\$", _stash_math, markdown_body, flags=re.DOTALL)
    protected = re.sub(r"(?<!\$)\$(?!\$)([^\$\n]+?)(?<!\$)\$(?!\$)", _stash_math, protected)

    lines = protected.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_table = False
    skip_first_h1 = True
    skip_next_italic_caption: str | None = None

    def _close_blocks() -> None:
        nonlocal in_ul, in_ol, in_table
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            _close_blocks()
            continue

        if skip_next_italic_caption is not None:
            if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
                inner = stripped[1:-1].strip()
                if inner == skip_next_italic_caption or inner[:36] == skip_next_italic_caption[:36]:
                    skip_next_italic_caption = None
                    continue
            skip_next_italic_caption = None

        if stripped.startswith("# ") and skip_first_h1:
            skip_first_h1 = False
            skip_next_italic_caption = "__CHAPTER_SUBTITLE__"
            continue

        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2 and out == []:
            # Salta la riga del sottotitolo duplicata sotto `# Capitolo N`, già resa nell'<header>
            continue

        img_match = _IMG_LINE_RE.match(stripped)
        if img_match:
            _close_blocks()
            alt_text = img_match.group(1).strip()
            raw_src = img_match.group(2).strip()
            filename = Path(raw_src).name
            safe_src = html.escape(f"/books-assets/{filename}", quote=True)
            safe_alt = html.escape(alt_text or "Diagramma geometrico del capitolo", quote=True)
            out.append(
                f'<figure class="book-figure">'
                f'<img src="{safe_src}" alt="{safe_alt}" width="760" height="320" loading="lazy">'
                f"</figure>"
            )
            skip_next_italic_caption = alt_text
            continue

        if stripped.startswith("## "):
            _close_blocks()
            out.append(f"<h2>{_format_inline_book(stripped[3:].strip(), fn_by_num)}</h2>")
            continue

        if stripped.startswith("### "):
            _close_blocks()
            out.append(f"<h3>{_format_inline_book(stripped[4:].strip(), fn_by_num)}</h3>")
            continue

        if stripped.startswith("> "):
            _close_blocks()
            out.append(f"<blockquote><p>{_format_inline_book(stripped[2:].strip(), fn_by_num)}</p></blockquote>")
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                _close_blocks()
                in_table = True
                out.append('<table class="book-table"><tbody>')
            row_html = "".join(f"<td>{_format_inline_book(c, fn_by_num)}</td>" for c in cells)
            out.append(f"<tr>{row_html}</tr>")
            continue
        elif in_table:
            out.append("</tbody></table>")
            in_table = False

        if stripped.startswith("- "):
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append('<ul class="book-list">')
                in_ul = True
            out.append(f"<li>{_format_inline_book(stripped[2:].strip(), fn_by_num)}</li>")
            continue

        m_ol = re.match(r"^(\d+)[\.\)]\s+(.+)$", stripped)
        if m_ol:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append('<ol class="book-list">')
                in_ol = True
            out.append(f"<li>{_format_inline_book(m_ol.group(2).strip(), fn_by_num)}</li>")
            continue

        _close_blocks()
        out.append(f"<p>{_format_inline_book(stripped, fn_by_num)}</p>")

    _close_blocks()
    compiled = "\n".join(out)
    for idx, expr in enumerate(math_tokens):
        compiled = compiled.replace(f"@@BOOK_MATH_{idx}@@", expr)
    return compiled


def _all_ordered_chapters(books_dir: Path) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    for vid in ("vol1_ofa", "vol2_secai"):
        vmeta = VOLUMES_META[vid]
        vdir = books_dir / vid
        for sp in vmeta["specs"]:
            ch_file = vdir / f"{sp.chapter_number:02d}_{sp.slug}.md"
            status = "pubblicato"
            title = sp.title
            subtitle = sp.subtitle
            footnotes_count = 0
            if ch_file.exists():
                raw = ch_file.read_text(encoding="utf-8")
                fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, flags=re.DOTALL)
                if fm_match:
                    meta = yaml.safe_load(fm_match.group(1)) or {}
                    status = str(meta.get("stato", "pubblicato"))
                    title = str(meta.get("titolo") or sp.title)
                    subtitle = str(meta.get("sottotitolo") or sp.subtitle)
                    footnotes_count = len(meta.get("fonti") or [])
            ordered.append(
                {
                    "volume_id": vid,
                    "volume_short_title": vmeta["short_title"],
                    "volume_title": vmeta["title"],
                    "chapter_number": sp.chapter_number,
                    "slug": sp.slug,
                    "title": title,
                    "subtitle": subtitle,
                    "status": status,
                    "footnotes_count": footnotes_count,
                    "drill_keys_count": len(sp.drill_keys),
                    "url": f"/libro/{vid}/{sp.slug}",
                }
            )
    return ordered


def list_volumes_and_chapters(books_dir: Path | str = DEFAULT_BOOKS_DIR) -> dict[str, Any]:
    """Restituisce i 2 volumi e tutti i 20 capitoli ordinati senza troncamenti."""
    bdir = Path(books_dir)
    all_chapters = _all_ordered_chapters(bdir)
    volumes: list[dict[str, Any]] = []
    for vid in ("vol1_ofa", "vol2_secai"):
        vmeta = VOLUMES_META[vid]
        chapters = [ch for ch in all_chapters if ch["volume_id"] == vid]
        volumes.append(
            {
                "volume_id": vid,
                "short_title": vmeta["short_title"],
                "title": vmeta["title"],
                "subtitle": vmeta["subtitle"],
                "chapters": chapters,
            }
        )
    return {
        "volumes": volumes,
        "total_chapters": len(all_chapters),
    }


def _find_chapter_spec(volume_id: str, slug: str):
    if volume_id not in VOLUMES_META:
        return None
    for sp in VOLUMES_META[volume_id]["specs"]:
        if sp.slug == slug:
            return sp
    return None


def load_book_chapter(
    volume_id: str,
    slug: str,
    *,
    books_dir: Path | str = DEFAULT_BOOKS_DIR,
    dag_payload: Mapping[str, Any] | None = None,
    seed: int = 42,
) -> dict[str, Any] | None:
    """Carica un capitolo completo per /libro e /api/books/<volume_id>/<slug>."""
    if volume_id not in VOLUMES_META:
        return None
    safe_slug = Path(str(slug)).name
    spec = _find_chapter_spec(volume_id, safe_slug)
    if spec is None:
        return None

    bdir = Path(books_dir)
    ch_path = bdir / volume_id / f"{spec.chapter_number:02d}_{spec.slug}.md"
    if not ch_path.exists():
        return None

    raw = ch_path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = raw
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, flags=re.DOTALL)
    if fm_match:
        loaded = yaml.safe_load(fm_match.group(1)) or {}
        if isinstance(loaded, dict):
            meta = loaded
        body = fm_match.group(2)

    parts = re.split(r"^##\s+Apparato delle fonti\b.*$", body, maxsplit=1, flags=re.MULTILINE)
    prose_md = parts[0].strip()
    apparatus_md = parts[1].strip() if len(parts) > 1 else ""

    apparatus = _parse_apparatus_sections(apparatus_md)
    footnotes = apparatus["footnotes"]
    if not footnotes and isinstance(meta.get("fonti"), list):
        footnotes = [
            {
                "num": idx + 1,
                "block_pk": int(f["block_pk"]),
                "block_uid": str(f.get("block_uid", "")),
                "quote": str(f.get("citazione", "")),
                "source_label": "Fonte verificata",
            }
            for idx, f in enumerate(meta["fonti"])
        ]

    fn_by_num = {fn["num"]: fn for fn in footnotes}
    rendered_html = render_book_markdown_to_html(prose_md, fn_by_num)

    dag = dag_payload or load_unified_dag(DEFAULT_DAG_PATH)
    nodes = dag.get("nodes", {}) if isinstance(dag, Mapping) else {}
    node_by_drill: dict[str, str] = {}
    for nid in spec.node_ids:
        node = nodes.get(nid)
        if isinstance(node, Mapping) and node.get("drill_key"):
            node_by_drill[str(node["drill_key"])] = nid
    fallback_node_id = spec.node_ids[0] if spec.node_ids else "numeri.quantita"

    drills: list[dict[str, Any]] = []
    for idx_d, dk in enumerate(spec.drill_keys):
        nid = node_by_drill.get(dk, fallback_node_id)
        node_info = nodes.get(nid, {})
        items = generate_drill_set(nid, dk, count=2, seed=seed + idx_d)
        topic_title = str(node_info.get("title") or "Verifica simbolica")
        for item in items:
            enriched = dict(item)
            enriched["node_id"] = nid
            enriched["topic_title"] = topic_title
            drills.append(enriched)

    all_chapters = _all_ordered_chapters(bdir)
    cur_idx = next(
        (i for i, ch in enumerate(all_chapters) if ch["volume_id"] == volume_id and ch["slug"] == spec.slug),
        -1,
    )
    prev_ch = all_chapters[cur_idx - 1] if cur_idx > 0 else None
    next_ch = all_chapters[cur_idx + 1] if 0 <= cur_idx < len(all_chapters) - 1 else None

    vmeta = VOLUMES_META[volume_id]
    proof_rubric = _PROOF_RUBRIC_META.get(spec.proof_rubric_id) if spec.proof_rubric_id else None
    if proof_rubric and spec.proof_rubric_id in PROOF_RUBRICS:
        proof_rubric = {
            **proof_rubric,
            "node_id": fallback_node_id,
            "lemmas_count": len(PROOF_RUBRICS[spec.proof_rubric_id]),
        }
    graph_invariant = _GRAPH_INVARIANT_META.get(spec.graph_invariant_id) if spec.graph_invariant_id else None
    if graph_invariant:
        graph_invariant = {**graph_invariant, "node_id": fallback_node_id}

    return {
        "volume_id": volume_id,
        "volume_short_title": vmeta["short_title"],
        "volume_title": vmeta["title"],
        "chapter_number": spec.chapter_number,
        "slug": spec.slug,
        "title": str(meta.get("titolo") or spec.title),
        "subtitle": str(meta.get("sottotitolo") or spec.subtitle),
        "status": str(meta.get("stato") or "pubblicato"),
        "html": rendered_html,
        "footnotes": footnotes,
        "ricostruzione": apparatus["ricostruzione"],
        "esercizi_originali": apparatus["esercizi_originali"],
        "drills": drills,
        "proof_rubric": proof_rubric,
        "graph_invariant": graph_invariant,
        "prev_chapter": prev_ch,
        "next_chapter": next_ch,
        "has_ofa_bank": volume_id == "vol1_ofa",
    }


def load_ofa_30_questions(books_dir: Path | str = DEFAULT_BOOKS_DIR) -> dict[str, Any]:
    """Carica i 30 quesiti reali d'ingresso/OFA pulendo i titoli per la vista lettore."""
    q_path = Path(books_dir) / "vol1_ofa" / "ofa_30_quesiti_reali.json"
    if not q_path.exists():
        return {"count": 0, "questions": []}
    raw = json.loads(q_path.read_text(encoding="utf-8"))
    out_questions: list[dict[str, Any]] = []
    for idx, q in enumerate(raw.get("questions", []), start=1):
        out_questions.append(
            {
                "index": idx,
                "block_pk": int(q["block_pk"]),
                "book_title": _clean_book_title_for_citation(str(q.get("book_title", ""))),
                "page": q.get("page"),
                "question_excerpt": str(q.get("question_excerpt", "")).strip(),
                "source_tag": "Test CISIA / ingresso universitario"
                if "Test" in str(q.get("book_title", ""))
                else "Testo storico del corpus",
            }
        )
    return {
        "count": len(out_questions),
        "questions": out_questions,
    }


__all__ = [
    "VOLUMES_META",
    "list_volumes_and_chapters",
    "load_book_chapter",
    "load_ofa_30_questions",
    "render_book_markdown_to_html",
]
