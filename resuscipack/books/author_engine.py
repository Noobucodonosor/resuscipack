"""Motore Autoriale dei *Nuovi Libri* Continui (ADR-0004, TASK-BOOK-01).

Orchestra l'intera filiera editoriale su `pack_corpus.db`:
1. Assembla un dossier di Contezza Simultanea (`curiosity_bridges`, `decompress_concept`,
   `objective_corpus_map`, figure reali da `data/corpus_figures/`, diagrammi SVG controllati e
   palestra `SymPy`).
2. Pre-verifica deterministicamente tutte le citazioni verbatim (`[Q1]..[Qk]`) contro
   `blocks.norm_content` (4–25 parole, OCR pulito, zero deissi cieche).
3. Genera la prosa adulta continua tramite LLM configurabile (`vertex` default `gemini-3.1-pro-preview`,
   fail-honest senza mock).
4. Compila il Markdown definitivo con rimandi `[^1..m]`, figure/SVG inline e Apparato delle fonti
   a 3 colori (`[Verificato sul testo]`, `[Ricostruzione matematica / addestramento]`,
   `[Esercizi originali]`).
5. Sottopone il capitolo al doppio controllo (`run_deterministic_chapter_audit` +
   `run_adversarial_llm_critique` su modello revisore separato) con auto-revisione guidata prima
   della promozione a `stato: pubblicato`.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from ..corpus.schema import DEFAULT_DB_PATH, connect_corpus_db
from ..curriculum.drills_sympy import generate_drill_set
from ..epistemic.batch_cli import MissingCredentialsError  # noqa: F401
from ..epistemic.bridge import get_bridges_for_node
from ..epistemic.decompressor import decompress_concept
from ..epistemic.schema_v21 import normalizza_testo
from .critique import (
    CritiqueReport,
    JsonLlmCallable,
    audit_and_critique_chapter,
    call_editorial_json_llm,
)
from .svg_diagrams import (
    DEFAULT_ASSETS_DIR,
    DEFAULT_FIGURES_DIR,
    FigureAsset,
    find_corpus_figures_for_blocks,
    save_svg_diagram,
)

DEFAULT_BOOKS_DIR = Path(__file__).resolve().parents[2] / "data" / "books"

_OCR_GARBAGE_RE = re.compile(r"(?:[ëãõ■\ufffd]|_{3,}|\.{4,}|[a-z]{2,}[A-Z]\.[a-z]+)")
_BLIND_DEIXIS_QUOTE_RE = re.compile(
    r"\b(?:ivi|ibidem|op\.\s*cit\.|loc\.\s*cit\.|vedi\s+sopra|vedi\s+sotto|suddetto)\b",
    flags=re.IGNORECASE,
)
_Q_TAG_RE = re.compile(r"\[Q(\d+)\]")
_DANGLING_TAIL_WORDS = frozenset(
    {
        "e",
        "ed",
        "o",
        "ma",
        "che",
        "di",
        "del",
        "della",
        "dei",
        "degli",
        "delle",
        "a",
        "al",
        "alla",
        "in",
        "nel",
        "nella",
        "con",
        "su",
        "per",
        "tra",
        "fra",
        "il",
        "lo",
        "la",
        "i",
        "gli",
        "le",
        "un",
        "uno",
        "una",
        "questo",
        "questa",
        "questi",
        "queste",
        "si",
        "se",
    }
)


@dataclass(frozen=True)
class ChapterSpec:
    """Specifica editoriale completa per generare un capitolo continuo."""

    volume_id: str
    chapter_number: int
    slug: str
    title: str
    subtitle: str
    node_ids: Tuple[str, ...]
    concept_queries: Tuple[str, ...]
    drill_keys: Tuple[str, ...]
    svg_diagram_id: str
    svg_caption: str = ""
    extra_block_pks: Tuple[int, ...] = ()
    target_length_words: int = 1200


def _clean_book_title_for_citation(book_title: str, author: Optional[str] = None) -> str:
    """Rimuove prefissi editoriali tra quadre, suffissi di archivio (`libgen.lc`) e duplicazioni dell'autore."""
    cleaned = " ".join(str(book_title or "").split()).strip()
    cleaned = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", cleaned)
    cleaned = re.sub(
        r"\s*(?:-\s*)?(?:libgen(?:\.lc)?|z-lib(?:\.org)?)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\(\s*,\s*", "(", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" -")
    if author:
        author_norm = " ".join(str(author).split()).strip()
        for sep in (" - ", ": ", ", "):
            prefix = f"{author_norm}{sep}"
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()
                break
        if cleaned.lower().startswith(author_norm.lower() + " "):
            rest = cleaned[len(author_norm) :].lstrip(" -:")
            if rest:
                cleaned = rest
    return cleaned or str(book_title or "").strip()


@dataclass(frozen=True)
class VerifiedQuoteCandidate:
    """Citazione pre-verificata deterministicamente contro `blocks.norm_content`."""

    quote_id: str  # "Q1", "Q2", ...
    block_pk: int
    block_uid: str
    book_pk: int
    book_title: str
    author: Optional[str]
    page: Optional[int]
    printed_page: Optional[str]
    primary_discipline: Optional[str]
    mode: str
    when_label: str
    stmt: str
    quote: str
    vs_dispute: Optional[str]
    is_wrong_book_bridge: bool

    def source_label(self) -> str:
        clean_title = _clean_book_title_for_citation(self.book_title, self.author)
        author_part = f"{self.author}, " if self.author else ""
        page_part = f"p. {self.printed_page}" if self.printed_page else (f"p. {self.page}" if self.page else "s.p.")
        return f"{author_part}{clean_title} ({page_part})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "block_pk": self.block_pk,
            "block_uid": self.block_uid,
            "book_pk": self.book_pk,
            "book_title": self.book_title,
            "author": self.author,
            "page": self.page,
            "printed_page": self.printed_page,
            "primary_discipline": self.primary_discipline,
            "mode": self.mode,
            "when_label": self.when_label,
            "stmt": self.stmt,
            "quote": self.quote,
            "vs_dispute": self.vs_dispute,
            "is_wrong_book_bridge": self.is_wrong_book_bridge,
        }


