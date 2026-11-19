"""Risolutore di figure reali Baidu (`data/corpus_figures/`) e generatore editoriale di diagrammi SVG
controllati per i *Nuovi Libri* (ADR-0004, TASK-BOOK-01)."""

from __future__ import annotations

import html
import math
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
    "fraction_number_line",
    "proportional_scaling_hyperbola",
    "pythagoras_and_circle",
    "function_sets_mapping",
    "derivative_tangent_integral",
    "linear_algebra_transform",
    "statistical_regression_ci",
    "modular_clock_rsa",
    "memory_stack_twos_comp",
    "algorithm_invariant_testing",
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


def _svg_parabola_focal_rays(title: str) -> str:
    # Parabola x = (y^2)/4p verticale y = a*x^2 con fuoco F e direttrice + raggi riflessi verso F
    # Vertice in (360, 172), direttrice y = 196, fuoco F = (360, 136), y = 172 - (x-360)^2 / 240
    pts = []
    for x in range(180, 541, 12):
        y = 172.0 - ((x - 360) ** 2) / 360.0
        pts.append(f"{x},{y:.1f}")
    poly = " ".join(pts)
    body = (
        f'  <text x="360" y="32" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <line x1="120" y1="172" x2="600" y2="172" stroke="{_INK}" stroke-width="1.3"/>\n'
        f'  <line x1="360" y1="48" x2="360" y2="212" stroke="{_INK}" stroke-width="1.3"/>\n'
        f'  <line x1="140" y1="196" x2="580" y2="196" stroke="{_TEAL}" stroke-width="1.6" stroke-dasharray="6 4"/>\n'
        f'  <text x="586" y="200" class="muted">direttrice d</text>\n'
        f'  <polyline points="{poly}" fill="none" stroke="{_BLUE}" stroke-width="2.6"/>\n'
        f'  <circle cx="360" cy="136" r="5" fill="{_OCHRE}"/>\n'
        f'  <text x="372" y="138" class="math">F(0, p)</text>\n'
        # Punto P = (480, 132) -> (480-360)^2/360 = 40 -> y = 132
        f'  <line x1="480" y1="54" x2="480" y2="132" stroke="{_OCHRE}" stroke-width="1.6" stroke-dasharray="4 3"/>\n'
        f'  <line x1="480" y1="132" x2="360" y2="136" stroke="{_OCHRE}" stroke-width="1.8"/>\n'
        f'  <line x1="480" y1="132" x2="480" y2="196" stroke="{_TEAL}" stroke-width="1.6" stroke-dasharray="3 3"/>\n'
        f'  <circle cx="480" cy="132" r="4.5" fill="{_BLUE}"/>\n'
        f'  <text x="492" y="128" class="math">P(x, y)</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Luogo geometrico: distanza PF = distanza Pd; raggi assiali convergenti nel fuoco F</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_unit_circle_trig(title: str) -> str:
    # Cerchio unitario centro (230, 128), r = 74; angolo alpha = 35 deg -> x = 230 + 60.6, y = 128 - 42.4
    cx, cy, r = 230, 128, 74
    px, py = 290.6, 85.6
    # Sinusoide a destra x in [390..650]
    sine_pts = []
    for i in range(0, 53):
        t = i * (2 * math.pi / 52.0)
        sx = 395 + i * 4.8
        sy = 128 - 58.0 * math.sin(t)
        sine_pts.append(f"{sx:.1f},{sy:.1f}")
    sine_poly = " ".join(sine_pts)
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <line x1="120" y1="{cy}" x2="340" y2="{cy}" stroke="{_INK}" stroke-width="1.3"/>\n'
        f'  <line x1="{cx}" y1="42" x2="{cx}" y2="214" stroke="{_INK}" stroke-width="1.3"/>\n'
        f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{_BLUE}" fill-opacity="0.06" stroke="{_BLUE}" stroke-width="2"/>\n'
        f'  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{cy}" stroke="{_TEAL}" stroke-width="2.5"/>\n'
        f'  <line x1="{px:.1f}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="{_OCHRE}" stroke-width="2.5"/>\n'
        f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{_OCHRE}"/>\n'
        f'  <text x="256" y="143" class="math" style="fill:{_TEAL}">cos α</text>\n'
        f'  <text x="298" y="110" class="math" style="fill:{_OCHRE}">sen α</text>\n'
        f'  <text x="248" y="117" class="muted">α</text>\n'
        f'  <line x1="{px:.1f}" y1="{py:.1f}" x2="418" y2="{py:.1f}" stroke="{_GRID}" stroke-width="1.2" stroke-dasharray="4 3"/>\n'
        f'  <line x1="395" y1="128" x2="660" y2="128" stroke="{_INK}" stroke-width="1.3"/>\n'
        f'  <line x1="395" y1="54" x2="395" y2="202" stroke="{_INK}" stroke-width="1.3"/>\n'
        f'  <polyline points="{sine_poly}" fill="none" stroke="{_OCHRE}" stroke-width="2.2"/>\n'
        f'  <text x="528" y="214" text-anchor="middle" class="math">sen²α + cos²α = 1</text>\n'
        f'  <text x="360" y="234" text-anchor="middle" class="muted">Dalla proiezione sul cerchio unitario all’onda periodica in radianti</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_series_conjunction_circuit(title: str) -> str:
    body = (
        f'  <text x="360" y="32" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <text x="195" y="58" text-anchor="middle" class="muted">Circuito in serie ↔ Congiunzione logica (A ∧ B)</text>\n'
        f'  <line x1="60" y1="104" x2="118" y2="104" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <line x1="118" y1="104" x2="162" y2="82" stroke="{_BLUE}" stroke-width="2.4"/>\n'
        f'  <circle cx="118" cy="104" r="4" fill="{_BLUE}"/><circle cx="164" cy="104" r="4" fill="{_BLUE}"/>\n'
        f'  <text x="140" y="76" text-anchor="middle" class="math">A</text>\n'
        f'  <line x1="164" y1="104" x2="220" y2="104" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <line x1="220" y1="104" x2="264" y2="104" stroke="{_TEAL}" stroke-width="2.4"/>\n'
        f'  <circle cx="220" cy="104" r="4" fill="{_TEAL}"/><circle cx="264" cy="104" r="4" fill="{_TEAL}"/>\n'
        f'  <text x="242" y="76" text-anchor="middle" class="math">B</text>\n'
        f'  <line x1="264" y1="104" x2="325" y2="104" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <circle cx="332" cy="104" r="9" fill="{_OCHRE}" fill-opacity="0.22" stroke="{_OCHRE}" stroke-width="1.8"/>\n'
        f'  <text x="195" y="138" text-anchor="middle" class="label">Chiuso sse A = 1 ∧ B = 1</text>\n'
        f'  <line x1="365" y1="50" x2="365" y2="215" stroke="{_GRID}" stroke-width="1.2"/>\n'
        f'  <text x="538" y="58" text-anchor="middle" class="muted">Circuito in parallelo ↔ Disgiunzione logica (A ∨ B)</text>\n'
        f'  <line x1="395" y1="104" x2="445" y2="104" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <polyline points="445,104 445,78 485,78" fill="none" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <line x1="485" y1="78" x2="530" y2="78" stroke="{_TEAL}" stroke-width="2.4"/>\n'
        f'  <polyline points="530,78 575,78 575,104" fill="none" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <polyline points="445,104 445,132 485,132" fill="none" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <line x1="485" y1="132" x2="526" y2="114" stroke="{_BLUE}" stroke-width="2.4"/>\n'
        f'  <polyline points="530,132 575,132 575,104" fill="none" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <text x="508" y="70" text-anchor="middle" class="math">A</text>\n'
        f'  <text x="508" y="152" text-anchor="middle" class="math">B</text>\n'
        f'  <line x1="575" y1="104" x2="625" y2="104" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <circle cx="634" cy="104" r="9" fill="{_TEAL}" fill-opacity="0.32" stroke="{_TEAL}" stroke-width="1.8"/>\n'
        f'  <text x="538" y="180" text-anchor="middle" class="label">Chiuso sse A = 1 ∨ B = 1</text>\n'
        f'  <text x="360" y="230" text-anchor="middle" class="muted">Isomorfismo booleano tra commutazione elettrica, algebra degli insiemi e tavola di verità</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_probability_tree_bayes(title: str) -> str:
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <circle cx="90" cy="126" r="7" fill="{_INK}"/>\n'
        f'  <line x1="97" y1="122" x2="260" y2="76" stroke="{_BLUE}" stroke-width="2.2"/>\n'
        f'  <line x1="97" y1="130" x2="260" y2="176" stroke="{_OCHRE}" stroke-width="2.2"/>\n'
        f'  <text x="172" y="88" class="math">P(H)</text>\n'
        f'  <text x="172" y="172" class="math" style="fill:{_OCHRE}">P(¬H)</text>\n'
        f'  <rect x="260" y="60" width="54" height="30" rx="5" fill="{_BLUE}" fill-opacity="0.14" stroke="{_BLUE}"/>\n'
        f'  <text x="287" y="80" text-anchor="middle" class="math">H</text>\n'
        f'  <rect x="260" y="160" width="54" height="30" rx="5" fill="{_OCHRE}" fill-opacity="0.14" stroke="{_OCHRE}"/>\n'
        f'  <text x="287" y="180" text-anchor="middle" class="math">¬H</text>\n'
        f'  <line x1="314" y1="70" x2="475" y2="54" stroke="{_TEAL}" stroke-width="2"/>\n'
        f'  <line x1="314" y1="80" x2="475" y2="98" stroke="{_MUTED}" stroke-width="1.5" stroke-dasharray="4 3"/>\n'
        f'  <line x1="314" y1="170" x2="475" y2="148" stroke="{_TEAL}" stroke-width="2"/>\n'
        f'  <line x1="314" y1="180" x2="475" y2="196" stroke="{_MUTED}" stroke-width="1.5" stroke-dasharray="4 3"/>\n'
        f'  <text x="394" y="54" class="muted">P(E|H)</text>\n'
        f'  <text x="394" y="150" class="muted">P(E|¬H)</text>\n'
        f'  <text x="484" y="58" class="math">H ∩ E</text>\n'
        f'  <text x="484" y="102" class="muted">H ∩ ¬E</text>\n'
        f'  <text x="484" y="152" class="math">¬H ∩ E</text>\n'
        f'  <text x="484" y="200" class="muted">¬H ∩ ¬E</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="math">P(H|E) = P(E|H)P(H) / [P(E|H)P(H) + P(E|¬H)P(¬H)]</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_fraction_number_line(title: str) -> str:
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <rect x="70" y="56" width="290" height="28" rx="4" fill="{_BLUE}" fill-opacity="0.16" stroke="{_BLUE}"/>\n'
        f'  <line x1="215" y1="56" x2="215" y2="84" stroke="{_BLUE}" stroke-width="1.5"/>\n'
        f'  <rect x="70" y="92" width="290" height="28" rx="4" fill="{_OCHRE}" fill-opacity="0.16" stroke="{_OCHRE}"/>\n'
        f'  <line x1="142.5" y1="92" x2="142.5" y2="120" stroke="{_OCHRE}" stroke-width="1.2"/>\n'
        f'  <line x1="215" y1="92" x2="215" y2="120" stroke="{_OCHRE}" stroke-width="1.2"/>\n'
        f'  <line x1="287.5" y1="92" x2="287.5" y2="120" stroke="{_OCHRE}" stroke-width="1.2"/>\n'
        f'  <text x="378" y="75" class="math">1/2 = 2/4 = 3/6</text>\n'
        f'  <text x="378" y="111" class="muted">Parti equivalenti dello stesso intero</text>\n'
        f'  <line x1="80" y1="176" x2="640" y2="176" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <polygon points="640,176 630,171 630,181" fill="{_INK}"/>\n'
        f'  <line x1="80" y1="176" x2="90" y2="171" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <line x1="360" y1="166" x2="360" y2="186" stroke="{_TEAL}" stroke-width="2.2"/>\n'
        f'  <text x="360" y="204" text-anchor="middle" class="math">0</text>\n'
        f'  <line x1="160" y1="168" x2="160" y2="184" stroke="{_INK}"/><text x="160" y="204" text-anchor="middle" class="label">-2</text>\n'
        f'  <line x1="260" y1="168" x2="260" y2="184" stroke="{_INK}"/><text x="260" y="204" text-anchor="middle" class="label">-1</text>\n'
        f'  <line x1="460" y1="168" x2="460" y2="184" stroke="{_INK}"/><text x="460" y="204" text-anchor="middle" class="label">+1</text>\n'
        f'  <line x1="560" y1="168" x2="560" y2="184" stroke="{_INK}"/><text x="560" y="204" text-anchor="middle" class="label">+2</text>\n'
        f'  <circle cx="510" cy="176" r="5" fill="{_OCHRE}"/><text x="510" y="158" text-anchor="middle" class="math">3/2</text>\n'
        f'  <circle cx="210" cy="176" r="5" fill="{_BLUE}"/><text x="210" y="158" text-anchor="middle" class="math">-3/2</text>\n'
        f'  <text x="360" y="230" text-anchor="middle" class="muted">Densità dei razionali Q, segni orientati in Z e simmetria rispetto allo zero</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_proportional_scaling_hyperbola(title: str) -> str:
    hyp = " ".join(f"{410 + dx},{(186 - 1600.0 / max(12, dx)):.1f}" for dx in range(18, 210, 8))
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <line x1="70" y1="186" x2="310" y2="186" stroke="{_INK}" stroke-width="1.5"/>\n'
        f'  <line x1="90" y1="54" x2="90" y2="200" stroke="{_INK}" stroke-width="1.5"/>\n'
        f'  <line x1="90" y1="186" x2="290" y2="66" stroke="{_BLUE}" stroke-width="2.5"/>\n'
        f'  <text x="195" y="154" class="math">y = k·x</text>\n'
        f'  <text x="195" y="210" text-anchor="middle" class="muted">Rapporto costante (y/x = k)</text>\n'
        f'  <line x1="390" y1="186" x2="650" y2="186" stroke="{_INK}" stroke-width="1.5"/>\n'
        f'  <line x1="410" y1="54" x2="410" y2="200" stroke="{_INK}" stroke-width="1.5"/>\n'
        f'  <polyline points="{hyp}" fill="none" stroke="{_OCHRE}" stroke-width="2.5"/>\n'
        f'  <rect x="410" y="122" width="25" height="64" fill="{_TEAL}" fill-opacity="0.16" stroke="{_TEAL}" stroke-dasharray="3 2"/>\n'
        f'  <text x="540" y="114" class="math" style="fill:{_OCHRE}">x · y = k</text>\n'
        f'  <text x="530" y="210" text-anchor="middle" class="muted">Prodotto costante: area invariante</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Confronto tra variazione lineare diretta e legge iperbolica inversa</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_pythagoras_and_circle(title: str) -> str:
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        # Triangolo rettangolo A=(150,170), B=(260,170), C=(150,90)
        f'  <polygon points="150,170 260,170 150,90" fill="{_TEAL}" fill-opacity="0.18" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <rect x="104" y="90" width="46" height="80" fill="{_BLUE}" fill-opacity="0.12" stroke="{_BLUE}" stroke-width="1.4"/>\n'
        f'  <rect x="150" y="170" width="110" height="44" fill="{_OCHRE}" fill-opacity="0.12" stroke="{_OCHRE}" stroke-width="1.4"/>\n'
        f'  <text x="127" y="134" text-anchor="middle" class="math">a²</text>\n'
        f'  <text x="205" y="196" text-anchor="middle" class="math">b²</text>\n'
        f'  <text x="220" y="122" class="math">c = √(a²+b²)</text>\n'
        f'  <line x1="360" y1="48" x2="360" y2="212" stroke="{_GRID}" stroke-width="1.2"/>\n'
        f'  <circle cx="520" cy="126" r="66" fill="{_BLUE}" fill-opacity="0.08" stroke="{_BLUE}" stroke-width="2.2"/>\n'
        f'  <line x1="520" y1="126" x2="586" y2="126" stroke="{_OCHRE}" stroke-width="2.2"/>\n'
        f'  <circle cx="520" cy="126" r="4" fill="{_INK}"/>\n'
        f'  <text x="553" y="118" text-anchor="middle" class="math" style="fill:{_OCHRE}">r</text>\n'
        f'  <text x="520" y="210" text-anchor="middle" class="math">C = 2πr ,  A = πr²</text>\n'
        f'  <text x="360" y="234" text-anchor="middle" class="muted">Invariante metrico euclideo sul piano cartesiano e misura del cerchio</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_function_sets_mapping(title: str) -> str:
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <ellipse cx="145" cy="126" rx="58" ry="68" fill="{_BLUE}" fill-opacity="0.08" stroke="{_BLUE}" stroke-width="1.8"/>\n'
        f'  <ellipse cx="325" cy="126" rx="58" ry="68" fill="{_TEAL}" fill-opacity="0.08" stroke="{_TEAL}" stroke-width="1.8"/>\n'
        f'  <text x="145" y="76" text-anchor="middle" class="math">A (Dominio)</text>\n'
        f'  <text x="325" y="76" text-anchor="middle" class="math">B (Codominio)</text>\n'
        f'  <circle cx="145" cy="104" r="4" fill="{_INK}"/><circle cx="145" cy="134" r="4" fill="{_INK}"/><circle cx="145" cy="164" r="4" fill="{_INK}"/>\n'
        f'  <circle cx="325" cy="104" r="4" fill="{_INK}"/><circle cx="325" cy="144" r="4" fill="{_INK}"/>\n'
        f'  <line x1="149" y1="104" x2="320" y2="104" stroke="{_BLUE}" stroke-width="1.8"/>\n'
        f'  <line x1="149" y1="134" x2="320" y2="144" stroke="{_OCHRE}" stroke-width="1.8"/>\n'
        f'  <line x1="149" y1="164" x2="320" y2="144" stroke="{_OCHRE}" stroke-width="1.8" stroke-dasharray="4 3"/>\n'
        f'  <text x="235" y="210" text-anchor="middle" class="muted">Funzione ben definita, non iniettiva</text>\n'
        f'  <line x1="430" y1="184" x2="650" y2="184" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <line x1="450" y1="54" x2="450" y2="200" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <line x1="465" y1="168" x2="635" y2="74" stroke="{_BLUE}" stroke-width="2.2"/>\n'
        f'  <line x1="470" y1="78" x2="625" y2="164" stroke="{_OCHRE}" stroke-width="2.2"/>\n'
        f'  <circle cx="548" cy="122" r="5" fill="{_TEAL}"/>\n'
        f'  <text x="548" y="210" text-anchor="middle" class="math">Intersezione r₁ ∩ r₂</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Dalle relazioni tra insiemi alla geometria analitica dei sistemi lineari</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_derivative_tangent_integral(title: str) -> str:
    curve = " ".join(f"{90 + i * 16},{(180 - 0.14 * ((i * 16) ** 1.45)):.1f}" for i in range(0, 17))
    curve_r = " ".join(
        f"{x},{(176 - 22 - 0.0028 * ((x - 400) ** 2)):.1f}" for x in range(405, 630, 14)
    )
    poly_area = "430,176 " + " ".join(
        f"{x},{(176 - 22 - 0.0028 * ((x - 400) ** 2)):.1f}" for x in range(430, 591, 16)
    ) + " 590,176"
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <line x1="70" y1="180" x2="340" y2="180" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <line x1="90" y1="50" x2="90" y2="195" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <polyline points="{curve}" fill="none" stroke="{_BLUE}" stroke-width="2.4"/>\n'
        f'  <line x1="150" y1="168" x2="318" y2="68" stroke="{_OCHRE}" stroke-width="2" stroke-dasharray="5 3"/>\n'
        f'  <line x1="175" y1="153" x2="320" y2="96" stroke="{_TEAL}" stroke-width="2"/>\n'
        f'  <circle cx="202" cy="137" r="4.5" fill="{_OCHRE}"/>\n'
        f'  <text x="205" y="206" text-anchor="middle" class="math">f\'(x) = lim Δy/Δx</text>\n'
        f'  <line x1="395" y1="176" x2="650" y2="176" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <line x1="405" y1="50" x2="405" y2="195" stroke="{_INK}" stroke-width="1.4"/>\n'
        f'  <polygon points="{poly_area}" fill="{_TEAL}" fill-opacity="0.22" stroke="none"/>\n'
        f'  <polyline points="{curve_r}" fill="none" stroke="{_BLUE}" stroke-width="2.4"/>\n'
        f'  <text x="520" y="206" text-anchor="middle" class="math">∫ₐᵇ f(x) dx = F(b) - F(a)</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Dualità differenziale: tasso istantaneo lungo la tangente e accumulo dell’area</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_linear_algebra_transform(title: str) -> str:
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <rect x="90" y="88" width="110" height="84" fill="{_BLUE}" fill-opacity="0.12" stroke="{_BLUE}" stroke-width="1.4"/>\n'
        f'  <line x1="90" y1="172" x2="200" y2="172" stroke="{_BLUE}" stroke-width="2.6"/>\n'
        f'  <line x1="90" y1="172" x2="90" y2="88" stroke="{_TEAL}" stroke-width="2.6"/>\n'
        f'  <text x="145" y="192" text-anchor="middle" class="math">e₁</text>\n'
        f'  <text x="72" y="132" class="math" style="fill:{_TEAL}">e₂</text>\n'
        f'  <text x="305" y="132" text-anchor="middle" class="math">T(v) = Av</text>\n'
        f'  <line x1="255" y1="142" x2="355" y2="142" stroke="{_INK}" stroke-width="2"/>\n'
        f'  <polygon points="355,142 345,137 345,147" fill="{_INK}"/>\n'
        f'  <polygon points="420,176 540,152 595,74 475,98" fill="{_OCHRE}" fill-opacity="0.16" stroke="{_OCHRE}" stroke-width="1.8"/>\n'
        f'  <line x1="420" y1="176" x2="540" y2="152" stroke="{_BLUE}" stroke-width="2.6"/>\n'
        f'  <line x1="420" y1="176" x2="475" y2="98" stroke="{_TEAL}" stroke-width="2.6"/>\n'
        f'  <line x1="420" y1="176" x2="595" y2="74" stroke="{_OCHRE}" stroke-width="2" stroke-dasharray="5 3"/>\n'
        f'  <text x="530" y="196" text-anchor="middle" class="math">Av = λv ,  Area = |det(A)|</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Deformazione lineare della base canonica, determinante e direzioni invarianti (autovettori)</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_statistical_regression_ci(title: str) -> str:
    pts = [(115, 162), (165, 146), (210, 152), (255, 128), (305, 118), (350, 124), (400, 96), (455, 86), (510, 74), (565, 62)]
    dots = "\n".join(
        f'  <circle cx="{x}" cy="{y}" r="4.5" fill="{_BLUE}"/>\n'
        f'  <line x1="{x}" y1="{y}" x2="{x}" y2="{184 - 0.22 * (x - 90):.1f}" stroke="{_OCHRE}" stroke-width="1.2" stroke-dasharray="3 2"/>'
        for x, y in pts
    )
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <polygon points="100,192 590,82 590,48 100,162" fill="{_TEAL}" fill-opacity="0.12" stroke="none"/>\n'
        f'  <line x1="80" y1="196" x2="640" y2="196" stroke="{_INK}" stroke-width="1.5"/>\n'
        f'  <line x1="95" y1="48" x2="95" y2="208" stroke="{_INK}" stroke-width="1.5"/>\n'
        f'  <line x1="100" y1="181" x2="590" y2="73" stroke="{_TEAL}" stroke-width="2.5"/>\n'
        f"{dots}\n"
        f'  <text x="485" y="138" class="math">min ∑(yᵢ - ŷᵢ)²</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Retta ai minimi quadrati, residui verticali e banda di confidenza campionaria</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_modular_clock_rsa(title: str) -> str:
    cx, cy, r = 175, 128, 72
    ticks = []
    for k in range(12):
        ang = -math.pi / 2 + k * (2 * math.pi / 12)
        tx = cx + (r + 16) * math.cos(ang)
        ty = cy + (r + 16) * math.sin(ang) + 4
        dx = cx + r * math.cos(ang)
        dy = cy + r * math.sin(ang)
        col = _OCHRE if k in {0, 5, 7} else _BLUE
        ticks.append(f'  <circle cx="{dx:.1f}" cy="{dy:.1f}" r="4" fill="{col}"/>')
        ticks.append(f'  <text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" class="muted">{k}</text>')
    clock_svg = "\n".join(ticks)
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{_BLUE}" fill-opacity="0.06" stroke="{_BLUE}" stroke-width="1.8"/>\n'
        f"{clock_svg}\n"
        f'  <text x="{cx}" y="{cy + 4}" text-anchor="middle" class="math">ℤ / nℤ</text>\n'
        f'  <rect x="330" y="68" width="120" height="44" rx="6" fill="{_BLUE}" fill-opacity="0.12" stroke="{_BLUE}"/>\n'
        f'  <text x="390" y="95" text-anchor="middle" class="math">c ≡ mᵉ (mod n)</text>\n'
        f'  <rect x="515" y="68" width="140" height="44" rx="6" fill="{_OCHRE}" fill-opacity="0.12" stroke="{_OCHRE}"/>\n'
        f'  <text x="585" y="95" text-anchor="middle" class="math">m ≡ cᵈ (mod n)</text>\n'
        f'  <line x1="450" y1="90" x2="515" y2="90" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <polygon points="515,90 506,85 506,95" fill="{_INK}"/>\n'
        f'  <rect x="330" y="138" width="325" height="44" rx="6" fill="{_TEAL}" fill-opacity="0.10" stroke="{_TEAL}"/>\n'
        f'  <text x="492" y="165" text-anchor="middle" class="math">e·d ≡ 1 (mod φ(n)),   n = p·q</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Orologio delle congruenze modulari, asimmetria RSA ed esponente privato tramite Eulero</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_memory_stack_twos_comp(title: str) -> str:
    bits = [("1", _OCHRE, "-128"), ("0", _BLUE, "+64"), ("1", _BLUE, "+32"), ("0", _BLUE, "+16"), ("1", _BLUE, "+8"), ("0", _BLUE, "+4"), ("1", _BLUE, "+2"), ("0", _BLUE, "+1")]
    cells = []
    for i, (b, col, wt) in enumerate(bits):
        x = 58 + i * 42
        cells.append(
            f'  <rect x="{x}" y="72" width="38" height="44" rx="4" fill="{col}" fill-opacity="0.12" stroke="{col}" stroke-width="1.4"/>\n'
            f'  <text x="{x + 19}" y="64" text-anchor="middle" class="muted">{wt}</text>\n'
            f'  <text x="{x + 19}" y="101" text-anchor="middle" class="title">{b}</text>'
        )
    bits_svg = "\n".join(cells)
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f"{bits_svg}\n"
        f'  <text x="225" y="142" text-anchor="middle" class="math">Complemento a 2 (8 bit): -128 + 42 = -86</text>\n'
        f'  <rect x="440" y="64" width="220" height="40" rx="5" fill="{_OCHRE}" fill-opacity="0.14" stroke="{_OCHRE}"/>\n'
        f'  <text x="550" y="89" text-anchor="middle" class="label">Stack ↓ (frame &amp; indirizzi ritorno)</text>\n'
        f'  <rect x="440" y="114" width="220" height="40" rx="5" fill="{_TEAL}" fill-opacity="0.14" stroke="{_TEAL}"/>\n'
        f'  <text x="550" y="139" text-anchor="middle" class="label">Heap ↑ (allocazione dinamica)</text>\n'
        f'  <rect x="440" y="164" width="220" height="32" rx="5" fill="{_BLUE}" fill-opacity="0.12" stroke="{_BLUE}"/>\n'
        f'  <text x="550" y="185" text-anchor="middle" class="label">Testo / Dati statici</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Rappresentazione binaria con segno, rischio di overflow e geografia della memoria virtuale</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def _svg_algorithm_invariant_testing(title: str) -> str:
    body = (
        f'  <text x="360" y="30" text-anchor="middle" class="title">{html.escape(title)}</text>\n'
        f'  <rect x="60" y="72" width="130" height="44" rx="6" fill="{_BLUE}" fill-opacity="0.12" stroke="{_BLUE}"/>\n'
        f'  <text x="125" y="99" text-anchor="middle" class="label">Inizializzazione (I₀)</text>\n'
        f'  <rect x="240" y="72" width="145" height="44" rx="6" fill="{_TEAL}" fill-opacity="0.14" stroke="{_TEAL}"/>\n'
        f'  <text x="312" y="99" text-anchor="middle" class="label">Mantenimento (Iₖ⇒Iₖ₊₁)</text>\n'
        f'  <rect x="240" y="148" width="145" height="44" rx="6" fill="{_OCHRE}" fill-opacity="0.14" stroke="{_OCHRE}"/>\n'
        f'  <text x="312" y="175" text-anchor="middle" class="label">Terminazione &amp; Verifica</text>\n'
        f'  <line x1="190" y1="94" x2="240" y2="94" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <line x1="312" y1="116" x2="312" y2="148" stroke="{_INK}" stroke-width="1.8"/>\n'
        f'  <line x1="425" y1="48" x2="425" y2="206" stroke="{_GRID}" stroke-width="1.2"/>\n'
        f'  <polygon points="480,184 650,184 610,144 520,144" fill="{_BLUE}" fill-opacity="0.14" stroke="{_BLUE}"/>\n'
        f'  <polygon points="520,144 610,144 590,104 540,104" fill="{_TEAL}" fill-opacity="0.18" stroke="{_TEAL}"/>\n'
        f'  <polygon points="540,104 590,104 565,64" fill="{_OCHRE}" fill-opacity="0.22" stroke="{_OCHRE}"/>\n'
        f'  <text x="565" y="169" text-anchor="middle" class="muted">Test unitari &amp; proprietà</text>\n'
        f'  <text x="565" y="129" text-anchor="middle" class="muted">Integrazione</text>\n'
        f'  <text x="565" y="95" text-anchor="middle" class="muted">E2E</text>\n'
        f'  <text x="360" y="232" text-anchor="middle" class="muted">Dimostrazione di correttezza tramite invariante di ciclo e piramide di verifica automatica</text>'
    )
    return _svg_wrapper(title=title, width=720, height=250, body=body)


def generate_controlled_svg(diagram_id: str, *, title: Optional[str] = None) -> str:
    """Genera un diagramma SVG controllato ed esteticamente uniforme per il libro."""
    did = str(diagram_id or "").strip()
    dispatch = {
        "balance_and_number_line": lambda: _svg_balance_and_number_line(title or "Contare, ordinare e bilancia dell'uguale"),
        "marconi_tolerance_corridor": lambda: _svg_marconi_tolerance_corridor(title or "Tolleranza simmetrica e valore assoluto"),
        "positional_base_grid": lambda: _svg_positional_base_grid(title or "Sistema posizionale in base 10 e zero"),
        "area_distributive_grid": lambda: _svg_area_distributive_grid(title or "Proprietà distributiva via aree"),
        "parabola_focal_rays": lambda: _svg_parabola_focal_rays(title or "Parabola e proprietà focale"),
        "unit_circle_trig": lambda: _svg_unit_circle_trig(title or "Circonferenza goniometrica e onda sinusoidale"),
        "series_conjunction_circuit": lambda: _svg_series_conjunction_circuit(title or "Circuiti booleani in serie e in parallelo"),
        "probability_tree_bayes": lambda: _svg_probability_tree_bayes(title or "Albero degli eventi e aggiornamento di Bayes"),
        "fraction_number_line": lambda: _svg_fraction_number_line(title or "Frazioni equivalenti e numeri relativi sulla retta"),
        "proportional_scaling_hyperbola": lambda: _svg_proportional_scaling_hyperbola(title or "Proporzionalità diretta e legge inversa"),
        "pythagoras_and_circle": lambda: _svg_pythagoras_and_circle(title or "Teorema di Pitagora e geometria del cerchio"),
        "function_sets_mapping": lambda: _svg_function_sets_mapping(title or "Funzioni tra insiemi e sistemi lineari"),
        "derivative_tangent_integral": lambda: _svg_derivative_tangent_integral(title or "Secante, tangente e accumulo integrale"),
        "linear_algebra_transform": lambda: _svg_linear_algebra_transform(title or "Trasformazioni lineari, determinante e autovettori"),
        "statistical_regression_ci": lambda: _svg_statistical_regression_ci(title or "Regressione lineare, residui e stima intervallare"),
        "modular_clock_rsa": lambda: _svg_modular_clock_rsa(title or "Aritmetica modulare e cifratura asimmetrica"),
        "memory_stack_twos_comp": lambda: _svg_memory_stack_twos_comp(title or "Complemento a due e architettura della memoria"),
        "algorithm_invariant_testing": lambda: _svg_algorithm_invariant_testing(title or "Invarianti algoritmici e verifica automatica"),
    }
    builder = dispatch.get(did)
    if builder is not None:
        return builder()
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
