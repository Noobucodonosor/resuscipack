"""Calcolo deterministico dello Spettro Disciplinare Percentuale per Libro (ADR-0004, TASK-SPEC-01).

Aggrega in forma pura SQLite + Python i metadati `BlockExtraction v2.2` pesati per `char_count`:
- `coverage_pct(d)`: percentuale dei caratteri sostanziali del libro in cui compare la disciplina `d`.
- `share_pct(d)`: composizione tematica normalizzata a somma 100.0% (`w = 1 / |disc(b)|`).
- `block_pks_json`: elenco completo e ordinato di tutti i `block_pk` (zero `.slice()`).
- `book_spectrum_meta`: profilo non-distruttivo per libro con `quality_tier` per isolare cataloghi/CV/noise
  senza mai alterare o cancellare record in `books` o `blocks`.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..corpus.schema import DEFAULT_DB_PATH, SCHEMA_DDL, connect_corpus_db
from .schema_v21 import ALL_MACRO_DISCIPLINES, MacroDiscipline

MACRO_DISCIPLINE_LABELS_IT: Dict[str, str] = {
    MacroDiscipline.MATEMATICA.value: "Matematica",
    MacroDiscipline.LOGICA.value: "Logica",
    MacroDiscipline.INFORMATICA.value: "Informatica",
    MacroDiscipline.CRITTOGRAFIA_SICUREZZA.value: "Crittografia e Sicurezza",
    MacroDiscipline.FISICA.value: "Fisica",
    MacroDiscipline.ASTRONOMIA_COSMOLOGIA.value: "Astronomia e Cosmologia",
    MacroDiscipline.CHIMICA_MATERIALI.value: "Chimica e Scienza dei Materiali",
    MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA.value: "Biologia, Fisiologia e Medicina",
    MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value: "Geografia, Cartografia e Territorio",
    MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value: "Nautica, Navigazione e Meteorologia",
    MacroDiscipline.INGEGNERIA_MECCANICA_ELETTRONICA.value: "Ingegneria Meccanica ed Elettronica",
    MacroDiscipline.TELECOMUNICAZIONI_SEGNALI.value: "Telecomunicazioni e Segnali",
    MacroDiscipline.STORIA_POLITICA_MILITARE.value: "Storia, Politica e Storia Militare",
    MacroDiscipline.ECONOMIA_COMMERCIO_ASSICURAZIONI.value: "Economia, Commercio e Assicurazioni",
    MacroDiscipline.DIRITTO_ISTITUZIONI.value: "Diritto e Istituzioni",
    MacroDiscipline.FILOSOFIA_EPISTEMOLOGIA.value: "Filosofia ed Epistemologia",
    MacroDiscipline.LETTERATURA_RETORICA_FILOLOGIA.value: "Letteratura, Retorica e Filologia",
    MacroDiscipline.MUSICA_ACUSTICA.value: "Musica e Acustica",
    MacroDiscipline.ARTE_ARCHITETTURA_DISEGNO.value: "Arte, Architettura e Disegno",
    MacroDiscipline.PSICOLOGIA_PEDAGOGIA_SOCIETA.value: "Psicologia, Pedagogia e Società",
    MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value: "Agronomia, Scienze Naturali e Alimentazione",
    MacroDiscipline.ARTI_PRATICHE_ARTIGIANATO.value: "Arti Pratiche e Artigianato",
}

DISCIPLINE_ALIASES: Dict[str, str] = {
    # Alias storici di ADR-0004 e Issue #5 + sinonimi naturali italiani/inglesi
    "geografia_territorio": MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
    "geografia_e_territorio": MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
    "geografia": MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
    "geography": MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
    "cartografia": MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
    "territorio": MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value,
    "nautica_mare": MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value,
    "nautica": MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value,
    "navigazione": MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value,
    "meteo": MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value,
    "meteorologia": MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO.value,
    "economia": MacroDiscipline.ECONOMIA_COMMERCIO_ASSICURAZIONI.value,
    "commercio": MacroDiscipline.ECONOMIA_COMMERCIO_ASSICURAZIONI.value,
    "assicurazioni": MacroDiscipline.ECONOMIA_COMMERCIO_ASSICURAZIONI.value,
    "filosofia": MacroDiscipline.FILOSOFIA_EPISTEMOLOGIA.value,
    "epistemologia": MacroDiscipline.FILOSOFIA_EPISTEMOLOGIA.value,
    "medicina_biologia": MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA.value,
    "medicina": MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA.value,
    "biologia": MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA.value,
    "fisiologia": MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA.value,
    "storia_politica_economica": MacroDiscipline.STORIA_POLITICA_MILITARE.value,
    "storia_della_scienza": MacroDiscipline.STORIA_POLITICA_MILITARE.value,
    "storia": MacroDiscipline.STORIA_POLITICA_MILITARE.value,
    "politica": MacroDiscipline.STORIA_POLITICA_MILITARE.value,
    "militare": MacroDiscipline.STORIA_POLITICA_MILITARE.value,
    "diritto_societa": MacroDiscipline.DIRITTO_ISTITUZIONI.value,
    "diritto": MacroDiscipline.DIRITTO_ISTITUZIONI.value,
    "istituzioni": MacroDiscipline.DIRITTO_ISTITUZIONI.value,
    "arte_architettura": MacroDiscipline.ARTE_ARCHITETTURA_DISEGNO.value,
    "arte": MacroDiscipline.ARTE_ARCHITETTURA_DISEGNO.value,
    "architettura": MacroDiscipline.ARTE_ARCHITETTURA_DISEGNO.value,
    "disegno": MacroDiscipline.ARTE_ARCHITETTURA_DISEGNO.value,
    "telecomunicazioni_elettronica": MacroDiscipline.TELECOMUNICAZIONI_SEGNALI.value,
    "telecomunicazioni": MacroDiscipline.TELECOMUNICAZIONI_SEGNALI.value,
    "segnali": MacroDiscipline.TELECOMUNICAZIONI_SEGNALI.value,
    "radio": MacroDiscipline.TELECOMUNICAZIONI_SEGNALI.value,
    "ingegneria": MacroDiscipline.INGEGNERIA_MECCANICA_ELETTRONICA.value,
    "meccanica": MacroDiscipline.INGEGNERIA_MECCANICA_ELETTRONICA.value,
    "elettronica": MacroDiscipline.INGEGNERIA_MECCANICA_ELETTRONICA.value,
    "musica": MacroDiscipline.MUSICA_ACUSTICA.value,
    "acustica": MacroDiscipline.MUSICA_ACUSTICA.value,
    "letteratura": MacroDiscipline.LETTERATURA_RETORICA_FILOLOGIA.value,
    "retorica": MacroDiscipline.LETTERATURA_RETORICA_FILOLOGIA.value,
    "filologia": MacroDiscipline.LETTERATURA_RETORICA_FILOLOGIA.value,
    "astronomia": MacroDiscipline.ASTRONOMIA_COSMOLOGIA.value,
    "cosmologia": MacroDiscipline.ASTRONOMIA_COSMOLOGIA.value,
    "chimica": MacroDiscipline.CHIMICA_MATERIALI.value,
    "materiali": MacroDiscipline.CHIMICA_MATERIALI.value,
    "crittografia": MacroDiscipline.CRITTOGRAFIA_SICUREZZA.value,
    "sicurezza": MacroDiscipline.CRITTOGRAFIA_SICUREZZA.value,
    "psicologia": MacroDiscipline.PSICOLOGIA_PEDAGOGIA_SOCIETA.value,
    "pedagogia": MacroDiscipline.PSICOLOGIA_PEDAGOGIA_SOCIETA.value,
    "societa": MacroDiscipline.PSICOLOGIA_PEDAGOGIA_SOCIETA.value,
    "agronomia": MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value,
    "scienze_naturali": MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value,
    "botanica_scienze_naturali": MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value,
    "botanica": MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value,
    "cibo": MacroDiscipline.AGRONOMIA_SCIENZE_NATURALI_CIBO.value,
    "arti_pratiche": MacroDiscipline.ARTI_PRATICHE_ARTIGIANATO.value,
    "artigianato": MacroDiscipline.ARTI_PRATICHE_ARTIGIANATO.value,
}


def _slugify_discipline_input(raw: str) -> str:
    txt = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode("ascii")
    txt = re.sub(r"[^a-zA-Z0-9]+", "_", txt.strip().lower()).strip("_")
    return txt


_LABEL_SLUG_TO_CANONICAL: Dict[str, str] = {
    _slugify_discipline_input(label): canon for canon, label in MACRO_DISCIPLINE_LABELS_IT.items()
}


def resolve_macro_discipline(raw: str | MacroDiscipline) -> MacroDiscipline:
    """Risolve uno slug canonico, un alias legacy o un nome leggibile in `MacroDiscipline`."""
    if isinstance(raw, MacroDiscipline):
        return raw
    slug = _slugify_discipline_input(raw)
    if not slug:
        raise ValueError("Disciplina vuota non valida")
    if slug in ALL_MACRO_DISCIPLINES:
        return MacroDiscipline(slug)
    if slug in DISCIPLINE_ALIASES:
        return MacroDiscipline(DISCIPLINE_ALIASES[slug])
    if slug in _LABEL_SLUG_TO_CANONICAL:
        return MacroDiscipline(_LABEL_SLUG_TO_CANONICAL[slug])

    # Fallback univoco solo se il prefisso identifica esattamente 1 macro-disciplina
    matches = [d for d in ALL_MACRO_DISCIPLINES if d.startswith(slug + "_")]
    if len(matches) == 1:
        return MacroDiscipline(matches[0])

    raise ValueError(
        f"Disciplina sconosciuta: {raw!r}. Valori ammessi: {sorted(ALL_MACRO_DISCIPLINES)}"
    )


def label_for_discipline(discipline: str | MacroDiscipline) -> str:
    """Restituisce l'etichetta editoriale italiana per una macro-disciplina."""
    key = discipline.value if isinstance(discipline, MacroDiscipline) else str(discipline)
    return MACRO_DISCIPLINE_LABELS_IT.get(key, key.replace("_", " ").title())


