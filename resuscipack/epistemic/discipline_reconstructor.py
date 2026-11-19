"""Motore di Ricostruzione delle Discipline dal Basso ("Il Libro Sbagliato" — Livello B, ADR-0004, TASK-SPEC-02).

Data una qualunque disciplina target `D`, raccoglie e ordina i passaggi verificati ad alta densità
in cui `D` emerge dentro libri la cui disciplina primaria e `surface_domain` appartengono ad *altre*
discipline (es. "La Geografia dentro Marconi, Laplace, Volta, Torricelli, Galileo, Eco, Cartesio").

Opera in sola lettura su `book_discipline_spectrum`, `book_spectrum_meta`, `block_metadata_v22`,
`blocks` e `epistemic_units`, con costo API 0 EUR e zero troncamenti di default.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..corpus.schema import DEFAULT_DB_PATH, connect_corpus_db
from .schema_v21 import ALL_MACRO_DISCIPLINES, MacroDiscipline
from .spectrum import (
    is_residual_paratext_block,
    label_for_discipline,
    resolve_macro_discipline,
)

# Mappa completa delle 22 MacroDiscipline -> `books.surface_domain` nativi da escludere come "Libri Giusti"
DISCIPLINE_NATIVE_SURFACE_DOMAINS: Dict[str, frozenset[str]] = {
    MacroDiscipline.MATEMATICA.value: frozenset({"matematica"}),
    MacroDiscipline.LOGICA.value: frozenset(),
    MacroDiscipline.INFORMATICA.value: frozenset({"informatica"}),
    MacroDiscipline.CRITTOGRAFIA_SICUREZZA.value: frozenset({"informatica"}),
    MacroDiscipline.FISICA.value: frozenset({"fisica_ingegneria"}),
    MacroDiscipline.ASTRONOMIA_COSMOLOGIA.value: frozenset(),
    MacroDiscipline.CHIMICA_MATERIALI.value: frozenset(),
    MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA.value: frozenset({"medicina_biologia"}),
    MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value: frozenset(),
    MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value: frozenset(),
    MacroDiscipline.INGEGNERIA_MECCANICA_ELETTRONICA.value: frozenset({"fisica_ingegneria"}),
    MacroDiscipline.TELECOMUNICAZIONI_SEGNALI.value: frozenset({"fisica_ingegneria"}),
    MacroDiscipline.STORIA_POLITICA_MILITARE.value: frozenset({"storia_della_scienza"}),
    MacroDiscipline.ECONOMIA_COMMERCIO_ASSICURAZIONI.value: frozenset(),
    MacroDiscipline.DIRITTO_ISTITUZIONI.value: frozenset(),
    MacroDiscipline.FILOSOFIA_EPISTEMOLOGIA.value: frozenset({"filosofia_scienze_umane"}),
    MacroDiscipline.LETTERATURA_RETORICA_FILOLOGIA.value: frozenset({"arte_letteratura_antichita"}),
    MacroDiscipline.MUSICA_ACUSTICA.value: frozenset({"musica_acustica"}),
    MacroDiscipline.ARTE_ARCHITETTURA_DISEGNO.value: frozenset({"arte_letteratura_antichita"}),
    MacroDiscipline.PSICOLOGIA_PEDAGOGIA_SOCIETA.value: frozenset(),
    MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value: frozenset({"botanica_scienze_naturali"}),
    MacroDiscipline.ARTI_PRATICHE_ARTIGIANATO.value: frozenset(),
}

_SPATIAL_DISCIPLINES = frozenset(
    {
        MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
        MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value,
    }
)

_UNIT_KIND_PRIORITY: Dict[str, int] = {
    "exp": 5,
    "dispute": 4,
    "claim": 4,
    "def": 3,
    "thm": 3,
    "counterex": 2,
    "proc": 2,
    "proof_idea": 2,
}


@dataclass(frozen=True)
class ReconstructedPassage:
    """Singolo passaggio ad alta densità della disciplina target estratto da un 'Libro Sbagliato'."""

    block_pk: int
    block_uid: str
    book_pk: int
    book_title: str
    author: Optional[str]
    year: Optional[int]
    surface_domain: str
    primary_discipline: Optional[str]
    primary_discipline_label: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    printed_page: Optional[str]
    section_title: str
    char_count: int
    macro_disciplines: Tuple[str, ...]
    topics: Tuple[str, ...]
    places: Tuple[str, ...]
    historical_years: Tuple[str, ...]
    best_stmt: str
    verbatim_quote: str
    units_count: int
    density_score: float
    interdisciplinary_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_pk": self.block_pk,
            "block_uid": self.block_uid,
            "book_pk": self.book_pk,
            "book_title": self.book_title,
            "author": self.author,
            "year": self.year,
            "surface_domain": self.surface_domain,
            "primary_discipline": self.primary_discipline,
            "primary_discipline_label": self.primary_discipline_label,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "printed_page": self.printed_page,
            "section_title": self.section_title,
            "char_count": self.char_count,
            "macro_disciplines": list(self.macro_disciplines),
            "topics": list(self.topics),
            "places": list(self.places),
            "historical_years": list(self.historical_years),
            "best_stmt": self.best_stmt,
            "verbatim_quote": self.verbatim_quote,
            "units_count": self.units_count,
            "density_score": self.density_score,
            "interdisciplinary_reason": self.interdisciplinary_reason,
        }


@dataclass(frozen=True)
class ReconstructedBookContribution:
    """Contributo complessivo di un 'Libro Sbagliato' al mosaico della disciplina target."""

    book_pk: int
    book_uid: str
    book_title: str
    author: Optional[str]
    year: Optional[int]
    surface_domain: str
    quality_tier: str
    primary_discipline: Optional[str]
    primary_discipline_label: Optional[str]
    primary_share_pct: float
    target_block_count: int
    target_coverage_pct: float
    target_share_pct: float
    book_surprise_score: float
    top_places: Tuple[str, ...]
    top_topics: Tuple[str, ...]
    interdisciplinary_reason: str
    passages: Tuple[ReconstructedPassage, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "book_pk": self.book_pk,
            "book_uid": self.book_uid,
            "book_title": self.book_title,
            "author": self.author,
            "year": self.year,
            "surface_domain": self.surface_domain,
            "quality_tier": self.quality_tier,
            "primary_discipline": self.primary_discipline,
            "primary_discipline_label": self.primary_discipline_label,
            "primary_share_pct": self.primary_share_pct,
            "target_block_count": self.target_block_count,
            "target_coverage_pct": self.target_coverage_pct,
            "target_share_pct": self.target_share_pct,
            "book_surprise_score": self.book_surprise_score,
            "top_places": list(self.top_places),
            "top_topics": list(self.top_topics),
            "interdisciplinary_reason": self.interdisciplinary_reason,
            "passages": [p.to_dict() for p in self.passages],
        }


@dataclass(frozen=True)
class ReconstructedDisciplineReport:
    """Mosaico completo di una disciplina ricostruita dal basso attraverso libri non disciplinari."""

    target_discipline: str
    target_label_it: str
    raw_query: str
    total_wrong_books: int
    total_passages: int
    excluded_native_books_count: int
    excluded_noise_books_count: int
    distinct_primary_disciplines: Tuple[str, ...]
    top_places: Tuple[str, ...]
    top_topics: Tuple[str, ...]
    books: Tuple[ReconstructedBookContribution, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_discipline": self.target_discipline,
            "target_label_it": self.target_label_it,
            "raw_query": self.raw_query,
            "total_wrong_books": self.total_wrong_books,
            "total_passages": self.total_passages,
            "excluded_native_books_count": self.excluded_native_books_count,
            "excluded_noise_books_count": self.excluded_noise_books_count,
            "distinct_primary_disciplines": list(self.distinct_primary_disciplines),
            "top_places": list(self.top_places),
            "top_topics": list(self.top_topics),
            "books": [b.to_dict() for b in self.books],
        }


def _assert_spectrum_populated(conn: sqlite3.Connection) -> None:
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('book_discipline_spectrum', 'book_spectrum_meta')"
        ).fetchall()
    }
    if len(tables) < 2:
        raise RuntimeError(
            "Le tabelle dello spettro (`book_discipline_spectrum`, `book_spectrum_meta`) non sono "
            "ancora state inizializzate: esegui prima `compute_all_book_spectra()`."
        )
    row_count = int(conn.execute("SELECT COUNT(*) FROM book_discipline_spectrum").fetchone()[0])
    if row_count == 0:
        raise RuntimeError(
            "La tabella `book_discipline_spectrum` è vuota: esegui prima `compute_all_book_spectra()`."
        )


def _chunked(seq: Sequence[int], size: int = 500) -> Iterable[Sequence[int]]:
    for idx in range(0, len(seq), size):
        yield seq[idx : idx + size]


def _parse_str_tuple(raw: Optional[str]) -> Tuple[str, ...]:
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(data, list):
        return ()
    out: List[str] = []
    seen: set[str] = set()
    for item in data:
        cleaned = " ".join(str(item or "").split()).strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            out.append(cleaned)
    return tuple(out)


def _format_ital_pct(val: float) -> str:
    return f"{val:.1f}%".replace(".", ",")


def _build_interdisciplinary_reason(
    *,
    target_label: str,
    primary_label: Optional[str],
    primary_share_pct: float,
    places: Sequence[str],
    topics: Sequence[str],
) -> str:
    host_desc = (
        f"un'opera di {primary_label} ({_format_ital_pct(primary_share_pct)})"
        if primary_label
        else "un'opera di ambito differente"
    )
    if places:
        detail = f" — luoghi citati: {', '.join(places[:4])}"
    elif topics:
        detail = f" — temi: {', '.join(topics[:3])}"
    else:
        detail = ""
    return f"Passaggio di {target_label} dentro {host_desc}{detail}."


def _compute_passage_density(
    *,
    target_discipline: str,
    macro_disciplines: Sequence[str],
    units_count: int,
    places: Sequence[str],
    topics: Sequence[str],
    historical_years: Sequence[str],
    char_count: int,
) -> float:
    purity = 1.0 / max(1, len(macro_disciplines))
    unit_richness = min(1.0, units_count / 3.0)
    if target_discipline in _SPATIAL_DISCIPLINES:
        concrete_raw = 1.5 * len(places) + len(topics) + 0.5 * len(historical_years)
        concrete_anchor = min(1.0, concrete_raw / 6.0)
    else:
        concrete_raw = len(places) + len(topics) + len(historical_years)
        concrete_anchor = min(1.0, concrete_raw / 5.0)
    text_substance = min(1.0, char_count / 2500.0)
    return round(
        0.35 * purity + 0.25 * unit_richness + 0.25 * concrete_anchor + 0.15 * text_substance,
        4,
    )


def _select_representative_unit(units: Sequence[sqlite3.Row]) -> Tuple[str, str]:
    best_stmt = ""
    best_quote = ""
    best_key: Tuple[int, int, int] = (-1, -1, -1)
    for u in units:
        stmt = " ".join(str(u["stmt"] or "").split()).strip()
        quote = " ".join(str(u["verbatim_quote"] or "").split()).strip()
        kind = str(u["kind"] or "").strip().lower()
        key = (
            1 if (quote and stmt) else 0,
            _UNIT_KIND_PRIORITY.get(kind, 1),
            len(quote) + len(stmt),
        )
        if key > best_key:
            best_key = key
            best_stmt = stmt
            best_quote = quote
    return best_stmt, best_quote


def reconstruct_discipline(
    conn: sqlite3.Connection,
    target_discipline: str | MacroDiscipline,
    *,
    exclude_non_book_noise: bool = True,
    min_book_blocks: int = 2,
    min_coverage_pct: float = 0.5,
    max_target_share_pct: float = 30.0,
    max_target_coverage_pct: float = 45.0,
    min_block_chars: int = 250,
    require_epistemic_unit: bool = True,
    limit_books: Optional[int] = None,
    limit_passages_per_book: Optional[int] = None,
) -> ReconstructedDisciplineReport:
    """Ricostruisce la disciplina `target_discipline` dai 'Libri Sbagliati' del corpus."""
    conn.row_factory = sqlite3.Row
    _assert_spectrum_populated(conn)

    raw_query = target_discipline.value if isinstance(target_discipline, MacroDiscipline) else str(target_discipline)
    target_enum = resolve_macro_discipline(target_discipline)
    target_key = target_enum.value
    target_label = label_for_discipline(target_key)
    native_domains = DISCIPLINE_NATIVE_SURFACE_DOMAINS.get(target_key, frozenset())

    candidate_book_rows = conn.execute(
        """
        SELECT
            bk.book_pk,
            bk.book_uid,
            bk.title,
            bk.author,
            bk.year,
            bk.surface_domain,
            COALESCE(m.quality_tier, 'canonical_book') AS quality_tier,
            m.primary_discipline,
            COALESCE(m.primary_share_pct, 0.0) AS primary_share_pct,
            s.block_count,
            s.coverage_pct,
            s.share_pct,
            s.block_pks_json,
            s.top_topics_json,
            s.top_places_json
        FROM book_discipline_spectrum s
        JOIN books bk ON bk.book_pk = s.book_pk
        LEFT JOIN book_spectrum_meta m ON m.book_pk = s.book_pk
        WHERE bk.is_active = 1
          AND s.macro_discipline = ?
        ORDER BY s.block_count DESC, s.coverage_pct DESC, bk.book_pk ASC
        """,
        (target_key,),
    ).fetchall()

    excluded_native = 0
    excluded_noise = 0
    qualified_book_specs: List[Dict[str, Any]] = []
    all_target_block_pks: List[int] = []

    for row in candidate_book_rows:
        quality_tier = str(row["quality_tier"] or "canonical_book")
        if exclude_non_book_noise and quality_tier in {"non_book_noise", "reference_manual"}:
            excluded_noise += 1
            continue

        surface_low = str(row["surface_domain"] or "").strip().lower()
        primary_disc = row["primary_discipline"]
        cov_pct = float(row["coverage_pct"])
        share_pct = float(row["share_pct"])
        blk_cnt = int(row["block_count"])

        is_native = (
            surface_low in native_domains
            or primary_disc == target_key
            or share_pct > float(max_target_share_pct)
            or cov_pct > float(max_target_coverage_pct)
        )
        if is_native:
            excluded_native += 1
            continue

        if blk_cnt < int(min_book_blocks) or cov_pct < float(min_coverage_pct):
            continue

        pks = [int(pk) for pk in json.loads(row["block_pks_json"] or "[]")]
        if not pks:
            continue

        qualified_book_specs.append(
            {
                "row": row,
                "block_pks": pks,
                "top_topics": _parse_str_tuple(row["top_topics_json"]),
                "top_places": _parse_str_tuple(row["top_places_json"]),
            }
        )
        all_target_block_pks.extend(pks)

    # Caricamento in batch (chunk da 500) di blocks, block_metadata_v22 ed epistemic_units
    blocks_by_pk: Dict[int, sqlite3.Row] = {}
    units_by_pk: Dict[int, List[sqlite3.Row]] = {}
    unique_pks = sorted(set(all_target_block_pks))

    for chunk in _chunked(unique_pks, size=500):
        placeholders = ",".join("?" for _ in chunk)
        blk_rows = conn.execute(
            f"""
            SELECT
                b.block_pk,
                b.block_uid,
                b.book_pk,
                b.block_role,
                b.page_start,
                b.page_end,
                b.printed_page,
                b.section_title,
                b.content,
                b.char_count,
                m.macro_disciplines_json,
                m.emergent_topics_json,
                m.places_json,
                m.historical_years_json
            FROM blocks b
            JOIN block_metadata_v22 m ON m.block_pk = b.block_pk
            WHERE b.block_pk IN ({placeholders})
              AND b.is_active = 1
            """,
            tuple(chunk),
        ).fetchall()
        for br in blk_rows:
            blocks_by_pk[int(br["block_pk"])] = br

        unit_rows = conn.execute(
            f"""
            SELECT block_pk, kind, stmt, verbatim_quote
            FROM epistemic_units
            WHERE block_pk IN ({placeholders})
            ORDER BY block_pk ASC, unit_pk ASC
            """,
            tuple(chunk),
        ).fetchall()
        for ur in unit_rows:
            units_by_pk.setdefault(int(ur["block_pk"]), []).append(ur)

    book_contributions: List[ReconstructedBookContribution] = []
    global_places: Counter[str] = Counter()
    global_topics: Counter[str] = Counter()
    primary_disciplines_seen: set[str] = set()
    total_passages_full = 0

    for item in qualified_book_specs:
        brow = item["row"]
        book_pk = int(brow["book_pk"])
        primary_disc = brow["primary_discipline"]
        primary_label = label_for_discipline(primary_disc) if primary_disc else None
        primary_share = float(brow["primary_share_pct"] or 0.0)
        target_share = float(brow["share_pct"])
        target_cov = float(brow["coverage_pct"])
        quality_tier = str(brow["quality_tier"] or "canonical_book")

        book_passages: List[ReconstructedPassage] = []
        book_place_counts: Counter[str] = Counter()
        book_topic_counts: Counter[str] = Counter()

        for bpk in item["block_pks"]:
            blk = blocks_by_pk.get(bpk)
            if blk is None:
                continue
            if str(blk["block_role"] or "") == "paratext":
                continue
            sec_title = str(blk["section_title"] or "")
            content = str(blk["content"] or "")
            if is_residual_paratext_block(sec_title, content):
                continue
            char_cnt = int(blk["char_count"] or 0)
            if char_cnt < int(min_block_chars):
                continue

            blk_units = units_by_pk.get(bpk, [])
            best_stmt, best_quote = _select_representative_unit(blk_units)
            if require_epistemic_unit and (not blk_units or not best_stmt or not best_quote):
                continue

            macro_discs = _parse_str_tuple(blk["macro_disciplines_json"])
            if target_key not in macro_discs:
                continue
            topics = _parse_str_tuple(blk["emergent_topics_json"])
            places = _parse_str_tuple(blk["places_json"])
            years = _parse_str_tuple(blk["historical_years_json"])

            density = _compute_passage_density(
                target_discipline=target_key,
                macro_disciplines=macro_discs,
                units_count=len(blk_units),
                places=places,
                topics=topics,
                historical_years=years,
                char_count=char_cnt,
            )
            reason = _build_interdisciplinary_reason(
                target_label=target_label,
                primary_label=primary_label,
                primary_share_pct=primary_share,
                places=places,
                topics=topics,
            )

            book_place_counts.update(places)
            book_topic_counts.update(topics)
            global_places.update(places)
            global_topics.update(topics)

            book_passages.append(
                ReconstructedPassage(
                    block_pk=bpk,
                    block_uid=str(blk["block_uid"]),
                    book_pk=book_pk,
                    book_title=str(brow["title"]),
                    author=brow["author"],
                    year=brow["year"],
                    surface_domain=str(brow["surface_domain"]),
                    primary_discipline=primary_disc,
                    primary_discipline_label=primary_label,
                    page_start=blk["page_start"],
                    page_end=blk["page_end"],
                    printed_page=blk["printed_page"],
                    section_title=sec_title,
                    char_count=char_cnt,
                    macro_disciplines=macro_discs,
                    topics=topics,
                    places=places,
                    historical_years=years,
                    best_stmt=best_stmt,
                    verbatim_quote=best_quote,
                    units_count=len(blk_units),
                    density_score=density,
                    interdisciplinary_reason=reason,
                )
            )

        if not book_passages:
            continue

        book_passages.sort(key=lambda p: (-p.density_score, p.page_start or 0, p.block_pk))
        total_passages_full += len(book_passages)
        if primary_disc:
            primary_disciplines_seen.add(primary_disc)

        top_places = tuple(pl for pl, _ in book_place_counts.most_common(12)) or item["top_places"]
        top_topics = tuple(tp for tp, _ in book_topic_counts.most_common(12)) or item["top_topics"]

        top_sample = book_passages[:5]
        avg_top_density = sum(p.density_score for p in top_sample) / len(top_sample)
        volume_log = min(1.0, math.log1p(len(book_passages)) / math.log1p(25))
        contrast = max(0.0, 1.0 - target_share / 100.0)
        anchor_bonus = min(1.0, len(book_place_counts) / 8.0)
        tier_bonus = 0.05 if quality_tier == "canonical_book" else 0.0
        surprise_score = round(
            0.38 * avg_top_density
            + 0.30 * volume_log
            + 0.17 * contrast
            + 0.10 * anchor_bonus
            + tier_bonus,
            4,
        )

        book_reason = _build_interdisciplinary_reason(
            target_label=target_label,
            primary_label=primary_label,
            primary_share_pct=primary_share,
            places=top_places,
            topics=top_topics,
        )

        limited_passages = (
            tuple(book_passages[:limit_passages_per_book])
            if limit_passages_per_book is not None and limit_passages_per_book >= 0
            else tuple(book_passages)
        )

        book_contributions.append(
            ReconstructedBookContribution(
                book_pk=book_pk,
                book_uid=str(brow["book_uid"]),
                book_title=str(brow["title"]),
                author=brow["author"],
                year=brow["year"],
                surface_domain=str(brow["surface_domain"]),
                quality_tier=quality_tier,
                primary_discipline=primary_disc,
                primary_discipline_label=primary_label,
                primary_share_pct=primary_share,
                target_block_count=int(brow["block_count"]),
                target_coverage_pct=target_cov,
                target_share_pct=target_share,
                book_surprise_score=surprise_score,
                top_places=top_places,
                top_topics=top_topics,
                interdisciplinary_reason=book_reason,
                passages=limited_passages,
            )
        )

    book_contributions.sort(
        key=lambda b: (-b.book_surprise_score, -b.target_block_count, b.book_pk)
    )
    total_wrong_books_full = len(book_contributions)
    limited_books = (
        tuple(book_contributions[:limit_books])
        if limit_books is not None and limit_books >= 0
        else tuple(book_contributions)
    )

    return ReconstructedDisciplineReport(
        target_discipline=target_key,
        target_label_it=target_label,
        raw_query=raw_query,
        total_wrong_books=total_wrong_books_full,
        total_passages=total_passages_full,
        excluded_native_books_count=excluded_native,
        excluded_noise_books_count=excluded_noise,
        distinct_primary_disciplines=tuple(sorted(primary_disciplines_seen)),
        top_places=tuple(pl for pl, _ in global_places.most_common(15)),
        top_topics=tuple(tp for tp, _ in global_topics.most_common(15)),
        books=limited_books,
    )


def _format_report_text(report: ReconstructedDisciplineReport) -> str:
    lines: List[str] = [
        f"\n=== {report.target_label_it} ricostruita dal basso ({report.target_discipline}) ===",
        f"Libri 'sbagliati' qualificati: {report.total_wrong_books} (mostrati: {len(report.books)}) | "
        f"Passaggi verificati: {report.total_passages} | "
        f"Esclusi nativi/primari: {report.excluded_native_books_count} | "
        f"Esclusi non-libro: {report.excluded_noise_books_count}",
        f"Discipline ospitanti distinte ({len(report.distinct_primary_disciplines)}): "
        f"{', '.join(label_for_discipline(d) for d in report.distinct_primary_disciplines)}",
    ]
    if report.top_places:
        lines.append(f"Luoghi ricorrenti nel mosaico: {', '.join(report.top_places[:10])}")
    if report.top_topics:
        lines.append(f"Temi trasversali: {', '.join(report.top_topics[:8])}")

    for idx, b in enumerate(report.books, start=1):
        prim = b.primary_discipline_label or b.surface_domain
        lines.append(
            f"\n{idx:2d}. [{b.book_pk}] {b.book_title} "
            f"(Ospite: {prim} {b.primary_share_pct:.1f}% | "
            f"{report.target_label_it}: {b.target_coverage_pct:.1f}% Cov / {b.target_share_pct:.1f}% Share | "
            f"blks={b.target_block_count} | surprise={b.book_surprise_score:.3f})"
        )
        lines.append(f"    {b.interdisciplinary_reason}")
        for p in b.passages:
            loc = f"pag. {p.printed_page}" if p.printed_page else f"pag. {p.page_start}"
            lines.append(f"    • [{loc} | densità={p.density_score:.3f}] {p.best_stmt}")
            lines.append(f"      «{p.verbatim_quote}»")
    return "\n".join(lines)


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ricostruisce una disciplina dal basso attraverso i 'Libri Sbagliati' (TASK-SPEC-02)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso a pack_corpus.db")
    parser.add_argument(
        "--discipline",
        type=str,
        default="geografia_territorio",
        help="Disciplina target o alias (es. geografia_territorio, musica_acustica, logica)",
    )
    parser.add_argument("--limit-books", type=int, default=12, help="Numero libri mostrati (ignorato con --all)")
    parser.add_argument("--passages-per-book", type=int, default=2, help="Passaggi per libro (ignorato con --all)")
    parser.add_argument("--min-book-blocks", type=int, default=2)
    parser.add_argument("--min-coverage-pct", type=float, default=0.5)
    parser.add_argument("--all", action="store_true", help="Restituisce tutti i libri e tutti i passaggi")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    conn = connect_corpus_db(args.db, read_only=True)
    try:
        report = reconstruct_discipline(
            conn,
            args.discipline,
            min_book_blocks=args.min_book_blocks,
            min_coverage_pct=args.min_coverage_pct,
            limit_books=None if args.all else args.limit_books,
            limit_passages_per_book=None if args.all else args.passages_per_book,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(_format_report_text(report))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