@dataclass(frozen=True)
class ChapterDossier:
    """Dossier unificato di fonti verificate, figure, esercizi SymPy e radar ministeriale."""

    spec: ChapterSpec
    quotes: Tuple[VerifiedQuoteCandidate, ...]
    figures: Tuple[FigureAsset, ...]
    sympy_drills: Tuple[Dict[str, Any], ...]
    curriculum_objectives: Tuple[str, ...]

    def to_critic_sources_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "quote_id": q.quote_id,
                "block_pk": q.block_pk,
                "book_title": q.book_title,
                "page": q.printed_page or q.page,
                "quote": q.quote,
                "stmt": q.stmt,
                "vs_dispute": q.vs_dispute,
            }
            for q in self.quotes
        ]


@dataclass(frozen=True)
class CompiledChapterResult:
    """Esito completo della generazione, compilazione e rilettura critica di un capitolo."""

    chapter_path: Path
    status: str  # "pubblicato" | "bozza"
    attempts: int
    author_model: str
    critique: CritiqueReport
    footnotes_used: int
    figures_included: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_path": str(self.chapter_path),
            "status": self.status,
            "attempts": self.attempts,
            "author_model": self.author_model,
            "footnotes_used": self.footnotes_used,
            "figures_included": list(self.figures_included),
            "critique": self.critique.to_dict(),
        }


PILOT_CHAPTER_SPEC = ChapterSpec(
    volume_id="vol1_ofa",
    chapter_number=1,
    slug="dall_ovvio_al_numero",
    title="Dall'ovvio al numero: contare, ordinare e l'equilibrio dell'uguale",
    subtitle="Dalle corrispondenze di Galileo e Cantor alle nozioni comuni di Euclide, allo zero posizionale e all'equilibrio dell'uguale",
    node_ids=(
        "numeri.quantita",
        "numeri.ordine",
        "numeri.posizionale",
        "relazioni.uguaglianza-bilancia",
    ),
    concept_queries=("corrispondenza biunivoca", "notazione posizionale", "uguaglianza"),
    extra_block_pks=(13576, 12855, 13818, 28856, 57616, 116781),
    drill_keys=(
        "drill_counting_bijection",
        "drill_number_order",
        "drill_positional_value",
        "drill_equality_balance",
    ),
    svg_diagram_id="balance_and_number_line",
    svg_caption="Corrispondenza biunivoca tra collezioni, successione ordinata sulla retta ed equilibrio simmetrico del segno uguale.",
    target_length_words=1200,
)

CHAPTER_DRAFT_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": [
        "opening_epigraph_quote_id",
        "sections",
        "worked_examples",
        "original_exercises",
        "reconstruction_notes",
    ],
    "properties": {
        "opening_epigraph_quote_id": {"type": "STRING", "nullable": True},
        "sections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["heading", "paragraphs", "include_figure"],
                "properties": {
                    "heading": {"type": "STRING"},
                    "paragraphs": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "include_figure": {"type": "BOOLEAN"},
                },
            },
        },
        "worked_examples": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["title", "problem", "steps", "conclusion"],
                "properties": {
                    "title": {"type": "STRING"},
                    "problem": {"type": "STRING"},
                    "steps": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "conclusion": {"type": "STRING"},
                },
            },
        },
        "original_exercises": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["prompt", "solution_sketch"],
                "properties": {
                    "prompt": {"type": "STRING"},
                    "solution_sketch": {"type": "STRING"},
                },
            },
        },
        "reconstruction_notes": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
}


def is_clean_editorial_quote(quote: str) -> bool:
    """Rifiuta citazioni corrotte da OCR, povere di lettere alfabetiche o con deissi opache."""
    q = " ".join(str(quote or "").split()).strip()
    if len(q) < 18:
        return False
    if _OCR_GARBAGE_RE.search(q) or _BLIND_DEIXIS_QUOTE_RE.search(q):
        return False
    alpha = sum(1 for ch in q if ch.isalpha())
    if alpha / max(1, len(q)) < 0.55:
        return False
    return True


def _sanitize_quote_for_markdown(text: str) -> str:
    """Rimuove newline o sequenze incompatibili col formato nota `«...» — ...`."""
    cleaned = " ".join(str(text or "").split()).strip()
    cleaned = cleaned.replace("—", "-").replace("«", '"').replace("»", '"').strip()
    if cleaned.count('"') % 2 == 1:
        if cleaned.startswith('"'):
            cleaned = cleaned[1:].strip()
        elif cleaned.endswith('"'):
            cleaned = cleaned[:-1].strip()
    return cleaned