# Pattern chirurgici non-distruttivi per documenti commerciali/amministrativi/cataloghi finiti in Wave 0
_NON_BOOK_NOISE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"disponibilit[aà']|(?:^|[\s_-])primigi(?:$|[\s_-])|collection\s+fall\s+winter", re.I), "commercial_stock_list"),
    (re.compile(r"curriculum\s*vitae|(?:^|[\s_-])cv(?:$|[\s_-])", re.I), "personal_cv"),
    (re.compile(r"domanda[_\s]+(?:firmata|iscrizione)|modulo\s+assegni", re.I), "administrative_form"),
    (re.compile(r"^(?:ricevuta|fattura|preventivo|listino)(?:\b|$)", re.I), "commercial_receipt_or_list"),
    (re.compile(r"(?:^|[\s_-])(?:bando|brochure)(?:$|[\s_-])", re.I), "promotional_brochure_or_call"),
    (re.compile(r"tavola\s+programmazione|^layout\s*\d|bozza\s+regolamento", re.I), "institutional_schedule_or_layout"),
    (re.compile(r"triax_catalogo|^tech_cat$|^1fing\d+", re.I), "hardware_catalog_or_study_plan"),
)

_REFERENCE_MANUAL_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^fullrefman$", re.I), "r_package_reference_manual"),
    (re.compile(r"^bt\s*\d+|guida\s+all['’]installazione.*bticino", re.I), "electrical_product_manual"),
)

