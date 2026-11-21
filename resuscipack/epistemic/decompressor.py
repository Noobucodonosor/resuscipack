"""Decompressore Sinottico Cronologico e Modale (ADR-0004, TASK-SPEC-03).

Interroga l'intera memoria estratta di `pack_corpus.db` intorno a un concetto o domanda
restituendo una mappa sinottica multi-autore e cronologica (`Chi / Come / Dove / Quando /
Con chi in disaccordo`), sempre ancorata a `block_pk`, `block_uid` e `verbatim_quote` verificate.

Costi API esterni: 0 EUR (query deterministiche su `passages_fts`, `epistemic_units`,
`block_metadata_v22` e `book_spectrum_meta`).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..corpus.schema import DEFAULT_DB_PATH, connect_corpus_db
from .schema_v21 import normalizza_testo
from .spectrum import is_residual_paratext_block, label_for_discipline

MODE_LABELS_IT: Dict[str, str] = {
    "defines": "Definisce",
    "proves": "Dimostra",
    "applies": "Applica",
    "critiques": "Critica / Contesta",
    "extends": "Estende",
    "presupposes": "Presuppone",
    "narrates": "Narra",
}

CANONICAL_AUTHOR_EPOCH: Dict[str, Tuple[int, str]] = {
    "talete": (-585, "~585 a.C."),
    "pitagora": (-530, "~530 a.C."),
    "platone": (-380, "~380 a.C."),
    "aristotele": (-340, "~340 a.C."),
    "euclide": (-300, "~300 a.C."),
    "archimede": (-250, "~250 a.C."),
    "copernico": (1543, "1543"),
    "galileo": (1632, "1632"),
    "galilei": (1632, "1632"),
    "cavalieri": (1635, "1635"),
    "descartes": (1637, "1637"),
    "cartesio": (1637, "1637"),
    "torricelli": (1644, "1644"),
    "boyle": (1661, "1661"),
    "leibniz": (1684, "1684"),
    "newton": (1687, "1687"),
    "eulero": (1748, "1748"),
    "euler": (1748, "1748"),
    "winckelmann": (1764, "1764"),
    "galvani": (1791, "1791"),
    "laplace": (1796, "1796"),
    "alessandro volta": (1799, "1799"),
    "gauss": (1801, "1801"),
    "ampere": (1820, "1820"),
    "ampère": (1820, "1820"),
    "cauchy": (1821, "1821"),
    "boole": (1854, "1854"),
    "maxwell": (1865, "1865"),
    "kelvin": (1867, "1867"),
    "thomson": (1867, "1867"),
    "cantor": (1874, "1874"),
    "boltzmann": (1877, "1877"),
    "peano": (1889, "1889"),
    "hilbert": (1899, "1899"),
    "marconi": (1901, "1901"),
    "einstein": (1905, "1905"),
    "wittgenstein": (1921, "1921"),
    "godel": (1931, "1931"),
    "gödel": (1931, "1931"),
    "turing": (1936, "1936"),
    "shannon": (1948, "1948"),
}

_AUTHOR_PATTERNS: Tuple[Tuple[re.Pattern[str], int, str], ...] = tuple(
    (
        re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE),
        yr,
        lbl,
    )
    for name, (yr, lbl) in sorted(CANONICAL_AUTHOR_EPOCH.items(), key=lambda kv: -len(kv[0]))
)

_ROMAN_MAP: Dict[str, int] = {"I": 1, "V": 5, "X": 10}
_ITALIAN_CENTURIES: Dict[str, Tuple[int, str]] = {
    "duecento": (1250, "Duecento"),
    "trecento": (1350, "Trecento"),
    "quattrocento": (1450, "Quattrocento"),
    "cinquecento": (1550, "Cinquecento"),
    "seicento": (1650, "Seicento"),
    "settecento": (1750, "Settecento"),
    "ottocento": (1850, "Ottocento"),
    "novecento": (1950, "Novecento"),
}
_DECADE_WORDS: Dict[str, int] = {
    "venti": 1920,
    "trenta": 1930,
    "quaranta": 1940,
    "cinquanta": 1950,
    "sessanta": 1960,
    "settanta": 1970,
    "ottanta": 1980,
    "novanta": 1990,
}

_SLASH_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_CPP_NOISE_RE = re.compile(r"c\+\+", re.IGNORECASE)
_BC_CENTURY_ROMAN_RE = re.compile(
    r"^(?:~|circa\s+)?(?:sec(?:olo)?\.?\s*)?([ivx]+)\s*(?:sec(?:olo)?\.?)?\s*(?:a\.?\s*c\.?|b\.?\s*c\.?)$",
    re.IGNORECASE,
)
_DC_CENTURY_ROMAN_RE = re.compile(
    r"^(?:~|circa\s+)?(?:sec(?:olo)?\.?\s*)?([ivx]+)\s*(?:sec(?:olo)?\.?)?\s*(?:d\.?\s*c\.?|a\.?\s*d\.?)$",
    re.IGNORECASE,
)
_BC_YEAR_RE = re.compile(
    r"^(?:~|circa\s+)?(\d{1,4})\s*(?:a\.?\s*c\.?|b\.?\s*c\.?)$",
    re.IGNORECASE,
)
_DC_YEAR_RE = re.compile(
    r"^(?:~|circa\s+)?(\d{1,4})\s*(?:d\.?\s*c\.?|a\.?\s*d\.?)$",
    re.IGNORECASE,
)
_ROMAN_CENTURY_RE = re.compile(
    r"^(?:sec(?:olo)?\.?\s*)?([ivx]+)(?:\s*(?:sec(?:olo)?\.?))?$",
    re.IGNORECASE,
)
_DECADE_NUM_RE = re.compile(r"^(\d{4})s$", re.IGNORECASE)
_ANNI_WORD_RE = re.compile(
    r"^anni\s+(?:'?(\d{2})|(venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|novanta))$",
    re.IGNORECASE,
)
_YEAR_RANGE_RE = re.compile(r"^(?:~|circa\s+)?(\d{4})\s*[-–/]\s*(\d{2,4})$")
_YEAR_4D_RE = re.compile(r"(?:^|[^\d+])(\d{4})(?:[^\d]|$)")


def _roman_to_int(roman: str) -> Optional[int]:
    s = roman.strip().upper()
    if not s or any(ch not in _ROMAN_MAP for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_MAP[ch]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    # Verifica canonicalità tramite roundtrip su 1..21
    if not (1 <= total <= 21):
        return None
    return total


def parse_historical_year(raw: str) -> Optional[Tuple[int, str]]:
    """Converte stringhe cronologiche eterogenee del corpus in `(sort_year, when_label)` affidabili."""
    s = " ".join(str(raw or "").split()).strip()
    if not s:
        return None
    if _CPP_NOISE_RE.search(s) or _SLASH_DATE_RE.match(s):
        return None
    if re.fullmatch(r"\d{1,2}", s):
        return None

    m_bc_cent = _BC_CENTURY_ROMAN_RE.match(s)
    if m_bc_cent:
        c = _roman_to_int(m_bc_cent.group(1))
        if c is not None:
            mid = -((c - 1) * 100 + 50)
            return mid, f"{m_bc_cent.group(1).upper()} sec. a.C."

    m_dc_cent = _DC_CENTURY_ROMAN_RE.match(s)
    if m_dc_cent:
        c = _roman_to_int(m_dc_cent.group(1))
        if c is not None:
            mid = (c - 1) * 100 + 50
            return mid, f"{m_dc_cent.group(1).upper()} sec. d.C."

    m_bc = _BC_YEAR_RE.match(s)
    if m_bc:
        yr = int(m_bc.group(1))
        if 1 <= yr <= 3000:
            return -yr, f"{yr} a.C."
        return None

    m_dc = _DC_YEAR_RE.match(s)
    if m_dc:
        yr = int(m_dc.group(1))
        if 1 <= yr <= 2030:
            return yr, f"{yr} d.C."
        return None

    low = s.lower()
    for word, (mid, lbl) in _ITALIAN_CENTURIES.items():
        if word in low:
            return mid, lbl

    m_dec = _DECADE_NUM_RE.match(s)
    if m_dec:
        yr = int(m_dec.group(1))
        if 1000 <= yr <= 2020:
            return yr, f"{yr}s"

    m_anni = _ANNI_WORD_RE.match(low)
    if m_anni:
        if m_anni.group(1):
            d2 = int(m_anni.group(1))
            yr = 1900 + d2 if d2 >= 20 else 2000 + d2
            return yr, s
        word_dec = m_anni.group(2)
        if word_dec in _DECADE_WORDS:
            return _DECADE_WORDS[word_dec], s

    m_rom = _ROMAN_CENTURY_RE.match(s)
    if m_rom:
        token = m_rom.group(1).upper()
        c = _roman_to_int(token)
        has_sec_marker = "sec" in low
        # Evita falsi positivi su numeri di tomo/volume ('I'..'X') se manca la parola 'sec.'/'secolo'
        if c is not None and (has_sec_marker or 11 <= c <= 21):
            mid = (c - 1) * 100 + 50
            return mid, f"{token} sec."

    m_rng = _YEAR_RANGE_RE.match(s)
    if m_rng:
        yr = int(m_rng.group(1))
        if 1000 <= yr <= 2030:
            return yr, s

    m_4d = _YEAR_4D_RE.search(s)
    if m_4d:
        yr = int(m_4d.group(1))
        if 1000 <= yr <= 2030:
            return yr, str(yr)

    return None


def resolve_entry_chronology(
    historical_years: Sequence[str],
    actors: Sequence[str],
    book_title: str,
    book_author: Optional[str],
    book_year: Optional[int],
) -> Tuple[Optional[int], str, str]:
    """Determina `(sort_year, when_label, year_source)` ordinando per fonte più specifica."""
    parsed_years: List[Tuple[int, str]] = []
    for raw_y in historical_years:
        parsed = parse_historical_year(raw_y)
        if parsed is not None:
            parsed_years.append(parsed)
    if parsed_years:
        earliest = min(parsed_years, key=lambda pair: pair[0])
        return earliest[0], earliest[1], "block_metadata_year"

    # Match su autori/attori storici canonici (prima actors estratti, poi autore e titolo del libro)
    for source_text in (" ".join(actors), str(book_author or ""), str(book_title or "")):
        if not source_text:
            continue
        for pat, yr, lbl in _AUTHOR_PATTERNS:
            if pat.search(source_text):
                return yr, lbl, "author_epoch"
        # Caso speciale "Volta" solo se maiuscolo (evita "una volta")
        if re.search(r"\bVolta\b", source_text):
            return 1799, "1799", "author_epoch"

    if book_year is not None and 1400 <= int(book_year) <= 2030:
        return int(book_year), str(book_year), "book_publication_year"

    return None, "Data non indicata", "undated"


@dataclass(frozen=True)
class SynopticEntry:
    """Singola voce storica e modale ancorata a un blocco e a una citazione verbatim."""

    unit_pk: int
    unit_uid: str
    block_pk: int
    block_uid: str
    book_pk: int
    book_title: str
    author: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    printed_page: Optional[str]
    section_title: str
    surface_domain: str
    primary_discipline: Optional[str]
    primary_discipline_label: Optional[str]
    who: Tuple[str, ...]
    mode: str
    mode_label_it: str
    kind: str
    sort_year: Optional[int]
    when_label: str
    year_source: str
    places: Tuple[str, ...]
    source_locator: str
    vs_dispute: Optional[str]
    stmt: str
    verbatim_quote: str
    concepts: Tuple[str, ...]
    macro_disciplines: Tuple[str, ...]
    relevance_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_pk": self.unit_pk,
            "unit_uid": self.unit_uid,
            "block_pk": self.block_pk,
            "block_uid": self.block_uid,
            "book_pk": self.book_pk,
            "book_title": self.book_title,
            "author": self.author,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "printed_page": self.printed_page,
            "section_title": self.section_title,
            "surface_domain": self.surface_domain,
            "primary_discipline": self.primary_discipline,
            "primary_discipline_label": self.primary_discipline_label,
            "who": list(self.who),
            "mode": self.mode,
            "mode_label_it": self.mode_label_it,
            "kind": self.kind,
            "sort_year": self.sort_year,
            "when_label": self.when_label,
            "year_source": self.year_source,
            "places": list(self.places),
            "source_locator": self.source_locator,
            "vs_dispute": self.vs_dispute,
            "stmt": self.stmt,
            "verbatim_quote": self.verbatim_quote,
            "concepts": list(self.concepts),
            "macro_disciplines": list(self.macro_disciplines),
            "relevance_score": self.relevance_score,
        }


@dataclass(frozen=True)
class SynopticDisputeHighlight:
    """Controversia o posizione critica esplicita (`vs_dispute`) individuata nella sinossi."""

    unit_pk: int
    block_pk: int
    block_uid: str
    book_pk: int
    book_title: str
    page_start: Optional[int]
    printed_page: Optional[str]
    who: Tuple[str, ...]
    sort_year: Optional[int]
    when_label: str
    vs_dispute: str
    stmt: str
    verbatim_quote: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_pk": self.unit_pk,
            "block_pk": self.block_pk,
            "block_uid": self.block_uid,
            "book_pk": self.book_pk,
            "book_title": self.book_title,
            "page_start": self.page_start,
            "printed_page": self.printed_page,
            "who": list(self.who),
            "sort_year": self.sort_year,
            "when_label": self.when_label,
            "vs_dispute": self.vs_dispute,
            "stmt": self.stmt,
            "verbatim_quote": self.verbatim_quote,
        }


@dataclass(frozen=True)
class SynopticReport:
    """Risultato completo dell'interrogazione sinottica cronologica e modale."""

    query: str
    normalized_terms: Tuple[str, ...]
    total_entries: int
    distinct_books: int
    distinct_actors: int
    chronological_span: Tuple[Optional[int], Optional[int]]
    mode_counts: Dict[str, int]
    disputes_count: int
    disputes: Tuple[SynopticDisputeHighlight, ...]
    by_mode: Dict[str, Tuple[SynopticEntry, ...]]
    timeline: Tuple[SynopticEntry, ...]
    top_places: Tuple[str, ...]
    top_disciplines: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "normalized_terms": list(self.normalized_terms),
            "total_entries": self.total_entries,
            "distinct_books": self.distinct_books,
            "distinct_actors": self.distinct_actors,
            "chronological_span": list(self.chronological_span),
            "mode_counts": dict(self.mode_counts),
            "disputes_count": self.disputes_count,
            "disputes": [d.to_dict() for d in self.disputes],
            "by_mode": {m: [e.to_dict() for e in entries] for m, entries in self.by_mode.items()},
            "timeline": [e.to_dict() for e in self.timeline],
            "top_places": list(self.top_places),
            "top_disciplines": list(self.top_disciplines),
        }