def extract_verified_quote_span(
    raw_quote: str,
    block_content: str,
    norm_content: Optional[str] = None,
) -> Optional[str]:
    """Garantisce una sottostringa esatta (4–22 parole) presente in `blocks.norm_content`."""
    haystack = norm_content or normalizza_testo(block_content)
    if not haystack:
        return None

    def _check(candidate: str) -> Optional[str]:
        s = _sanitize_quote_for_markdown(candidate)
        if not is_clean_editorial_quote(s):
            return None
        words = s.split()
        if not (4 <= len(words) <= 23):
            return None
        if normalizza_testo(s) in haystack:
            return s
        return None

    def _trim_dangling(words: List[str]) -> List[str]:
        trimmed = list(words)
        while len(trimmed) > 5 and trimmed[-1].rstrip(",;:\"'").lower() in _DANGLING_TAIL_WORDS:
            trimmed.pop()
        return trimmed

    direct = _check(raw_quote)
    if direct is not None:
        direct_words = direct.split()
        if not direct.rstrip().endswith((".", "!", "?")):
            trimmed_words = _trim_dangling(direct_words)
            if len(trimmed_words) < len(direct_words):
                cand = _check(" ".join(trimmed_words))
                if cand is not None:
                    return cand
        return direct

    # Taglia progressivamente se la citazione supera 22 parole o differisce solo in coda/testa
    words_raw = _sanitize_quote_for_markdown(raw_quote).split()
    for length in range(min(22, len(words_raw)), 5, -1):
        slice_words = _trim_dangling(words_raw[:length])
        cand = _check(" ".join(slice_words))
        if cand is not None:
            return cand
    if len(words_raw) >= 8:
        for start in range(1, len(words_raw) - 5):
            slice_words = _trim_dangling(words_raw[start : min(len(words_raw), start + 18)])
            cand = _check(" ".join(slice_words))
            if cand is not None:
                return cand

    # Estrazione di ripiego di una frase pulita dal corpo (saltando intestazioni di pagina)
    sentences = re.split(r"(?<=[.;!?])\s+|\n{2,}", str(block_content or ""))
    for sent in sentences:
        s_clean = _sanitize_quote_for_markdown(sent)
        if re.match(r"^(?:~?\d+\s|LEZIONE\s+|CAPITOLO\s+|SEZIONE\s+|PAGINA\s+)", s_clean):
            continue
        sw = s_clean.split()
        if len(sw) < 6:
            continue
        if len(sw) <= 20:
            cand = _check(" ".join(sw))
            if cand is not None:
                return cand
        else:
            cand = _check(" ".join(sw[:18]))
            if cand is not None:
                return cand
    return None