_DIDACTIC_NOTE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"diapositiva\s+\d|^esercizi\s+", re.I), "slide_or_exercise_sheet"),
)


def classify_book_quality_tier(
    title: str,
    *,
    active_blocks_count: int,
    v22_blocks_count: int,
    total_v22_chars: int,
) -> Tuple[str, Optional[str]]:
    """Classifica in modo deterministico e non-distruttivo la natura editoriale di un record in `books`."""
    title_nfc = unicodedata.normalize("NFC", str(title or "")).strip()
    for pat, reason in _NON_BOOK_NOISE_PATTERNS:
        if pat.search(title_nfc):
            return "non_book_noise", reason
    for pat, reason in _REFERENCE_MANUAL_PATTERNS:
        if pat.search(title_nfc):
            return "reference_manual", reason
    if v22_blocks_count <= 0 or total_v22_chars <= 0 or active_blocks_count <= 0:
        return "didactic_notes", "zero_substantive_v22_blocks"
    for pat, reason in _DIDACTIC_NOTE_PATTERNS:
        if pat.search(title_nfc):
            return "didactic_notes", reason
    return "canonical_book", None


_PARATEXT_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s*)?(?:"
    r"indice(?:\s+(?:generale|analitico|dei\s+nomi|delle\s+materie|sommario|dei\s+capitoli))?"
    r"|sommario|table\s+of\s+contents|contents|bibliografia|riferimenti\s+bibliografici"
    r"|references|bibliography|further\s+reading(?:\s+and\s+references)?|index|nota\s+bibliografica"
    r")\s*:?\s*$",
    re.IGNORECASE,
)
_BIBLIO_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s*)?(?:bibliografia|riferimenti\s+bibliografici|references|bibliography"
    r"|further\s+reading(?:\s+and\s+references)?|nota\s+bibliografica)\s*:?\s*$",
    re.IGNORECASE,
)
_INLINE_CAPS_PARATEXT_RE = re.compile(
    r"(?:^|\n)\s*(?:SOMMARIO|INDICE\s+GENERALE|INDICE\s+ANALITICO|INDICE\s+DEI\s+NOMI|"
    r"TABLE\s+OF\s+CONTENTS|BIBLIOGRAFIA|BIBLIOGRAPHY|FURTHER\s+READING\s+AND\s+REFERENCES)\b"
)
_INLINE_CAPS_BIBLIO_RE = re.compile(
    r"(?:^|\n)\s*(?:BIBLIOGRAFIA|BIBLIOGRAPHY|FURTHER\s+READING\s+AND\s+REFERENCES|NOTA\s+BIBLIOGRAFICA)\b"
)
_PAGE_MARKER_LINE_RE = re.compile(r"^#{1,4}\s*pagina\s+\d+\s*$", re.IGNORECASE)
_DOTTED_TOC_LINE_RE = re.compile(r"\.{4,}\s*\d+\s*$")
_INDEX_LOCATOR_LINE_RE = re.compile(r",\s*\d+(?:\s*[-–,]\s*\d+){2,}\.?\s*$")