_QUERY_STOPWORDS = frozenset(
    {
        "il", "lo", "la", "le", "gli", "un", "uno", "una", "del", "dello", "della",
        "dei", "degli", "delle", "sul", "sulla", "nel", "nella", "dall", "dell",
        "nell", "sull", "all", "di", "da", "in", "su", "con", "per", "tra", "fra",
        "che", "chi", "come", "dove", "quando", "the", "and", "of", "in", "a", "e", "o",
        "ed", "ad", "al", "ai", "dal", "dai", "nei", "sui", "perche", "mentre", "quindi",
        # Parole-guscio frequenti nei sintagmi/proposizioni editoriali
        "atto", "passo", "passi", "idea", "modo", "verso", "primo", "prima", "secondo",
        "base", "ruolo", "senso", "forma", "parte", "generale", "generali",
        "fondamentale", "fondamentali", "rappresenta", "costituisce", "significa",
    }
)


_INVARIANT_ABSTRACT_SUFFIXES = ("tà", "ta", "zione", "zioni", "ismo", "ismi", "logia", "logie")


def _safe_morph_variants(term: str) -> Tuple[str, ...]:
    """Genera varianti flessive sicure senza troncamento cieco (`cardinalità` != `cardinal*`)."""
    clean = re.sub(r"[^a-zà-öø-ÿ0-9]+", "", term.lower())
    if not clean:
        return ()
    variants: List[str] = [clean]
    if len(clean) < 6 or clean.endswith(_INVARIANT_ABSTRACT_SUFFIXES):
        return tuple(variants)

    if clean.endswith(("a", "e", "i", "o")) and len(clean) >= 6:
        base = clean[:-1]
        for suf in ("o", "a", "i", "e"):
            cand = f"{base}{suf}"
            if cand not in variants:
                variants.append(cand)
    return tuple(variants)