def assemble_chapter_dossier(
    conn: sqlite3.Connection,
    spec: ChapterSpec,
    *,
    chapter_dir: Optional[Path | str] = None,
    assets_dir: Path | str = DEFAULT_ASSETS_DIR,
    figures_root: Path | str = DEFAULT_FIGURES_DIR,
    max_quotes: int = 14,
) -> ChapterDossier:
    """Raccoglie tutte le evidenze verificate del corpus per il capitolo senza chiamate LLM."""
    conn.row_factory = sqlite3.Row
    chapter_dir_path = Path(chapter_dir) if chapter_dir else (DEFAULT_BOOKS_DIR / spec.volume_id)

    raw_candidates: List[Dict[str, Any]] = []
    seen_block_pks: set[int] = set()

    # 1. Blocchetti espliciti curatoriali (`spec.extra_block_pks`) con massima priorità
    if spec.extra_block_pks:
        clean_extra = [int(pk) for pk in spec.extra_block_pks if int(pk) > 0]
        if clean_extra:
            ph = ",".join("?" for _ in clean_extra)
            eu_extra = conn.execute(
                f"""
                SELECT eu.block_pk, eu.stmt, eu.verbatim_quote, eu.mode, eu.vs_dispute
                FROM epistemic_units eu
                JOIN blocks b ON b.block_pk = eu.block_pk
                WHERE eu.block_pk IN ({ph}) AND b.is_active = 1
                ORDER BY eu.block_pk ASC, eu.unit_pk ASC
                """,
                tuple(clean_extra),
            ).fetchall()
            extra_units_map: Dict[int, List[sqlite3.Row]] = {}
            for ur in eu_extra:
                extra_units_map.setdefault(int(ur["block_pk"]), []).append(ur)
            for bpk in clean_extra:
                if bpk in seen_block_pks:
                    continue
                seen_block_pks.add(bpk)
                ulist = extra_units_map.get(bpk, [])
                best_u = max(
                    ulist,
                    key=lambda u: (1 if u["vs_dispute"] else 0, len(str(u["verbatim_quote"] or ""))),
                ) if ulist else None
                raw_candidates.append(
                    {
                        "block_pk": bpk,
                        "hint_quote": str(best_u["verbatim_quote"]) if best_u else "",
                        "stmt": str(best_u["stmt"]) if best_u else "",
                        "mode": str(best_u["mode"]) if best_u else "defines",
                        "when_label": "Fonte canonica",
                        "vs_dispute": str(best_u["vs_dispute"]) if (best_u and best_u["vs_dispute"]) else None,
                        "is_wb": False,
                    }
                )

    # 2. Ponti "Libro Sbagliato" validati dai nodi target
    for nid in spec.node_ids:
        for br in get_bridges_for_node(conn, nid, only_validated=True, prefix_fallback=False):
            bpk = int(br["block_pk"])
            if bpk in seen_block_pks:
                continue
            seen_block_pks.add(bpk)
            raw_candidates.append(
                {
                    "block_pk": bpk,
                    "hint_quote": "",
                    "stmt": str(br.get("mech") or ""),
                    "mode": "applies",
                    "when_label": str(br.get("year") or "Classico"),
                    "vs_dispute": None,
                    "is_wb": True,
                }
            )

    # 3. Decompressore sinottico cronologico e modale per ciascun concetto chiave
    for cq in spec.concept_queries:
        try:
            rep = decompress_concept(conn, cq, max_entries=10, max_per_book=2)
        except Exception:
            continue
        # Privilegia prima le controversie (`disputes`), poi il resto della timeline
        dispute_pks = {d.block_pk for d in rep.disputes}
        ordered_entries = sorted(
            rep.timeline,
            key=lambda e: (
                0 if e.block_pk in dispute_pks else 1,
                -(e.relevance_score),
                e.block_pk,
            ),
        )
        for e in ordered_entries:
            if e.block_pk in seen_block_pks:
                continue
            seen_block_pks.add(e.block_pk)
            raw_candidates.append(
                {
                    "block_pk": e.block_pk,
                    "hint_quote": e.verbatim_quote,
                    "stmt": e.stmt,
                    "mode": e.mode,
                    "when_label": e.when_label,
                    "vs_dispute": e.vs_dispute,
                    "is_wb": False,
                }
            )

    # Caricamento batch di `blocks`, `books`, eventuale `book_spectrum_meta` e `epistemic_units` di ripiego
    has_spec = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'book_spectrum_meta'"
        ).fetchone()
        is not None
    )
    cand_pks = [int(c["block_pk"]) for c in raw_candidates]
    block_rows: Dict[int, sqlite3.Row] = {}
    fallback_units: Dict[int, List[sqlite3.Row]] = {}

    for i in range(0, len(cand_pks), 500):
        chunk = cand_pks[i : i + 500]
        ph = ",".join("?" for _ in chunk)
        meta_col = "bsm.primary_discipline, COALESCE(bsm.quality_tier, 'canonical_book') AS quality_tier" if has_spec else "NULL AS primary_discipline, 'canonical_book' AS quality_tier"
        meta_join = "LEFT JOIN book_spectrum_meta bsm ON bsm.book_pk = bk.book_pk" if has_spec else ""
        for br in conn.execute(
            f"""
            SELECT b.block_pk, b.block_uid, b.book_pk, b.page_start, b.printed_page,
                   b.content, b.norm_content,
                   bk.title AS book_title, bk.author,
                   {meta_col}
            FROM blocks b
            JOIN books bk ON bk.book_pk = b.book_pk
            {meta_join}
            WHERE b.block_pk IN ({ph}) AND b.is_active = 1 AND bk.is_active = 1
            """,
            tuple(chunk),
        ).fetchall():
            if str(br["quality_tier"]) in {"non_book_noise", "reference_manual"}:
                continue
            block_rows[int(br["block_pk"])] = br

        for ur in conn.execute(
            f"""
            SELECT block_pk, stmt, verbatim_quote, mode, vs_dispute
            FROM epistemic_units
            WHERE block_pk IN ({ph})
            ORDER BY block_pk ASC, unit_pk ASC
            """,
            tuple(chunk),
        ).fetchall():
            fallback_units.setdefault(int(ur["block_pk"]), []).append(ur)

    verified_quotes: List[VerifiedQuoteCandidate] = []
    book_use_count: Dict[int, int] = {}

    for cand in raw_candidates:
        if len(verified_quotes) >= max_quotes:
            break
        bpk = int(cand["block_pk"])
        brow = block_rows.get(bpk)
        if brow is None:
            continue
        book_pk = int(brow["book_pk"])
        if book_use_count.get(book_pk, 0) >= 2:
            continue

        hint = cand["hint_quote"]
        stmt = cand["stmt"]
        fu_list = fallback_units.get(bpk, [])
        content_raw = str(brow["content"] or "")
        norm_c = brow["norm_content"]

        span: Optional[str] = None
        if hint:
            span = extract_verified_quote_span(hint, content_raw, norm_c)
        if span is None and fu_list:
            for fu in fu_list:
                fq = str(fu["verbatim_quote"] or "")
                cand_span = extract_verified_quote_span(fq, content_raw, norm_c)
                if cand_span is not None:
                    span = cand_span
                    if not stmt or cand["is_wb"]:
                        stmt = str(fu["stmt"] or stmt)
                    break
        if span is None:
            span = extract_verified_quote_span("", content_raw, norm_c)
        if span is None:
            continue

        q_id = f"Q{len(verified_quotes) + 1}"
        book_use_count[book_pk] = book_use_count.get(book_pk, 0) + 1
        verified_quotes.append(
            VerifiedQuoteCandidate(
                quote_id=q_id,
                block_pk=bpk,
                block_uid=str(brow["block_uid"]),
                book_pk=book_pk,
                book_title=str(brow["book_title"]),
                author=brow["author"],
                page=brow["page_start"],
                printed_page=brow["printed_page"],
                primary_discipline=brow["primary_discipline"],
                mode=cand["mode"],
                when_label=cand["when_label"],
                stmt=stmt or f"Passaggio verificato da {brow['book_title']}.",
                quote=span,
                vs_dispute=cand["vs_dispute"],
                is_wrong_book_bridge=bool(cand["is_wb"]),
            )
        )

    # 4. Figure reali dal corpus (se disponibili per i blocchi) + SVG controllato del capitolo
    corpus_figs = find_corpus_figures_for_blocks(
        conn,
        [q.block_pk for q in verified_quotes],
        figures_root=figures_root,
        chapter_dir=chapter_dir_path,
        max_figures=1,
    )
    svg_asset = save_svg_diagram(
        spec.svg_diagram_id,
        assets_dir,
        filename=f"{spec.chapter_number:02d}_{spec.svg_diagram_id}.svg",
        title=spec.title,
        caption=spec.svg_caption or spec.subtitle,
        chapter_dir=chapter_dir_path,
    )
    all_figures = tuple([svg_asset, *corpus_figs])

    # 5. Esercizi verificati SymPy sui `drill_keys`
    drills: List[Dict[str, Any]] = []
    for idx, dk in enumerate(spec.drill_keys):
        nid = spec.node_ids[idx] if idx < len(spec.node_ids) else spec.node_ids[0]
        dr_list = generate_drill_set(nid, dk, count=2, seed=100 + spec.chapter_number * 13 + idx)
        if dr_list:
            drills.append({**dr_list[0], "drill_key": dk})

    # 6. Radar silenzioso degli obiettivi ministeriali K-13 coperti dai nodi del capitolo
    objectives_list: List[str] = []
    has_obj_map = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'objective_corpus_map'"
        ).fetchone()
        is not None
    )
    if has_obj_map:
        for orow in conn.execute(
            "SELECT grade, nucleus, mapped_dag_node_ids_json FROM objective_corpus_map WHERE cycle IN ('primaria', 'secondaria_i_grado', 'secondaria_ii_grado_licei')"
        ).fetchall():
            nids = set(json.loads(orow["mapped_dag_node_ids_json"] or "[]"))
            if nids.intersection(spec.node_ids):
                lbl = f"{orow['grade']} — {orow['nucleus']}"
                if lbl not in objectives_list:
                    objectives_list.append(lbl)

    return ChapterDossier(
        spec=spec,
        quotes=tuple(verified_quotes),
        figures=all_figures,
        sympy_drills=tuple(drills),
        curriculum_objectives=tuple(objectives_list[:10]),
    )


