"""Parser e renderer HTML/KaTeX per le schede studio v3 (`data/cards/<node_id>.md`)."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CARDS_DIR = Path(__file__).resolve().parents[2] / "data" / "cards"

_NOTE_DEF_RE = re.compile(
    r"^\[\^(\d+)\]:\s*\[\s*block_pk\s*=\s*(\d+)\s*\|\s*block_uid\s*=\s*([A-Za-z0-9_:-]+)\s*\]\s*"
    r"«(.+)»\s*(?:—|--|-)\s*(.+)$",
    flags=re.MULTILINE,
)
_INLINE_FN_RE = re.compile(r"\[\^(\d+)\](?!:)")


def list_available_card_ids(cards_dir: Path | str = DEFAULT_CARDS_DIR) -> set[str]:
    p = Path(cards_dir)
    if not p.exists():
        return set()
    return {f.stem for f in p.glob("*.md") if not f.name.startswith("_")}


def load_card(node_id: str, cards_dir: Path | str = DEFAULT_CARDS_DIR) -> dict[str, Any] | None:
    """Carica una scheda `.md` per `node_id` restituendo metadati, note strutturate e HTML semantico."""
    safe_id = Path(str(node_id)).name
    card_path = Path(cards_dir) / f"{safe_id}.md"
    if not card_path.exists():
        return None

    raw_text = card_path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = raw_text
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw_text, flags=re.DOTALL)
    if m:
        loaded = yaml.safe_load(m.group(1)) or {}
        if isinstance(loaded, dict):
            meta = loaded
        body = m.group(2)

    footnotes: list[dict[str, Any]] = []
    fn_by_num: dict[int, dict[str, Any]] = {}
    for fm in _NOTE_DEF_RE.finditer(body):
        num = int(fm.group(1))
        entry = {
            "num": num,
            "block_pk": int(fm.group(2)),
            "block_uid": fm.group(3).strip(),
            "quote": fm.group(4).strip(),
            "source_label": fm.group(5).strip(),
        }
        footnotes.append(entry)
        fn_by_num[num] = entry

    # Rimuovi la sezione finale `## Note` dal corpo principale perché viene renderizzata come lista interattiva dedicata
    body_without_notes = re.sub(
        r"^##\s+Note[ \t]*\n.*$",
        "",
        body,
        flags=re.MULTILINE | re.DOTALL,
    ).strip()

    rendered_html = render_card_markdown_to_html(body_without_notes, fn_by_num)
    return {
        "id": meta.get("id", safe_id),
        "title": meta.get("titolo", safe_id),
        "level": meta.get("livello", ""),
        "status": meta.get("stato", "validata_auto"),
        "updated_at": str(meta.get("aggiornato", "")),
        "prerequisites": list(meta.get("prerequisiti") or []),
        "wrong_book_meta": meta.get("libro_sbagliato"),
        "footnotes": footnotes,
        "raw_markdown": raw_text,
        "html": rendered_html,
    }


def render_card_markdown_to_html(markdown_body: str, fn_by_num: dict[int, dict[str, Any]]) -> str:
    """Converte il Markdown della scheda in HTML sicuro preservando blocchi LaTeX (`$$...$$`, `$...$`)
    per KaTeX, trasformando le etichette `[Definizione|Assioma|Teorema|Convenzione]` in badge e
    i pedici `[^n]` in pulsanti cliccabili collegati al Lettore del Libro Vero."""
    math_placeholders: list[str] = []

    def _stash_math(match: re.Match[str]) -> str:
        idx = len(math_placeholders)
        math_placeholders.append(html.escape(match.group(0), quote=False))
        return f"@@MATH_TOKEN_{idx}@@"

    # Proteggi prima display math $$...$$, poi inline math $...$
    protected = re.sub(r"\$\$.*?\$\$", _stash_math, markdown_body, flags=re.DOTALL)
    protected = re.sub(r"(?<!\$)\$(?!\$)([^\$\n]+?)(?<!\$)\$(?!\$)", _stash_math, protected)

    lines = protected.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_table = False
    in_wrong_book_section = False

    def _close_lists() -> None:
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
            _close_lists()
            continue

        if stripped.startswith("## "):
            _close_lists()
            if in_wrong_book_section:
                out.append("</div>")
                in_wrong_book_section = False
            heading_text = stripped[3:].strip()
            if "libro sbagliato" in heading_text.lower():
                in_wrong_book_section = True
                out.append('<div class="wrong-book-callout">')
            out.append(f"<h2>{_format_inline(heading_text, fn_by_num)}</h2>")
            continue

        if stripped.startswith("### "):
            _close_lists()
            heading_text = stripped[4:].strip()
            out.append(f"<h3>{_format_inline(heading_text, fn_by_num)}</h3>")
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                _close_lists()
                in_table = True
                out.append('<table class="card-table"><tbody>')
            row_html = "".join(f"<td>{_format_inline(c, fn_by_num)}</td>" for c in cells)
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
                out.append('<ul class="card-list">')
                in_ul = True
            item_body = stripped[2:].strip()
            out.append(f"<li>{_format_inline(item_body, fn_by_num)}</li>")
            continue

        m_ol = re.match(r"^(\d+)[\.\)]\s+(.+)$", stripped)
        if m_ol:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append('<ol class="card-list">')
                in_ol = True
            out.append(f"<li>{_format_inline(m_ol.group(2), fn_by_num)}</li>")
            continue

        _close_lists()
        out.append(f"<p>{_format_inline(stripped, fn_by_num)}</p>")

    _close_lists()
    if in_wrong_book_section:
        out.append("</div>")

    joined = "\n".join(out)
    for idx, math_expr in enumerate(math_placeholders):
        joined = joined.replace(f"@@MATH_TOKEN_{idx}@@", math_expr)
    return joined


def _format_inline(text: str, fn_by_num: dict[int, dict[str, Any]]) -> str:
    escaped = html.escape(text, quote=False)

    # Badge per [Definizione], [Assioma], [Teorema], [Convenzione]
    escaped = re.sub(
        r"\*\*\[(Definizione|Assioma|Teorema|Convenzione)\]\*\*",
        lambda m: f'<span class="stmt-badge stmt-{m.group(1).lower()}">{m.group(1)}</span>',
        escaped,
    )
    # Code inline `...`
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    # Bold **...** e Italic *...*
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)

    # Pedici interattivi [^n]
    def _replace_fn(m: re.Match[str]) -> str:
        num = int(m.group(1))
        info = fn_by_num.get(num)
        if not info:
            return f'<sup class="fn-missing">[^{num}]</sup>'
        quote_attr = html.escape(info["quote"], quote=True)
        src_attr = html.escape(info["source_label"], quote=True)
        return (
            f'<button type="button" class="fn-trigger" '
            f'data-note="{num}" data-block-pk="{info["block_pk"]}" '
            f'data-block-uid="{info["block_uid"]}" '
            f'data-quote="{quote_attr}" title="{src_attr}">'
            f"[^{num}]</button>"
        )

    escaped = _INLINE_FN_RE.sub(_replace_fn, escaped)
    return escaped