def _extract_query_terms(concept_query: str) -> Tuple[str, ...]:
    norm = normalizza_testo(concept_query)
    raw_tokens = re.findall(r"[a-zà-öø-ÿ0-9]{2,}", norm)
    filtered = [t for t in raw_tokens if t not in _QUERY_STOPWORDS]
    tokens = filtered if filtered else raw_tokens
    seen: set[str] = set()
    unique: List[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.add(tok)
            unique.append(tok)
    return tuple(unique)


def _build_safe_fts_query(terms: Sequence[str]) -> str:
    if not terms:
        return ""
    safe_clauses: List[str] = []
    for tok in terms[:6]:
        variants = _safe_morph_variants(tok)
        if not variants:
            continue
        if len(variants) == 1:
            safe_clauses.append(f'"{variants[0]}"')
        else:
            joined = " OR ".join(f'"{v}"' for v in variants)
            safe_clauses.append(f"({joined})")
    if not safe_clauses:
        return ""
    if len(safe_clauses) == 1:
        return safe_clauses[0]
    if len(safe_clauses) == 2:
        phrase = " ".join(re.sub(r"[^a-zà-öø-ÿ0-9]+", "", t) for t in terms[:2]).strip()
        return f'"{phrase}" OR ({safe_clauses[0]} AND {safe_clauses[1]})'
    return " OR ".join(safe_clauses)


def _parse_json_tuple(raw: Optional[str]) -> Tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    out: List[str] = []
    seen: set[str] = set()
    for item in parsed:
        val = " ".join(str(item or "").split()).strip()
        if val and val.casefold() not in seen:
            seen.add(val.casefold())
            out.append(val)
    return tuple(out)


def _token_matches_hay(term: str, hay_norm: str, hay_words: set[str]) -> bool:
    for v in _safe_morph_variants(term):
        if v in hay_words or re.search(rf"\b{re.escape(v)}\b", hay_norm):
            return True
    return False


def _unit_relevance_score(
    *,
    terms: Sequence[str],
    phrase_norm: str,
    stmt: str,
    verbatim_quote: str,
    concepts: Sequence[str],
    vs_dispute: Optional[str],
    actors: Sequence[str],
) -> Optional[float]:
    stmt_n = normalizza_testo(stmt)
    quote_n = normalizza_testo(verbatim_quote)
    conc_n = normalizza_testo(" ".join(concepts))
    vs_n = normalizza_testo(vs_dispute or "")
    combined = f"{stmt_n} {quote_n} {conc_n} {vs_n}".strip()
    if not combined:
        return None

    hay_words = set(re.findall(r"[a-zà-öø-ÿ0-9]{2,}", combined))
    phrase_hit = bool(phrase_norm and len(phrase_norm) >= 4 and phrase_norm in combined)

    matched = sum(1 for t in terms if _token_matches_hay(t, combined, hay_words))
    min_needed = 1 if len(terms) <= 1 else (2 if len(terms) == 2 else max(2, math.ceil(0.6 * len(terms))))
    if not phrase_hit and matched < min_needed:
        return None

    conc_words = set(re.findall(r"[a-zà-öø-ÿ0-9]{2,}", conc_n))
    stmt_words = set(re.findall(r"[a-zà-öø-ÿ0-9]{2,}", stmt_n))

    concept_hits = sum(1 for t in terms if _token_matches_hay(t, conc_n, conc_words))
    stmt_hits = sum(1 for t in terms if _token_matches_hay(t, stmt_n, stmt_words))

    term_ratio = matched / max(1, len(terms))
    score = (
        0.35 * term_ratio
        + (0.20 if phrase_hit else 0.0)
        + 0.20 * min(1.0, concept_hits / max(1, len(terms)))
        + 0.15 * min(1.0, stmt_hits / max(1, len(terms)))
        + (0.06 if vs_dispute else 0.0)
        + (0.04 if actors else 0.0)
    )
    return round(min(1.0, score), 4)


def _chunked(seq: Sequence[int], size: int = 500) -> Iterable[Sequence[int]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _make_source_locator(
    book_title: str,
    page_start: Optional[int],
    printed_page: Optional[str],
    block_pk: int,
) -> str:
    page_part = f"p. {printed_page}" if printed_page else (f"p. {page_start}" if page_start else "s.p.")
    return f"{book_title} ({page_part}, blk #{block_pk})"


def decompress_concept(
    conn: sqlite3.Connection,
    concept_query: str,
    *,
    modes: Optional[Sequence[str]] = None,
    only_disputes: bool = False,
    exclude_non_book_noise: bool = True,
    max_fts_blocks: int = 800,
    max_entries: Optional[int] = None,
    max_per_book: Optional[int] = None,
) -> SynopticReport:
    """Interroga sinotticamente `pack_corpus.db` ordinando gli interventi per epoca e ruolo modale."""
    conn.row_factory = sqlite3.Row
    raw_query = " ".join(str(concept_query or "").split()).strip()
    terms = _extract_query_terms(raw_query)
    if not terms:
        raise ValueError(f"Query concettuale non valida o priva di termini utili: {concept_query!r}")

    phrase_norm = " ".join(terms)
    allowed_modes: Optional[set[str]] = None
    if modes:
        allowed_modes = {str(m).strip().lower() for m in modes if str(m).strip()}
        invalid = allowed_modes - set(MODE_LABELS_IT.keys())
        if invalid:
            raise ValueError(f"Modi non validi: {sorted(invalid)}. Valori ammessi: {sorted(MODE_LABELS_IT.keys())}")

    # Verifica opzionale presenza tabella `book_spectrum_meta` (compatibilità con DB sintetici)
    has_spectrum_meta = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'book_spectrum_meta'"
        ).fetchone()
        is not None
    )

    candidate_pks: List[int] = []
    seen_pks: set[int] = set()
    fts_expr = _build_safe_fts_query(terms)
    if fts_expr:
        try:
            fts_rows = conn.execute(
                """
                SELECT rowid
                FROM passages_fts
                WHERE passages_fts MATCH ?
                ORDER BY bm25(passages_fts)
                LIMIT ?
                """,
                (fts_expr, int(max_fts_blocks)),
            ).fetchall()
            for r in fts_rows:
                pk = int(r[0])
                if pk not in seen_pks:
                    seen_pks.add(pk)
                    candidate_pks.append(pk)
        except sqlite3.OperationalError:
            pass

    # Integrazione mirata su `epistemic_units` quando i candidati FTS5 sono pochi
    if len(candidate_pks) < 25:
        anchor_tok = max(terms, key=len)
        like_pat = f"%{anchor_tok}%"
        eu_pks = conn.execute(
            """
            SELECT DISTINCT eu.block_pk
            FROM epistemic_units eu
            JOIN blocks b ON b.block_pk = eu.block_pk
            WHERE b.is_active = 1
              AND (lower(eu.stmt) LIKE ? OR lower(eu.concepts_json) LIKE ? OR lower(eu.verbatim_quote) LIKE ?)
            LIMIT 300
            """,
            (like_pat, like_pat, like_pat),
        ).fetchall()
        for r in eu_pks:
            pk = int(r[0])
            if pk not in seen_pks:
                seen_pks.add(pk)
                candidate_pks.append(pk)

    if not candidate_pks:
        return SynopticReport(
            query=raw_query,
            normalized_terms=terms,
            total_entries=0,
            distinct_books=0,
            distinct_actors=0,
            chronological_span=(None, None),
            mode_counts={},
            disputes_count=0,
            disputes=(),
            by_mode={},
            timeline=(),
            top_places=(),
            top_disciplines=(),
        )

    blocks_by_pk: Dict[int, sqlite3.Row] = {}
    units_by_pk: Dict[int, List[sqlite3.Row]] = defaultdict(list)

    meta_select = (
        "COALESCE(bsm.quality_tier, 'canonical_book') AS quality_tier, bsm.primary_discipline"
        if has_spectrum_meta
        else "'canonical_book' AS quality_tier, NULL AS primary_discipline"
    )
    meta_join = "LEFT JOIN book_spectrum_meta bsm ON bsm.book_pk = bk.book_pk" if has_spectrum_meta else ""

    for chunk in _chunked(candidate_pks, size=500):
        ph = ",".join("?" for _ in chunk)
        b_rows = conn.execute(
            f"""
            SELECT
                b.block_pk,
                b.block_uid,
                b.book_pk,
                bk.title AS book_title,
                bk.author,
                bk.year AS book_year,
                bk.surface_domain,
                b.block_role,
                b.page_start,
                b.page_end,
                b.printed_page,
                b.section_title,
                b.content,
                m.macro_disciplines_json,
                m.places_json,
                m.historical_years_json,
                {meta_select}
            FROM blocks b
            JOIN books bk ON bk.book_pk = b.book_pk
            LEFT JOIN block_metadata_v22 m ON m.block_pk = b.block_pk
            {meta_join}
            WHERE b.block_pk IN ({ph})
              AND b.is_active = 1
              AND bk.is_active = 1
              AND b.block_role != 'paratext'
            """,
            tuple(chunk),
        ).fetchall()
        for br in b_rows:
            if exclude_non_book_noise and str(br["quality_tier"]) in {"non_book_noise", "reference_manual"}:
                continue
            if is_residual_paratext_block(str(br["section_title"] or ""), str(br["content"] or "")):
                continue
            blocks_by_pk[int(br["block_pk"])] = br

        if blocks_by_pk:
            chunk_active_pks = [pk for pk in chunk if pk in blocks_by_pk]
            if chunk_active_pks:
                ph_u = ",".join("?" for _ in chunk_active_pks)
                u_rows = conn.execute(
                    f"""
                    SELECT
                        unit_pk, unit_uid, block_pk, kind, mode, stmt,
                        verbatim_quote, actors_json, vs_dispute, concepts_json
                    FROM epistemic_units
                    WHERE block_pk IN ({ph_u})
                    ORDER BY unit_pk ASC
                    """,
                    tuple(chunk_active_pks),
                ).fetchall()
                for ur in u_rows:
                    units_by_pk[int(ur["block_pk"])].append(ur)

    matched_entries: List[SynopticEntry] = []
    for bpk, brow in blocks_by_pk.items():
        units = units_by_pk.get(bpk, [])
        if not units:
            continue

        places = _parse_json_tuple(brow["places_json"])
        hist_years = _parse_json_tuple(brow["historical_years_json"])
        macro_discs = _parse_json_tuple(brow["macro_disciplines_json"])
        prim_disc = brow["primary_discipline"]
        prim_label = label_for_discipline(prim_disc) if prim_disc else None

        for ur in units:
            mode = str(ur["mode"] or "").strip().lower()
            if allowed_modes is not None and mode not in allowed_modes:
                continue
            stmt = " ".join(str(ur["stmt"] or "").split()).strip()
            quote = " ".join(str(ur["verbatim_quote"] or "").split()).strip()
            if not stmt or not quote:
                continue

            vs_raw = " ".join(str(ur["vs_dispute"] or "").split()).strip()
            vs_val: Optional[str] = vs_raw if vs_raw else None
            if only_disputes and not vs_val:
                continue

            actors = _parse_json_tuple(ur["actors_json"])
            concepts = _parse_json_tuple(ur["concepts_json"])
            rel_score = _unit_relevance_score(
                terms=terms,
                phrase_norm=phrase_norm,
                stmt=stmt,
                verbatim_quote=quote,
                concepts=concepts,
                vs_dispute=vs_val,
                actors=actors,
            )
            if rel_score is None:
                continue

            sort_year, when_label, year_source = resolve_entry_chronology(
                hist_years,
                actors,
                str(brow["book_title"] or ""),
                brow["author"],
                brow["book_year"],
            )
            who = actors if actors else ((str(brow["author"]).strip(),) if brow["author"] else ())
            locator = _make_source_locator(
                str(brow["book_title"]),
                brow["page_start"],
                brow["printed_page"],
                bpk,
            )

            matched_entries.append(
                SynopticEntry(
                    unit_pk=int(ur["unit_pk"]),
                    unit_uid=str(ur["unit_uid"]),
                    block_pk=bpk,
                    block_uid=str(brow["block_uid"]),
                    book_pk=int(brow["book_pk"]),
                    book_title=str(brow["book_title"]),
                    author=brow["author"],
                    page_start=brow["page_start"],
                    page_end=brow["page_end"],
                    printed_page=brow["printed_page"],
                    section_title=str(brow["section_title"] or ""),
                    surface_domain=str(brow["surface_domain"] or ""),
                    primary_discipline=prim_disc,
                    primary_discipline_label=prim_label,
                    who=who,
                    mode=mode,
                    mode_label_it=MODE_LABELS_IT.get(mode, mode.title()),
                    kind=str(ur["kind"] or ""),
                    sort_year=sort_year,
                    when_label=when_label,
                    year_source=year_source,
                    places=places,
                    source_locator=locator,
                    vs_dispute=vs_val,
                    stmt=stmt,
                    verbatim_quote=quote,
                    concepts=concepts,
                    macro_disciplines=macro_discs,
                    relevance_score=rel_score,
                )
            )

    # Opzionale tetto per libro privilegiando controversie esplicite, pertinenza e varietà modale
    if max_per_book is not None and max_per_book >= 1:
        by_book: Dict[int, List[SynopticEntry]] = defaultdict(list)
        for e in matched_entries:
            by_book[e.book_pk].append(e)
        capped: List[SynopticEntry] = []
        for entries in by_book.values():
            entries.sort(
                key=lambda x: (
                    -(1 if x.vs_dispute else 0),
                    -x.relevance_score,
                    x.page_start or 0,
                    x.unit_pk,
                )
            )
            seen_modes: set[str] = set()
            selected: List[SynopticEntry] = []
            leftovers: List[SynopticEntry] = []
            for item in entries:
                if len(selected) >= max_per_book:
                    break
                if item.mode not in seen_modes:
                    selected.append(item)
                    seen_modes.add(item.mode)
                else:
                    leftovers.append(item)
            for item in leftovers:
                if len(selected) >= max_per_book:
                    break
                selected.append(item)
            capped.extend(selected)
        matched_entries = capped

    # Se `max_entries` è richiesto, seleziona le voci più informative e poi riordina cronologicamente
    if max_entries is not None and max_entries >= 0 and len(matched_entries) > max_entries:
        matched_entries.sort(
            key=lambda x: (
                -(1 if x.vs_dispute else 0),
                -x.relevance_score,
                0 if x.sort_year is not None else 1,
                x.unit_pk,
            )
        )
        matched_entries = matched_entries[:max_entries]

    # Ordinamento cronologico finale: prima i datati dal più antico al più recente, poi i non datati
    matched_entries.sort(
        key=lambda x: (
            1 if x.sort_year is None else 0,
            x.sort_year if x.sort_year is not None else 99999,
            x.book_pk,
            x.page_start if x.page_start is not None else 0,
            x.unit_pk,
        )
    )

    by_mode_dict: Dict[str, List[SynopticEntry]] = defaultdict(list)
    mode_counts: Counter[str] = Counter()
    places_cnt: Counter[str] = Counter()
    disc_cnt: Counter[str] = Counter()
    disputes_list: List[SynopticDisputeHighlight] = []
    actors_seen: set[str] = set()
    books_seen: set[int] = set()
    dated_years: List[int] = []

    for e in matched_entries:
        by_mode_dict[e.mode].append(e)
        mode_counts[e.mode] += 1
        books_seen.add(e.book_pk)
        for a in e.who:
            actors_seen.add(a.casefold())
        places_cnt.update(e.places)
        disc_cnt.update(e.macro_disciplines)
        if e.sort_year is not None:
            dated_years.append(e.sort_year)
        if e.vs_dispute:
            disputes_list.append(
                SynopticDisputeHighlight(
                    unit_pk=e.unit_pk,
                    block_pk=e.block_pk,
                    block_uid=e.block_uid,
                    book_pk=e.book_pk,
                    book_title=e.book_title,
                    page_start=e.page_start,
                    printed_page=e.printed_page,
                    who=e.who,
                    sort_year=e.sort_year,
                    when_label=e.when_label,
                    vs_dispute=e.vs_dispute,
                    stmt=e.stmt,
                    verbatim_quote=e.verbatim_quote,
                )
            )

    span: Tuple[Optional[int], Optional[int]] = (
        (min(dated_years), max(dated_years)) if dated_years else (None, None)
    )
    by_mode_frozen = {m: tuple(lst) for m, lst in sorted(by_mode_dict.items())}

    return SynopticReport(
        query=raw_query,
        normalized_terms=terms,
        total_entries=len(matched_entries),
        distinct_books=len(books_seen),
        distinct_actors=len(actors_seen),
        chronological_span=span,
        mode_counts=dict(sorted(mode_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        disputes_count=len(disputes_list),
        disputes=tuple(disputes_list),
        by_mode=by_mode_frozen,
        timeline=tuple(matched_entries),
        top_places=tuple(pl for pl, _ in places_cnt.most_common(12)),
        top_disciplines=tuple(d for d, _ in disc_cnt.most_common(12)),
    )


def _format_synoptic_report(report: SynopticReport) -> str:
    min_y, max_y = report.chronological_span
    span_str = f"{min_y} → {max_y}" if min_y is not None else "n.d."
    modes_str = ", ".join(f"{MODE_LABELS_IT.get(m, m)}={c}" for m, c in report.mode_counts.items())
    lines: List[str] = [
        f"\n=== Decompressore Sinottico: «{report.query}» ===",
        f"Voci ancorate: {report.total_entries} | Libri distinti: {report.distinct_books} | "
        f"Attori: {report.distinct_actors} | Arco cronologico: {span_str} | Controversie (`vs`): {report.disputes_count}",
        f"Distribuzione modale: {modes_str or 'nessuna'}",
    ]
    if report.top_places:
        lines.append(f"Luoghi: {', '.join(report.top_places[:8])}")
    if report.disputes:
        lines.append("\n--- Controversie / Critiche (`vs_dispute`) ---")
        for d in report.disputes[:6]:
            who_s = ", ".join(d.who[:3]) if d.who else "Autore"
            lines.append(
                f"  • [{d.when_label}] {who_s} in {d.book_title[:55]} (p.{d.printed_page or d.page_start}, blk #{d.block_pk})"
            )
            lines.append(f"    vs: {d.vs_dispute}")
            lines.append(f"    «{d.verbatim_quote[:160]}»")

    lines.append("\n--- Linea Cronologica e Modale ---")
    for e in report.timeline:
        who_s = ", ".join(e.who[:3]) if e.who else "N.D."
        place_s = f" | Dove: {', '.join(e.places[:3])}" if e.places else ""
        vs_s = f" | VS: {e.vs_dispute}" if e.vs_dispute else ""
        lines.append(
            f"  [{e.when_label:11s}] [{e.mode_label_it:18s}] {who_s} — {e.source_locator}{place_s}"
        )
        lines.append(f"     {e.stmt}{vs_s}")
        lines.append(f"     «{e.verbatim_quote[:160]}»")
    return "\n".join(lines)


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decompressore Sinottico Cronologico e Modale sull'intero corpus (TASK-SPEC-03)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso a pack_corpus.db")
    parser.add_argument("--concept", type=str, required=True, help="Concetto o query da decomprimere")
    parser.add_argument("--modes", type=str, help="Lista separata da virgole (es. defines,proves,critiques)")
    parser.add_argument("--only-disputes", action="store_true", help="Mostra solo voci con vs_dispute esplicito")
    parser.add_argument("--max-entries", type=int, default=20, help="Limite voci mostrate (0 = tutte)")
    parser.add_argument("--max-per-book", type=int, default=2, help="Limite voci per singolo libro (0 = illimitato)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    modes_arg = [m.strip() for m in args.modes.split(",")] if args.modes else None
    conn = connect_corpus_db(args.db, read_only=True)
    try:
        report = decompress_concept(
            conn,
            args.concept,
            modes=modes_arg,
            only_disputes=args.only_disputes,
            max_entries=None if args.max_entries <= 0 else args.max_entries,
            max_per_book=None if args.max_per_book <= 0 else args.max_per_book,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(_format_synoptic_report(report))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