def build_author_chapter_prompt(
    dossier: ChapterDossier,
    *,
    previous_feedback: Optional[str] = None,
) -> str:
    """Costruisce il prompt editoriale autoriale (nobilitazione dell'ovvio, la carne genera l'osso)."""
    spec = dossier.spec
    quotes_block = "\n".join(
        f"- [{q.quote_id}] ({q.when_label} | {q.mode} | {q.source_label()}):\n"
        f"  Enunciato sintetico: {q.stmt}\n"
        f"  Citazione esatta verbatim: «{q.quote}»"
        + (f"\n  Controversia (`vs`): {q.vs_dispute}" if q.vs_dispute else "")
        for q in dossier.quotes
    )
    drills_block = "\n".join(
        f"- ({d['drill_key']}) {d['prompt']} -> Risposta esatta: `{d['expected']}` | Spiegazione: {d['explanation']}"
        for d in dossier.sympy_drills
    )
    radar_block = (
        "\n".join(f"- {o}" for o in dossier.curriculum_objectives)
        if dossier.curriculum_objectives
        else "- Copertura curricolare dalle origini elementari al calcolo simbolico"
    )
    revision_block = (
        "\n\nFEEDBACK OBBLIGATORIO DA RISOLVERE RISPETTO ALLA BOZZA PRECEDENTE:\n"
        f"{previous_feedback}\n"
        if previous_feedback
        else ""
    )

    return (
        "Sei l'autore principale della collana scientifica di `resuscipack`: stai scrivendo un vero libro continuo\n"
        "intitolato *Dall'Ovvio al Simbolo*, rivolto a studenti universitari e lettori adulti che vogliono capire la matematica\n"
        "dalle radici profonde fino al rigore formale (stile saggistico limpido, colto e concreto alla Bellissima / Frajese / Prodi).\n\n"
        f"TITOLO CAPITOLO {spec.chapter_number}: {spec.title}\n"
        f"SOTTOTITOLO: {spec.subtitle}\n"
        f"LUNGHEZZA BERSAGLIO: circa {spec.target_length_words} parole complessive (minimo assoluto 750 parole di prosa).\n\n"
        "REGOLE EDITORIALI NON NEGOZIABILI:\n"
        "1. PROSA CONTINUA ADULTA, SOBRIA E NOBILITAZIONE DELL'OVVIO: scrivi 4–6 sezioni (`sections`) composte da veri paragrafi narrativi\n"
        "   ed esplicativi in italiano limpido (almeno 6–8 paragrafi sostanziosi complessivi). Stile saggistico calmo, preciso e concreto alla\n"
        "   Bellissima / Prodi / Frajese: evita aggettivi melodrammatici ('abisso vertiginoso', 'spietata', 'trionfo dell'intelletto'),\n"
        "   tono da sussidiario infantile, elenchi burocratici al posto del ragionamento e formule vuote da AI ('In questo capitolo scopriremo...').\n"
        "2. LA CARNE GENERA L'OSSO, ZERO SALTI LOGICI E RIGORE LATEX: parti sempre dalle idee concrete, storiche e dalle controversie vive nei testi del dossier,\n"
        "   e porta il lettore fino alle definizioni matematiche precise, al simbolismo formale e alle dimostrazioni complete.\n"
        "   Definisci esplicitamente ogni nuovo concetto o notazione (`permutazione`, `fattoriale` $n!$, `relazione di equivalenza`, `notazione posizionale`, ecc.) dai principi primi PRIMA di usarlo nei calcoli.\n"
        "   Scrivi OGNI espressione matematica in LaTeX pulito (`$6x + 3 = 51$`, `$2^4$`, `$3! = 6$`, `$\\{1, 2, 3\\}$`), mai con sintassi informatica ASCII come `6*x`.\n"
        "3. CITAZIONI RIGOROSAMENTE ANCORATE: integra nella prosa almeno 5 fonti distinte dal dossier qui sotto inserendo nel punto esatto del testo\n"
        "   il segnaposto fra parentesi quadre `[Q1]`, `[Q2]`, ecc. NON inventare altri tag tra quadre `[1]` o citazioni non presenti nel dossier.\n"
        "   Sii rigorosamente fedele al significato letterale della citazione nel contesto della fonte: non forzarne l'interpretazione e non attribuirle tesi estranee.\n"
        "4. ZERO GERGO INTERNO E ZERO METATESTO EDITORIALE: è severamente vietato scrivere nel testo codici come `block_pk`, `block_uid`, `Strato`, `Gate`,\n"
        "   `P0.5`, `G00`, `score 0.9`, `TASK-`, titoli da vecchia scheda (`Contesto`, `Enunciati`, `Decisione`, `Alternative`, `Conseguenze`),\n"
        "   o qualunque riferimento meta-editoriale a 'bozza precedente', 'correzione', 'revisore' o 'direttive editoriali': ogni riga deve leggere come un libro stampato finito.\n"
        "5. ZERO DEISSI OPACHE: mai scrivere 'il Nostro', 'suddetto autore', 'ivi', 'ibidem', 'op. cit.', 'vedi sopra'.\n"
        "6. FIGURA EDITORIALE: in almeno una sezione imposta `include_figure: true` dove il testo introduce e commenta esplicitamente i contenuti del diagramma (bilancia simmetrica ed equilibrio, corrispondenza biunivoca, retta dei numeri).\n"
        "7. PALESTRA SIMBOLICA ANTI-POLTRONA E 3 COLORI: includi `worked_examples` (2–3 calcoli/dimostrazioni svolti passo passo senza salti logici),\n"
        "   `original_exercises` (3–5 esercizi originali attivi e non ripetitivi coerenti coi modelli SymPy sotto, includendo almeno una verifica concettuale o controesempio — es. riconoscere quando una corrispondenza NON è biunivoca; in `solution_sketch` scrivi una traccia concisa senza ripetere 'Traccia di verifica:') e `reconstruction_notes` (2–4 note trasparenti e impersonali sulle scelte formali del capitolo).\n"
        f"{revision_block}\n"
        "RADAR CURRICOLARE SILENZIOSO (temi scolastici da coprire naturalmente, senza citarne i codici):\n"
        f"{radar_block}\n\n"
        "DOSSIER DI FONTI PRE-VERIFICATE (cita esclusivamente con `[Q1]`, `[Q2]`, ...):\n"
        f"{quotes_block}\n\n"
        "PALESTRA SIMBOLICA DI RIFERIMENTO (SymPy):\n"
        f"{drills_block}\n\n"
        "Restituisci SOLO JSON valido conforme allo schema richiesto."
    )


