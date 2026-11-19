"""Risolutore di figure reali Baidu (`data/corpus_figures/`) e generatore editoriale di diagrammi SVG
controllati per i *Nuovi Libri* (ADR-0004, TASK-BOOK-01)."""

from __future__ import annotations

import html
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_FIGURES_DIR = Path(__file__).resolve().parents[2] / "data" / "corpus_figures"
DEFAULT_ASSETS_DIR = Path(__file__).resolve().parents[2] / "data" / "books" / "assets"

# Palette editoriale sobria (carta calda, inchiostro antracite, blu ardesia, ocra)
_PAPER = "#faf7f2"
_INK = "#1f2421"
_MUTED = "#5d645f"
_GRID = "#d9d2c5"
_BLUE = "#2c4f7c"
_OCHRE = "#b86b2b"
_TEAL = "#2d6a5b"

CONTROLLED_SVG_IDS: Tuple[str, ...] = (
    "balance_and_number_line",
    "marconi_tolerance_corridor",
    "positional_base_grid",
    "area_distributive_grid",
    "parabola_focal_rays",
    "unit_circle_trig",
    "series_conjunction_circuit",
    "probability_tree_bayes",
)


@dataclass(frozen=True)
class FigureAsset:
    """Risorsa visiva verificata inseribile nella prosa continua di un capitolo."""

    kind: str  # "corpus_figure" | "svg_diagram"
    path: Path
    rel_path: str
    caption: str
    diagram_id: Optional[str] = None
    block_pk: Optional[int] = None
    book_title: Optional[str] = None
    page: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "rel_path": self.rel_path,
            "caption": self.caption,
            "diagram_id": self.diagram_id,
            "block_pk": self.block_pk,
            "book_title": self.book_title,
            "page": self.page,
        }


def _svg_wrapper(*, title: str, width: int, height: int, body: str) -> str:
    safe_title = html.escape(title, quote=True)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-labelledby="svg-title">\n'
        f'  <title id="svg-title">{safe_title}</title>\n'
        f"  <style>\n"
        f'    .title {{ font: 600 15px Georgia, "Times New Roman", serif; fill: {_INK}; }}\n'
        f'    .label {{ font: 500 13px Georgia, "Times New Roman", serif; fill: {_INK}; }}\n'
        f'    .math {{ font: italic 600 14px Georgia, "Times New Roman", serif; fill: {_BLUE}; }}\n'
        f'    .muted {{ font: 400 11.5px -apple-system, BlinkMacSystemFont, sans-serif; fill: {_MUTED}; }}\n'
        f"  </style>\n"
        f'  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="8" '
        f'fill="{_PAPER}" stroke="{_GRID}" stroke-width="1.5"/>\n'
        f"{body}\n"
        f"</svg>\n"
    )