def _looks_like_reasoned_bibliography(content: str) -> bool:
    """Riconosce bibliografie ragionate o note critiche con prosa discorsiva (non meri elenchi)."""
    lines = [
        ln.strip()
        for ln in (content or "").splitlines()
        if ln.strip() and not _PAGE_MARKER_LINE_RE.match(ln.strip())
    ]
    if not lines:
        return False
    if len(lines) >= 4:
        dotted = sum(1 for ln in lines if _DOTTED_TOC_LINE_RE.search(ln))
        indexed = sum(1 for ln in lines if _INDEX_LOCATOR_LINE_RE.search(ln))
        if dotted / len(lines) >= 0.25 or indexed / len(lines) >= 0.25:
            return False

    body_text = " ".join(lines)
    sentences = [s.strip() for s in re.split(r"(?<=[.;?!])\s+", body_text) if len(s.strip()) >= 75]
    prose_sentences = [
        s
        for s in sentences
        if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", s)) >= 12
        and not _DOTTED_TOC_LINE_RE.search(s)
        and not _INDEX_LOCATOR_LINE_RE.search(s)
    ]
    if len(prose_sentences) >= 2:
        return True

    alpha_chars = sum(1 for ch in body_text if ch.isalpha())
    avg_len = sum(len(ln) for ln in lines) / len(lines)
    return alpha_chars >= 600 and avg_len >= 48.0


def is_residual_paratext_block(section_title: str, content: str) -> bool:
    """Rileva blocchi residui di indice/sommario/bibliografia meccanica, preservando bibliografie ragionate."""
    sec = (section_title or "").strip()
    lines = [ln.strip() for ln in (content or "").splitlines() if ln.strip()]
    if not lines:
        return True

    if len(lines) >= 4:
        dotted = sum(1 for ln in lines if _DOTTED_TOC_LINE_RE.search(ln))
        indexed = sum(1 for ln in lines if _INDEX_LOCATOR_LINE_RE.search(ln))
        if dotted / len(lines) >= 0.45 or indexed / len(lines) >= 0.45:
            return True

    raw_head = (content or "")[:360]
    non_page_lines = [ln for ln in lines[:8] if not _PAGE_MARKER_LINE_RE.match(ln)]
    first_non_page = non_page_lines[0] if non_page_lines else ""

    is_biblio = bool(
        (sec and _BIBLIO_HEADING_RE.match(sec))
        or _INLINE_CAPS_BIBLIO_RE.search(raw_head)
        or (first_non_page and _BIBLIO_HEADING_RE.match(first_non_page))
    )
    if is_biblio and _looks_like_reasoned_bibliography(content):
        return False

    if sec and _PARATEXT_HEADING_RE.match(sec):
        return True
    if _INLINE_CAPS_PARATEXT_RE.search(raw_head):
        return True
    if first_non_page and _PARATEXT_HEADING_RE.match(first_non_page):
        return True

    return False


def _ensure_spectrum_schema(conn: sqlite3.Connection) -> None:
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('book_discipline_spectrum', 'book_spectrum_meta')"
        ).fetchall()
    }
    if len(existing) < 2:
        conn.executescript(SCHEMA_DDL)


def _clean_str_list(raw_json: Optional[str]) -> List[str]:
    if not raw_json:
        return []
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for item in parsed:
        val = " ".join(str(item or "").split()).strip()
        if not val:
            continue
        key = val.casefold()
        if key not in seen:
            seen.add(key)
            out.append(val)
    return out