def _strip_unauthorized_square_refs(text: str, allowed_q_nums: set[int]) -> str:
    def _repl(m: re.Match[str]) -> str:
        q_num = int(m.group(1))
        return m.group(0) if q_num in allowed_q_nums else ""

    # Sostituisci solo [Qn] validi e rimuovi eventuali [Qn] inesistenti o [n] numerici spuri
    cleaned = _Q_TAG_RE.sub(_repl, text)
    cleaned = re.sub(r"(?<!\^)\[\d+\](?!:|\()", "", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned.strip()


def compile_chapter_markdown(
    draft: Mapping[str, Any],
    dossier: ChapterDossier,
    *,
    status: str = "bozza",
) -> Tuple[str, int, Tuple[str, ...]]:
    """Compila il JSON autoriale e il dossier pre-verificato in Markdown editoriale verificabile dai 6 Gate."""
    quotes_by_id: Dict[str, VerifiedQuoteCandidate] = {q.quote_id: q for q in dossier.quotes}
    allowed_q_nums = {int(qid[1:]) for qid in quotes_by_id if qid.startswith("Q") and qid[1:].isdigit()}

    q_to_fn: Dict[str, int] = {}
    ordered_used_quotes: List[Tuple[int, VerifiedQuoteCandidate]] = []

    def _bind_q_tags(raw_text: str) -> str:
        sanitized = _strip_unauthorized_square_refs(str(raw_text or "").strip(), allowed_q_nums)

        def _swap(m: re.Match[str]) -> str:
            qid = f"Q{int(m.group(1))}"
            cand = quotes_by_id.get(qid)
            if cand is None:
                return ""
            if qid not in q_to_fn:
                fn_num = len(ordered_used_quotes) + 1
                q_to_fn[qid] = fn_num
                ordered_used_quotes.append((fn_num, cand))
            return f"[^{q_to_fn[qid]}]"

        return _Q_TAG_RE.sub(_swap, sanitized)

    body_lines: List[str] = []
    spec = dossier.spec

    body_lines.append(f"# Capitolo {spec.chapter_number} — {spec.title}")
    if spec.subtitle:
        body_lines.append("")
        body_lines.append(f"*{spec.subtitle}*")

    ep_id = str(draft.get("opening_epigraph_quote_id") or "").strip().upper()
    if ep_id in quotes_by_id:
        ep_cand = quotes_by_id[ep_id]
        ep_ref = _bind_q_tags(f"[{ep_id}]")
        body_lines.extend(
            [
                "",
                f"> *«{ep_cand.quote}»* — {ep_cand.source_label()} {ep_ref}",
            ]
        )

    sections = list(draft.get("sections") or [])
    figures_queue = list(dossier.figures)
    figures_placed: List[str] = []

    def _pop_figure_markdown() -> List[str]:
        if not figures_queue:
            return []
        fig = figures_queue.pop(0)
        figures_placed.append(fig.rel_path)
        return [
            "",
            f"![{fig.caption}]({fig.rel_path})",
            f"*{fig.caption}*",
        ]

    for idx, sec in enumerate(sections):
        if not isinstance(sec, Mapping):
            continue
        heading = _bind_q_tags(str(sec.get("heading") or f"Sezione {idx + 1}"))
        body_lines.extend(["", f"## {heading}"])
        for p in sec.get("paragraphs") or []:
            para = _bind_q_tags(str(p))
            if para:
                body_lines.extend(["", para])
        if sec.get("include_figure") and figures_queue:
            body_lines.extend(_pop_figure_markdown())

    # Assicura che almeno la prima figura/SVG venga sempre inserita se nessuna sezione aveva include_figure=True
    if not figures_placed and figures_queue:
        body_lines.extend(_pop_figure_markdown())

    # Sezione esempi svolti ed esercizi operativi ("la carne genera l'osso")
    worked = list(draft.get("worked_examples") or [])
    orig_ex = list(draft.get("original_exercises") or [])
    if worked or orig_ex:
        body_lines.extend(["", "## Dal ragionamento al simbolo: esempi e verifiche"])
        for ex in worked:
            if not isinstance(ex, Mapping):
                continue
            title_ex = _bind_q_tags(str(ex.get("title") or "Esempio svolto"))
            prob_ex = _bind_q_tags(str(ex.get("problem") or ""))
            concl_ex = _bind_q_tags(str(ex.get("conclusion") or ""))
            body_lines.extend(["", f"### {title_ex}", "", prob_ex])
            for st_idx, step_txt in enumerate(ex.get("steps") or [], start=1):
                body_lines.append(f"{st_idx}. {_bind_q_tags(str(step_txt))}")
            if concl_ex:
                body_lines.extend(["", f"**Conclusione.** {concl_ex}"])

        if orig_ex:
            body_lines.extend(["", "### Esercizi di verifica attiva"])
            for ex_idx, ox in enumerate(orig_ex, start=1):
                if not isinstance(ox, Mapping):
                    continue
                pr_txt = _bind_q_tags(str(ox.get("prompt") or ""))
                if pr_txt:
                    body_lines.append(f"{ex_idx}. {pr_txt}")

    # Apparato delle fonti a 3 colori (sempre presente e verificato)
    body_lines.extend(["", "## Apparato delle fonti", "", "### [Verificato sul testo]"])
    if ordered_used_quotes:
        for fn_num, qcand in ordered_used_quotes:
            body_lines.append(
                f"[^{fn_num}]: [block_pk={qcand.block_pk} | block_uid={qcand.block_uid}] "
                f"«{qcand.quote}» — {qcand.source_label()}"
            )
    else:
        body_lines.append("- Nessuna citazione testuale ancora collegata.")

    body_lines.extend(["", "### [Ricostruzione matematica / addestramento]"])
    rec_notes = [str(n).strip() for n in (draft.get("reconstruction_notes") or []) if str(n).strip()]
    if not rec_notes:
        rec_notes = [
            "Il raccordo simbolico e le formule esplicite collegano le fonti storiche citate al formalismo richiesto dal percorso matematico."
        ]
    for fig in dossier.figures:
        if fig.kind == "svg_diagram" and fig.rel_path in figures_placed:
            rec_notes.append(f"Diagramma geometrico-simbolico controllato (`{fig.diagram_id}`): {fig.caption}")
    for note_txt in rec_notes:
        # Evita accidentalmente rimandi [Qn] non collegati dentro le note ricostruttive
        clean_note = _strip_unauthorized_square_refs(note_txt, set())
        body_lines.append(f"- {clean_note}")

    body_lines.extend(["", "### [Esercizi originali]"])
    for ox in orig_ex:
        if not isinstance(ox, Mapping):
            continue
        ox_prompt = _strip_unauthorized_square_refs(str(ox.get("prompt") or "").strip(), set())
        if not ox_prompt:
            continue
        sol_raw = re.sub(
            r"^\s*Traccia\s+di\s+verifica\s*:\s*",
            "",
            str(ox.get("solution_sketch") or "").strip(),
            flags=re.IGNORECASE,
        )
        sol_clean = _strip_unauthorized_square_refs(sol_raw, set())
        if sol_clean:
            body_lines.append(f"- {ox_prompt} — *Traccia di verifica:* {sol_clean}")
        else:
            body_lines.append(f"- {ox_prompt}")
    for dr in dossier.sympy_drills:
        body_lines.append(
            f"- **Palestra simbolica (`{dr['drill_key']}`):** {dr['prompt']} *(Risposta verificata: `{dr['expected']}`)*"
        )

    fonti_yaml = [
        {
            "block_pk": qcand.block_pk,
            "block_uid": qcand.block_uid,
            "citazione": qcand.quote,
        }
        for _, qcand in ordered_used_quotes
    ]
    frontmatter = {
        "tipo": "capitolo_libro",
        "id": f"{spec.volume_id}.cap{spec.chapter_number:02d}",
        "volume": spec.volume_id,
        "capitolo": spec.chapter_number,
        "titolo": spec.title,
        "sottotitolo": spec.subtitle,
        "nodi_coperti": list(spec.node_ids),
        "drill_keys": list(spec.drill_keys),
        "stato": status,
        "aggiornato": date.today().isoformat(),
        "fonti": fonti_yaml,
    }
    yaml_str = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    full_markdown = f"---\n{yaml_str}\n---\n\n" + "\n".join(body_lines).strip() + "\n"
    return full_markdown, len(ordered_used_quotes), tuple(figures_placed)


def _update_frontmatter_status(chapter_path: Path, new_status: str) -> None:
    text = chapter_path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
    if not m:
        return
    meta = yaml.safe_load(m.group(1)) or {}
    meta["stato"] = new_status
    yaml_str = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    chapter_path.write_text(f"---\n{yaml_str}\n---\n{m.group(2)}", encoding="utf-8")


def generate_and_verify_chapter(
    spec: ChapterSpec,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    output_dir: Optional[Path | str] = None,
    assets_dir: Path | str = DEFAULT_ASSETS_DIR,
    figures_root: Path | str = DEFAULT_FIGURES_DIR,
    provider: str = "vertex",
    author_model: str = "gemini-3.1-pro-preview",
    critic_model: str = "gemini-3-flash-preview",
    author_llm: Optional[JsonLlmCallable] = None,
    critic_llm: Optional[JsonLlmCallable] = None,
    max_revisions: int = 2,
    min_prose_words: int = 500,
    min_continuous_paragraphs: int = 4,
) -> CompiledChapterResult:
    """Genera un capitolo continuo dal corpus reale, esegue la rilettura critica e lo promuove se approvato."""
    dest_dir = Path(output_dir) if output_dir else (DEFAULT_BOOKS_DIR / spec.volume_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = dest_dir / f"{spec.chapter_number:02d}_{spec.slug}.md"

    conn = connect_corpus_db(db_path, read_only=True)
    try:
        dossier = assemble_chapter_dossier(
            conn,
            spec,
            chapter_dir=dest_dir,
            assets_dir=assets_dir,
            figures_root=figures_root,
        )
    finally:
        conn.close()

    if not dossier.quotes:
        raise RuntimeError(
            f"Impossibile generare il capitolo {spec.slug!r}: nessuna citazione verbatim valida nel dossier."
        )

    previous_feedback: Optional[str] = None
    last_critique: Optional[CritiqueReport] = None
    used_author_model = "injected-author-llm" if author_llm is not None else author_model
    footnotes_used = 0
    figures_placed: Tuple[str, ...] = ()

    for attempt in range(1, max(1, int(max_revisions)) + 2):
        prompt = build_author_chapter_prompt(dossier, previous_feedback=previous_feedback)
        if author_llm is not None:
            draft_payload = author_llm(prompt, CHAPTER_DRAFT_RESPONSE_SCHEMA)
        else:
            draft_payload, used_author_model = call_editorial_json_llm(
                prompt,
                CHAPTER_DRAFT_RESPONSE_SCHEMA,
                provider=provider,
                model=author_model,
                thinking_budget=2048,
                max_output_tokens=32768,
                temperature=0.25,
                timeout_seconds=240,
            )

        compiled_md, footnotes_used, figures_placed = compile_chapter_markdown(
            draft_payload, dossier, status="bozza"
        )
        chapter_path.write_text(compiled_md, encoding="utf-8")

        critique = audit_and_critique_chapter(
            chapter_path,
            dossier.to_critic_sources_summary(),
            db_path=db_path,
            provider=provider,
            critic_model=critic_model,
            critic_llm=critic_llm,
            min_prose_words=min_prose_words,
            min_continuous_paragraphs=min_continuous_paragraphs,
        )
        last_critique = critique

        if critique.approved:
            _update_frontmatter_status(chapter_path, "pubblicato")
            return CompiledChapterResult(
                chapter_path=chapter_path,
                status="pubblicato",
                attempts=attempt,
                author_model=used_author_model,
                critique=critique,
                footnotes_used=footnotes_used,
                figures_included=figures_placed,
            )

        previous_feedback = critique.blocking_feedback_text() or critique.summary

    assert last_critique is not None
    return CompiledChapterResult(
        chapter_path=chapter_path,
        status="bozza",
        attempts=max(1, int(max_revisions)) + 1,
        author_model=used_author_model,
        critique=last_critique,
        footnotes_used=footnotes_used,
        figures_included=figures_placed,
    )


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Motore Autoriale dei Nuovi Libri Continui (TASK-BOOK-01)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso a pack_corpus.db")
    parser.add_argument("--out-dir", type=Path, default=None, help="Cartella di destinazione capitoli")
    parser.add_argument("--pilot", action="store_true", help="Genera e verifica il Capitolo 1 pilota del Volume I")
    parser.add_argument("--dossier-only", action="store_true", help="Ispeziona solo il dossier pre-verificato senza chiamare LLM")
    parser.add_argument("--provider", type=str, default="vertex", choices=("vertex", "gemini", "deepseek"))
    parser.add_argument("--author-model", type=str, default="gemini-3.1-pro-preview")
    parser.add_argument("--critic-model", type=str, default="gemini-3-flash-preview")
    parser.add_argument("--max-revisions", type=int, default=2)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.pilot and not args.dossier_only:
        parser.error("Specifica `--pilot` o `--dossier-only`.")

    if args.dossier_only:
        conn = connect_corpus_db(args.db, read_only=True)
        try:
            dos = assemble_chapter_dossier(conn, PILOT_CHAPTER_SPEC)
            print(
                json.dumps(
                    {
                        "title": dos.spec.title,
                        "quotes": [q.to_dict() for q in dos.quotes],
                        "figures": [f.to_dict() for f in dos.figures],
                        "sympy_drills_count": len(dos.sympy_drills),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        finally:
            conn.close()
        return 0

    result = generate_and_verify_chapter(
        PILOT_CHAPTER_SPEC,
        db_path=args.db,
        output_dir=args.out_dir,
        provider=args.provider,
        author_model=args.author_model,
        critic_model=args.critic_model,
        max_revisions=args.max_revisions,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.critique.approved else 1


__all__ = [
    "CHAPTER_DRAFT_RESPONSE_SCHEMA",
    "ChapterDossier",
    "ChapterSpec",
    "CompiledChapterResult",
    "DEFAULT_BOOKS_DIR",
    "PILOT_CHAPTER_SPEC",
    "VerifiedQuoteCandidate",
    "assemble_chapter_dossier",
    "build_author_chapter_prompt",
    "compile_chapter_markdown",
    "extract_verified_quote_span",
    "generate_and_verify_chapter",
    "is_clean_editorial_quote",
]

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