def _svg_balance_and_number_line(title: str) -> str:
    # Pannello sinistro: corrispondenza biunivoca e retta discreta; destro: bilancia simmetrica (=)
    ticks = []
    for idx in range(6):
        x = 58 + idx * 50
        ticks.append(
            f'  <line x1="{x}" y1="168" x2="{x}" y2="180" stroke="{_INK}" stroke-width="1.5"/>\n'
            f'  <text x="{x}" y="200" text-anchor="middle" class="label">{idx}</text>'
        )
        if idx < 4:
            cx_top = 83 + idx * 45
            cx_bot = 58 + (idx + 1) * 50
            ticks.append(
                f'  <circle cx="{cx_top}" cy="86" r="10" fill="{_OCHRE}" fill-opacity="0.18" stroke="{_OCHRE}" stroke-width="1.5"/>\n'
                f'  <line x1="{cx_top}" y1="96" x2="{cx_bot}" y2="160" stroke="{_BLUE}" stroke-width="1.2" stroke-dasharray="4 3"/>'
            )
    left_svg = "\n".join(ticks)
    body = (
        f'  <text x="190" y="34" text-anchor="middle" class="title">Contare per corrispondenza e ordine</text>\n'
        f'  <line x1="360" y1="26" x2="360" y2="234" stroke="{_GRID}" stroke-width="1.2"/>\n'
        f'  <line x1="40" y1="174" x2="335" y2="174" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <polygon points="335,174 326,169 326,179" fill="{_INK}"/>\n'
        f"{left_svg}\n"
        f'  <text x="188" y="226" text-anchor="middle" class="muted">Ogni passo a destra aggiunge un successore (+1)</text>\n'
        f'  <text x="540" y="34" text-anchor="middle" class="title">L’uguale come equilibrio di bilancia</text>\n'
        f'  <line x1="540" y1="74" x2="540" y2="186" stroke="{_INK}" stroke-width="2.2"/>\n'
        f'  <polygon points="522,196 558,196 540,182" fill="{_INK}"/>\n'
        f'  <line x1="422" y1="94" x2="658" y2="94" stroke="{_BLUE}" stroke-width="3"/>\n'
        f'  <circle cx="540" cy="94" r="5" fill="{_OCHRE}"/>\n'
        f'  <line x1="440" y1="94" x2="424" y2="144" stroke="{_MUTED}" stroke-width="1.2"/>\n'
        f'  <line x1="440" y1="94" x2="456" y2="144" stroke="{_MUTED}" stroke-width="1.2"/>\n'
        f'  <rect x="408" y="144" width="64" height="10" rx="3" fill="{_BLUE}" fill-opacity="0.2" stroke="{_BLUE}"/>\n'
        f'  <text x="440" y="132" text-anchor="middle" class="math">3 + 4</text>\n'
        f'  <line x1="640" y1="94" x2="624" y2="144" stroke="{_MUTED}" stroke-width="1.2"/>\n'
        f'  <line x1="640" y1="94" x2="656" y2="144" stroke="{_MUTED}" stroke-width="1.2"/>\n'
        f'  <rect x="608" y="144" width="64" height="10" rx="3" fill="{_OCHRE}" fill-opacity="0.2" stroke="{_OCHRE}"/>\n'
        f'  <text x="640" y="132" text-anchor="middle" class="math">x + 2</text>\n'
        f'  <text x="540" y="226" text-anchor="middle" class="muted">Simmetria e invarianti: stessa operazione sui due piatti</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_marconi_tolerance_corridor(title: str) -> str:
    body = (
        f'  <text x="360" y="34" text-anchor="middle" class="title">Corridoio di tolleranza simmetrica: |x - x₀| &lt; δ</text>\n'
        f'  <rect x="230" y="74" width="260" height="88" fill="{_BLUE}" fill-opacity="0.11" stroke="none"/>\n'
        f'  <line x1="230" y1="68" x2="230" y2="178" stroke="{_OCHRE}" stroke-width="2" stroke-dasharray="5 3"/>\n'
        f'  <line x1="490" y1="68" x2="490" y2="178" stroke="{_OCHRE}" stroke-width="2" stroke-dasharray="5 3"/>\n'
        f'  <line x1="360" y1="58" x2="360" y2="180" stroke="{_TEAL}" stroke-width="2"/>\n'
        f'  <line x1="70" y1="162" x2="650" y2="162" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <polygon points="650,162 640,157 640,167" fill="{_INK}"/>\n'
        f'  <circle cx="230" cy="112" r="8" fill="{_OCHRE}"/>\n'
        f'  <circle cx="490" cy="112" r="8" fill="{_OCHRE}"/>\n'
        f'  <text x="230" y="198" text-anchor="middle" class="math">x₀ - δ</text>\n'
        f'  <text x="360" y="198" text-anchor="middle" class="math">x₀ (asse)</text>\n'
        f'  <text x="490" y="198" text-anchor="middle" class="math">x₀ + δ</text>\n'
        f'  <text x="360" y="228" text-anchor="middle" class="muted">L’intervallo aperto (x₀ - δ, x₀ + δ) traduce la rotta sicura tra due boe simmetriche</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_positional_base_grid(title: str) -> str:
    cols = [("10³ = 1000", "2"), ("10² = 100", "0"), ("10¹ = 10", "4"), ("10⁰ = 1", "7")]
    cells = []
    for idx, (hdr, digit) in enumerate(cols):
        x = 96 + idx * 136
        fill = _OCHRE if digit == "0" else _BLUE
        cells.append(
            f'  <rect x="{x}" y="66" width="120" height="106" rx="6" fill="{fill}" fill-opacity="0.09" stroke="{fill}" stroke-width="1.5"/>\n'
            f'  <text x="{x + 60}" y="92" text-anchor="middle" class="muted">{hdr}</text>\n'
            f'  <text x="{x + 60}" y="146" text-anchor="middle" class="title" style="font-size:32px">{digit}</text>'
        )
    body = (
        f'  <text x="360" y="34" text-anchor="middle" class="title">Notazione posizionale e ruolo dello zero segnaposto</text>\n'
        + "\n".join(cells)
        + f'\n  <text x="360" y="210" text-anchor="middle" class="math">2047 = 2·10³ + 0·10² + 4·10¹ + 7·10⁰</text>'
    )
    return _svg_wrapper(title=title, width=720, height=236, body=body)


def _svg_area_distributive_grid(title: str) -> str:
    body = (
        f'  <text x="360" y="34" text-anchor="middle" class="title">Legge distributiva come scomposizione geometrica di aree</text>\n'
        f'  <rect x="140" y="68" width="240" height="120" fill="{_BLUE}" fill-opacity="0.14" stroke="{_BLUE}" stroke-width="1.8"/>\n'
        f'  <rect x="380" y="68" width="170" height="120" fill="{_OCHRE}" fill-opacity="0.16" stroke="{_OCHRE}" stroke-width="1.8"/>\n'
        f'  <text x="122" y="132" text-anchor="end" class="math">a</text>\n'
        f'  <text x="260" y="58" text-anchor="middle" class="math">b</text>\n'
        f'  <text x="465" y="58" text-anchor="middle" class="math">c</text>\n'
        f'  <text x="260" y="134" text-anchor="middle" class="math">a · b</text>\n'
        f'  <text x="465" y="134" text-anchor="middle" class="math">a · c</text>\n'
        f'  <text x="345" y="220" text-anchor="middle" class="math">a(b + c) = ab + ac</text>'
    )
    return _svg_wrapper(title=title, width=720, height=244, body=body)


def _svg_generic_mathematical(title: str, subtitle: str) -> str:
    body = (
        f'  <text x="360" y="36" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <line x1="90" y1="184" x2="630" y2="184" stroke="{_INK}" stroke-width="1.6"/>\n'
        f'  <line x1="360" y1="54" x2="360" y2="206" stroke="{_INK}" stroke-width="1.6"/>\n'
        f'  <path d="M 140 166 Q 360 40 580 166" fill="none" stroke="{_BLUE}" stroke-width="2.4"/>\n'
        f'  <circle cx="360" cy="103" r="5" fill="{_OCHRE}"/>\n'
        f'  <text x="360" y="226" text-anchor="middle" class="muted">{html.escape(subtitle)}</text>'
    )
    return _svg_wrapper(title=title, width=720, height=248, body=body)


def generate_controlled_svg(diagram_id: str, *, title: Optional[str] = None) -> str:
    """Genera un diagramma SVG controllato ed esteticamente uniforme per il libro."""
    did = str(diagram_id or "").strip()
    if did == "balance_and_number_line":
        return _svg_balance_and_number_line(title or "Contare, ordinare e bilancia dell'uguale")
    if did == "marconi_tolerance_corridor":
        return _svg_marconi_tolerance_corridor(title or "Tolleranza simmetrica e valore assoluto")
    if did == "positional_base_grid":
        return _svg_positional_base_grid(title or "Sistema posizionale in base 10 e zero")
    if did == "area_distributive_grid":
        return _svg_area_distributive_grid(title or "Proprietà distributiva via aree")
    if did == "parabola_focal_rays":
        return _svg_generic_mathematical(title or "Parabola e proprietà focale", "Traiettoria parabolica e simmetria rispetto all'asse")
    if did == "unit_circle_trig":
        return _svg_generic_mathematical(title or "Circonferenza goniometrica", "Proiezioni ortogonali di coseno e seno")
    if did == "series_conjunction_circuit":
        return _svg_generic_mathematical(title or "Catena in serie e congiunzione logica", "Chiusura congiunta di tutti i contatti lungo il percorso")
    if did == "probability_tree_bayes":
        return _svg_generic_mathematical(title or "Albero di probabilità condizionata", "Partizione degli eventi e aggiornamento delle frequenze")
    raise ValueError(
        f"diagram_id non riconosciuto: {diagram_id!r}. Valori supportati: {CONTROLLED_SVG_IDS}"
    )


def save_svg_diagram(
    diagram_id: str,
    out_dir: Path | str = DEFAULT_ASSETS_DIR,
    *,
    filename: Optional[str] = None,
    title: Optional[str] = None,
    caption: str = "",
    chapter_dir: Optional[Path | str] = None,
) -> FigureAsset:
    """Salva su disco un diagramma SVG controllato e restituisce il `FigureAsset` verificato."""
    svg_text = generate_controlled_svg(diagram_id, title=title)
    dest_dir = Path(out_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = filename or f"{diagram_id}.svg"
    dest_path = (dest_dir / fname).resolve()
    dest_path.write_text(svg_text, encoding="utf-8")

    rel = (
        os.path.relpath(dest_path, start=Path(chapter_dir).resolve())
        if chapter_dir is not None
        else str(dest_path)
    ).replace("\\", "/")

    return FigureAsset(
        kind="svg_diagram",
        path=dest_path,
        rel_path=rel,
        caption=caption or (title or diagram_id.replace("_", " ").capitalize()),
        diagram_id=diagram_id,
    )


def find_corpus_figures_for_blocks(
    conn: sqlite3.Connection,
    block_pks: Sequence[int],
    *,
    figures_root: Path | str = DEFAULT_FIGURES_DIR,
    chapter_dir: Optional[Path | str] = None,
    max_figures: int = 3,
) -> List[FigureAsset]:
    """Individua figure reali estratte da Baidu OCR corrispondenti ai `block_pk` citati."""
    root = Path(figures_root)
    if not root.exists() or not block_pks:
        return []

    conn.row_factory = sqlite3.Row
    clean_pks = sorted({int(pk) for pk in block_pks if int(pk) > 0})
    rows: List[sqlite3.Row] = []
    for i in range(0, len(clean_pks), 500):
        chunk = clean_pks[i : i + 500]
        ph = ",".join("?" for _ in chunk)
        rows.extend(
            conn.execute(
                f"""
                SELECT b.block_pk, b.page_start, b.page_end, b.book_title, bk.book_uid
                FROM blocks b
                JOIN books bk ON bk.book_pk = b.book_pk
                WHERE b.block_pk IN ({ph}) AND b.is_active = 1
                ORDER BY b.block_pk ASC
                """,
                tuple(chunk),
            ).fetchall()
        )

    found: List[FigureAsset] = []
    seen_paths: set[Path] = set()
    for r in rows:
        buid = str(r["book_uid"])
        book_fig_dir = root / buid
        if not book_fig_dir.is_dir():
            continue
        p_start = int(r["page_start"] or 0)
        p_end = int(r["page_end"] or p_start)
        for pg in range(p_start, p_end + 1):
            for img_path in sorted(book_fig_dir.glob(f"page_{pg:04d}_*")):
                if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    continue
                resolved = img_path.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                rel = (
                    os.path.relpath(resolved, start=Path(chapter_dir).resolve())
                    if chapter_dir is not None
                    else str(resolved)
                ).replace("\\", "/")
                found.append(
                    FigureAsset(
                        kind="corpus_figure",
                        path=resolved,
                        rel_path=rel,
                        caption=f"Figura originale da {r['book_title']} (pag. {pg})",
                        block_pk=int(r["block_pk"]),
                        book_title=str(r["book_title"]),
                        page=pg,
                    )
                )
                if len(found) >= max_figures:
                    return found
    return found


__all__ = [
    "CONTROLLED_SVG_IDS",
    "DEFAULT_ASSETS_DIR",
    "DEFAULT_FIGURES_DIR",
    "FigureAsset",
    "find_corpus_figures_for_blocks",
    "generate_controlled_svg",
    "save_svg_diagram",
]