def compute_all_book_spectra(
    db_or_conn: Path | str | sqlite3.Connection = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Calcola e persiste `book_discipline_spectrum` e `book_spectrum_meta` su tutti i libri attivi.

    Operazione puramente deterministica in due query single-pass O(N) senza chiamate LLM e senza
    troncamenti (`block_pks_json` contiene sempre il 100% dei blocchi di quella disciplina nel libro).
    """
    owns_conn = not isinstance(db_or_conn, sqlite3.Connection)
    conn = connect_corpus_db(db_or_conn, read_only=False) if owns_conn else db_or_conn
    conn.row_factory = sqlite3.Row

    try:
        _ensure_spectrum_schema(conn)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Passata 1: censimento libri attivi e conteggio blocchi attivi (senza LEFT JOIN per evitare piani quadratici SQLite)
        active_books = conn.execute(
            "SELECT book_pk, title FROM books WHERE is_active = 1 ORDER BY book_pk ASC"
        ).fetchall()
        book_titles: Dict[int, str] = {int(r["book_pk"]): str(r["title"]) for r in active_books}
        book_active_counts: Dict[int, int] = {
            int(r["book_pk"]): int(r["cnt"] or 0)
            for r in conn.execute(
                "SELECT book_pk, COUNT(*) AS cnt FROM blocks WHERE is_active = 1 GROUP BY book_pk"
            ).fetchall()
        }

        # Passata 2: scansione single-pass dei blocchi attivi con metadati v2.2 (ordinamento in Python)
        v22_rows = conn.execute(
            """
            SELECT
                b.book_pk,
                b.block_pk,
                b.char_count,
                b.page_start,
                m.macro_disciplines_json,
                m.emergent_topics_json,
                m.places_json
            FROM blocks b
            JOIN block_metadata_v22 m ON m.block_pk = b.block_pk
            JOIN books bk ON bk.book_pk = b.book_pk
            WHERE b.is_active = 1
              AND bk.is_active = 1
              AND b.block_role != 'paratext'
            """
        ).fetchall()

        per_book_total_chars: Dict[int, int] = defaultdict(int)
        per_book_v22_count: Dict[int, int] = defaultdict(int)
        per_book_cov_chars: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        per_book_raw_share: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        per_book_pks: Dict[int, Dict[str, List[Tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
        per_book_topics: Dict[int, Dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
        per_book_places: Dict[int, Dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))

        malformed_v22_blocks = 0
        for row in v22_rows:
            book_pk = int(row["book_pk"])
            block_pk = int(row["block_pk"])
            page_start = int(row["page_start"] or 0)
            weight = max(1, int(row["char_count"] or 0))

            raw_discs = _clean_str_list(row["macro_disciplines_json"])
            valid_discs: List[str] = []
            seen_d: set[str] = set()
            has_unknown = False
            for d in raw_discs:
                if d in ALL_MACRO_DISCIPLINES and d not in seen_d:
                    seen_d.add(d)
                    valid_discs.append(d)
                elif d not in ALL_MACRO_DISCIPLINES:
                    has_unknown = True

            if has_unknown or not valid_discs:
                malformed_v22_blocks += 1
                if not valid_discs:
                    continue

            topics = _clean_str_list(row["emergent_topics_json"])
            places = _clean_str_list(row["places_json"])

            per_book_v22_count[book_pk] += 1
            per_book_total_chars[book_pk] += weight
            split_weight = weight / len(valid_discs)

            for disc in valid_discs:
                per_book_cov_chars[book_pk][disc] += weight
                per_book_raw_share[book_pk][disc] += split_weight
                per_book_pks[book_pk][disc].append((page_start, block_pk))
                if topics:
                    per_book_topics[book_pk][disc].update(topics)
                if places:
                    per_book_places[book_pk][disc].update(places)

        spectrum_inserts: List[Tuple[Any, ...]] = []
        meta_inserts: List[Tuple[Any, ...]] = []
        tier_counts: Counter[str] = Counter()
        max_share_sum_deviation = 0.0
        books_with_spectrum = 0

        for book_pk, title in book_titles.items():
            v22_cnt = per_book_v22_count.get(book_pk, 0)
            tot_chars = per_book_total_chars.get(book_pk, 0)
            act_cnt = book_active_counts.get(book_pk, 0)
            tier, noise_reason = classify_book_quality_tier(
                title,
                active_blocks_count=act_cnt,
                v22_blocks_count=v22_cnt,
                total_v22_chars=tot_chars,
            )
            tier_counts[tier] += 1

            if v22_cnt == 0 or tot_chars == 0:
                meta_inserts.append(
                    (
                        book_pk,
                        act_cnt,
                        v22_cnt,
                        tot_chars,
                        0,
                        None,
                        0.0,
                        0.0,
                        tier,
                        noise_reason,
                        now_iso,
                    )
                )
                continue

            books_with_spectrum += 1
            raw_shares = per_book_raw_share[book_pk]
            cov_chars = per_book_cov_chars[book_pk]
            pks_map = per_book_pks[book_pk]

            # Ordinamento deterministico decrescente per quota, copertura, poi nome disciplina
            ordered_discs = sorted(
                raw_shares.keys(),
                key=lambda d: (-raw_shares[d], -cov_chars[d], d),
            )

            shares_pct: Dict[str, float] = {
                d: round(100.0 * raw_shares[d] / tot_chars, 2) for d in ordered_discs
            }
            # Correzione deterministica del residuo di arrotondamento sulla disciplina dominante
            residual = round(100.0 - sum(shares_pct.values()), 2)
            if abs(residual) > 0.0 and ordered_discs:
                top_d = ordered_discs[0]
                shares_pct[top_d] = round(max(0.0, shares_pct[top_d] + residual), 2)

            share_sum = sum(shares_pct.values())
            max_share_sum_deviation = max(max_share_sum_deviation, abs(100.0 - share_sum))

            distinct_n = len(ordered_discs)
            if distinct_n <= 1:
                entropy_norm = 0.0
            else:
                h_val = 0.0
                for d in ordered_discs:
                    p = raw_shares[d] / tot_chars
                    if p > 0.0:
                        h_val -= p * math.log2(p)
                entropy_norm = round(h_val / math.log2(distinct_n), 4)

            primary_d = ordered_discs[0]
            primary_share = shares_pct[primary_d]

            meta_inserts.append(
                (
                    book_pk,
                    act_cnt,
                    v22_cnt,
                    tot_chars,
                    distinct_n,
                    primary_d,
                    primary_share,
                    entropy_norm,
                    tier,
                    noise_reason,
                    now_iso,
                )
            )

            for d in ordered_discs:
                pks_list = [pk for _, pk in sorted(pks_map[d])]
                cov_pct = round(100.0 * cov_chars[d] / tot_chars, 2)
                top_topics = [t for t, _ in per_book_topics[book_pk][d].most_common(12)]
                top_places = [pl for pl, _ in per_book_places[book_pk][d].most_common(12)]
                spectrum_inserts.append(
                    (
                        book_pk,
                        d,
                        len(pks_list),
                        int(cov_chars[d]),
                        cov_pct,
                        shares_pct[d],
                        json.dumps(pks_list, ensure_ascii=False),
                        json.dumps(top_topics, ensure_ascii=False),
                        json.dumps(top_places, ensure_ascii=False),
                        now_iso,
                    )
                )

        conn.execute("DELETE FROM book_discipline_spectrum")
        conn.execute("DELETE FROM book_spectrum_meta")
        conn.executemany(
            """
            INSERT INTO book_spectrum_meta (
                book_pk, active_blocks_count, v22_blocks_count, total_v22_chars,
                distinct_disciplines, primary_discipline, primary_share_pct,
                shannon_entropy_norm, quality_tier, noise_reason, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            meta_inserts,
        )
        conn.executemany(
            """
            INSERT INTO book_discipline_spectrum (
                book_pk, macro_discipline, block_count, char_count,
                coverage_pct, share_pct, block_pks_json,
                top_topics_json, top_places_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            spectrum_inserts,
        )
        conn.commit()

        return {
            "books_total_active": len(book_titles),
            "books_with_spectrum": books_with_spectrum,
            "books_without_v22": len(book_titles) - books_with_spectrum,
            "spectrum_rows_written": len(spectrum_inserts),
            "quality_tier_counts": dict(sorted(tier_counts.items())),
            "max_share_sum_deviation": round(max_share_sum_deviation, 4),
            "malformed_v22_blocks": malformed_v22_blocks,
        }
    finally:
        if owns_conn:
            conn.close()


def get_book_spectrum(
    conn: sqlite3.Connection,
    book_pk: int,
    *,
    min_coverage_pct: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """Restituisce profilo e spettro disciplinare completo (con tutti i `block_pks`) di un libro."""
    conn.row_factory = sqlite3.Row
    book_row = conn.execute(
        """
        SELECT
            bk.book_pk, bk.book_uid, bk.title, bk.author, bk.year,
            bk.surface_domain, bk.language, bk.is_active,
            m.active_blocks_count, m.v22_blocks_count, m.total_v22_chars,
            m.distinct_disciplines, m.primary_discipline, m.primary_share_pct,
            m.shannon_entropy_norm, m.quality_tier, m.noise_reason
        FROM books bk
        LEFT JOIN book_spectrum_meta m ON m.book_pk = bk.book_pk
        WHERE bk.book_pk = ?
        """,
        (int(book_pk),),
    ).fetchone()
    if book_row is None:
        return None

    spec_rows = conn.execute(
        """
        SELECT
            macro_discipline, block_count, char_count,
            coverage_pct, share_pct, block_pks_json,
            top_topics_json, top_places_json
        FROM book_discipline_spectrum
        WHERE book_pk = ?
        ORDER BY share_pct DESC, coverage_pct DESC, macro_discipline ASC
        """,
        (int(book_pk),),
    ).fetchall()

    all_disciplines: List[Dict[str, Any]] = []
    for r in spec_rows:
        disc_key = str(r["macro_discipline"])
        all_disciplines.append(
            {
                "macro_discipline": disc_key,
                "label_it": label_for_discipline(disc_key),
                "block_count": int(r["block_count"]),
                "char_count": int(r["char_count"]),
                "coverage_pct": float(r["coverage_pct"]),
                "share_pct": float(r["share_pct"]),
                "block_pks": [int(pk) for pk in json.loads(r["block_pks_json"] or "[]")],
                "top_topics": json.loads(r["top_topics_json"] or "[]"),
                "top_places": json.loads(r["top_places_json"] or "[]"),
            }
        )

    share_sum_pct = round(sum(d["share_pct"] for d in all_disciplines), 2)
    filtered_disciplines = [
        d for d in all_disciplines if d["coverage_pct"] >= float(min_coverage_pct)
    ]

    prim = book_row["primary_discipline"]
    return {
        "book_pk": int(book_row["book_pk"]),
        "book_uid": str(book_row["book_uid"]),
        "title": str(book_row["title"]),
        "author": book_row["author"],
        "year": book_row["year"],
        "surface_domain": str(book_row["surface_domain"]),
        "language": book_row["language"],
        "is_active": int(book_row["is_active"]),
        "active_blocks_count": int(book_row["active_blocks_count"] or 0),
        "v22_blocks_count": int(book_row["v22_blocks_count"] or 0),
        "total_v22_chars": int(book_row["total_v22_chars"] or 0),
        "distinct_disciplines": int(book_row["distinct_disciplines"] or len(all_disciplines)),
        "primary_discipline": prim,
        "primary_discipline_label": label_for_discipline(prim) if prim else None,
        "primary_share_pct": float(book_row["primary_share_pct"] or 0.0),
        "shannon_entropy_norm": float(book_row["shannon_entropy_norm"] or 0.0),
        "quality_tier": str(book_row["quality_tier"] or "canonical_book"),
        "noise_reason": book_row["noise_reason"],
        "share_sum_pct": share_sum_pct,
        "disciplines": filtered_disciplines,
    }


def list_books_by_discipline(
    conn: sqlite3.Connection,
    target_discipline: str | MacroDiscipline,
    *,
    exclude_non_book_noise: bool = True,
    exclude_reference_manuals: bool = False,
    exclude_primary_match: bool = False,
    min_coverage_pct: float = 0.0,
    min_block_count: int = 1,
) -> List[Dict[str, Any]]:
    """Elenca tutti i libri che contengono `target_discipline`, ordinati per copertura e densità."""
    conn.row_factory = sqlite3.Row
    target = resolve_macro_discipline(target_discipline).value

    clauses = [
        "bk.is_active = 1",
        "s.macro_discipline = ?",
        "s.coverage_pct >= ?",
        "s.block_count >= ?",
    ]
    params: List[Any] = [target, float(min_coverage_pct), int(min_block_count)]
    if exclude_non_book_noise:
        clauses.append("COALESCE(m.quality_tier, 'canonical_book') != 'non_book_noise'")
    if exclude_reference_manuals:
        clauses.append("COALESCE(m.quality_tier, 'canonical_book') != 'reference_manual'")
    if exclude_primary_match:
        clauses.append("COALESCE(m.primary_discipline, '') != ?")
        params.append(target)

    where_sql = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT
            bk.book_pk, bk.book_uid, bk.title, bk.author, bk.year, bk.surface_domain,
            COALESCE(m.quality_tier, 'canonical_book') AS quality_tier,
            m.v22_blocks_count, m.primary_discipline, m.primary_share_pct,
            s.block_count, s.char_count, s.coverage_pct, s.share_pct,
            s.block_pks_json, s.top_topics_json, s.top_places_json
        FROM book_discipline_spectrum s
        JOIN books bk ON bk.book_pk = s.book_pk
        LEFT JOIN book_spectrum_meta m ON m.book_pk = s.book_pk
        WHERE {where_sql}
        ORDER BY s.coverage_pct DESC, s.block_count DESC, bk.book_pk ASC
        """,
        tuple(params),
    ).fetchall()

    results: List[Dict[str, Any]] = []
    for r in rows:
        prim = r["primary_discipline"]
        results.append(
            {
                "book_pk": int(r["book_pk"]),
                "book_uid": str(r["book_uid"]),
                "title": str(r["title"]),
                "author": r["author"],
                "year": r["year"],
                "surface_domain": str(r["surface_domain"]),
                "quality_tier": str(r["quality_tier"]),
                "v22_blocks_count": int(r["v22_blocks_count"] or 0),
                "primary_discipline": prim,
                "primary_discipline_label": label_for_discipline(prim) if prim else None,
                "primary_share_pct": float(r["primary_share_pct"] or 0.0),
                "macro_discipline": target,
                "label_it": label_for_discipline(target),
                "block_count": int(r["block_count"]),
                "char_count": int(r["char_count"]),
                "coverage_pct": float(r["coverage_pct"]),
                "share_pct": float(r["share_pct"]),
                "block_pks": [int(pk) for pk in json.loads(r["block_pks_json"] or "[]")],
                "top_topics": json.loads(r["top_topics_json"] or "[]"),
                "top_places": json.loads(r["top_places_json"] or "[]"),
            }
        )
    return results


def _print_book_spectrum(spec: Dict[str, Any]) -> None:
    print(
        f"\n=== [{spec['book_pk']}] {spec['title']} ===\n"
        f"  surface_domain={spec['surface_domain']} | quality_tier={spec['quality_tier']} | "
        f"v22_blocks={spec['v22_blocks_count']}/{spec['active_blocks_count']} | "
        f"chars={spec['total_v22_chars']:,} | entropy={spec['shannon_entropy_norm']:.3f} | "
        f"SUM(Share)={spec['share_sum_pct']:.2f}%"
    )
    for d in spec["disciplines"]:
        places_str = f" | luoghi: {', '.join(d['top_places'][:5])}" if d["top_places"] else ""
        print(
            f"  - {d['label_it']:42s} ({d['macro_discipline']}): "
            f"blks={d['block_count']:3d} | Cov={d['coverage_pct']:5.1f}% | "
            f"Share={d['share_pct']:5.1f}%{places_str}"
        )


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calcola o ispeziona lo Spettro Disciplinare Percentuale per Libro (TASK-SPEC-01)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso a pack_corpus.db")
    parser.add_argument("--rebuild", action="store_true", help="Ricalcola l'intero spettro in DB")
    parser.add_argument("--book-pk", type=int, action="append", help="Ispeziona uno o più book_pk")
    parser.add_argument("--title-search", type=str, help="Cerca libri per titolo e mostra il relativo spettro")
    parser.add_argument("--stats-only", action="store_true", help="Mostra solo il riepilogo aggregato del corpus")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary: Optional[Dict[str, Any]] = None
    if args.rebuild:
        summary = compute_all_book_spectra(args.db)

    conn = connect_corpus_db(args.db, read_only=True)
    try:
        output_payload: Dict[str, Any] = {}
        if summary is not None:
            output_payload["rebuild_summary"] = summary

        if args.stats_only or (not args.book_pk and not args.title_search):
            tiers = conn.execute(
                "SELECT quality_tier, COUNT(*) AS n FROM book_spectrum_meta GROUP BY quality_tier ORDER BY n DESC"
            ).fetchall()
            tot_spec = conn.execute("SELECT COUNT(*) FROM book_discipline_spectrum").fetchone()[0]
            bad_sums = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT book_pk, SUM(share_pct) AS s
                    FROM book_discipline_spectrum
                    GROUP BY book_pk
                    HAVING ABS(s - 100.0) > 0.1
                )
                """
            ).fetchone()[0]
            output_payload["corpus_stats"] = {
                "meta_rows": sum(int(r["n"]) for r in tiers),
                "spectrum_rows": int(tot_spec),
                "quality_tiers": {str(r["quality_tier"]): int(r["n"]) for r in tiers},
                "share_sum_violations": int(bad_sums),
            }

        specs: List[Dict[str, Any]] = []
        for bpk in args.book_pk or []:
            sp = get_book_spectrum(conn, bpk)
            if sp is not None:
                specs.append(sp)

        if args.title_search:
            hits = conn.execute(
                "SELECT book_pk FROM books WHERE is_active = 1 AND lower(title) LIKE ? ORDER BY book_pk ASC",
                (f"%{args.title_search.lower()}%",),
            ).fetchall()
            for r in hits:
                sp = get_book_spectrum(conn, int(r["book_pk"]))
                if sp is not None:
                    specs.append(sp)

        if specs:
            output_payload["books"] = specs

        if args.json:
            print(json.dumps(output_payload, ensure_ascii=False, indent=2))
        else:
            if "rebuild_summary" in output_payload:
                print("Rebuild:", json.dumps(output_payload["rebuild_summary"], ensure_ascii=False))
            if "corpus_stats" in output_payload:
                print("Corpus stats:", json.dumps(output_payload["corpus_stats"], ensure_ascii=False))
            for sp in specs:
                _print_book_spectrum(sp)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
