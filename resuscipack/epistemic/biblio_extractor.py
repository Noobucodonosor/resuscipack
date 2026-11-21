"""Grafo delle Fonti e Bibliografie Ragionate (`ADR-0005`, TASK-BIBLIO-01).

1. Selettore deterministico a €0 dei blocchi ad alta densità di fonti (inclusi i blocchi
   precedentemente classificati `low_or_paratext` come note bibliografiche critiche).
2. Verifica anti-allucinazione di `verbatim_quote`, classificazione di strato (`source_layer`)
   e presa di posizione (`stance`), più risoluzione automatica `resolved_book_pk`
   contro il catalogo attivo in `pack_corpus.db` (*in casa* vs *Wishlist Epistemica*).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from resuscipack.corpus.normalizer import normalize_for_match
from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db
from resuscipack.epistemic.schema_v21 import quote_matches_block_ocr_tolerant

SOURCE_LAYERS: Tuple[str, ...] = (
    "primary_ancient",
    "commentator_transmission",
    "critical_edition",
    "modern_historiography",
    "manual_monograph",
    "doxographer",
)

CITATION_STANCES: Tuple[str, ...] = (
    "recommends",
    "qualified_recommends",
    "critiques",
    "uses_as_source",
    "transmits_from",
    "warns_unreliable",
)

_TRANSMISSION_CUES_RE = re.compile(
    r"\b(?:secondo|tramandat[oa]\s+da|conservat[oa]\s+in|commento\s+(?:di|a)|ed\.?\s*crit|"
    r"edizione\s+critica|a\s+cura\s+di|trad\.\s*it\.?|op\.\s*cit\.?|fr\.\s*\d+|libro\s+[IVX]+|"
    r"nota\s+bibliografica|bibliografia\s+ragionata|si\s+veda\s+anche|cfr\.)\b",
    re.IGNORECASE,
)
_AUTHOR_YEAR_RE = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]{2,}(?:,\s*|\s+)\(?(?:1[5-9]\d{2}|20[0-2]\d)\)?")
_ANCIENT_SOURCES_RE = re.compile(
    r"\b(?:Proclo|Gemino|Eudemo|Simplicio|Diogene\s+Laerzio|Pappo|Plutarco|Aristotele|Platone|"
    r"Euclide|Archimede|Apollonio|Diofanto|Erone|Teone|Ippocrate|Heath|Tannery|Enriques|"
    r"Frajese|Loria|Zeuthen|Neugebauer|Van\s+der\s+Waerden)\b",
    re.IGNORECASE,
)


def score_block_bibliographic_density(section_title: str, content: str) -> Dict[str, Any]:
    """Calcola in modo deterministico (€0) la densità di fonti e commento critico di un blocco."""
    text = str(content or "").strip()
    if len(text) < 250:
        return {"score": 0, "cues": 0, "author_years": 0, "ancient_mentions": 0, "is_biblio_rich": False}

    cues = len(_TRANSMISSION_CUES_RE.findall(text))
    author_years = len(_AUTHOR_YEAR_RE.findall(text))
    ancient_mentions = len({m.group(0).casefold() for m in _ANCIENT_SOURCES_RE.finditer(text)})
    sec_bonus = 2 if re.search(r"bibliograf|fonti|sguardo\s+generale|storiograf|nota\s+critica", section_title or "", re.IGNORECASE) else 0
    score = cues + author_years + ancient_mentions + sec_bonus
    return {
        "score": score,
        "cues": cues,
        "author_years": author_years,
        "ancient_mentions": ancient_mentions,
        "is_biblio_rich": score >= 4 and (cues >= 1 or author_years >= 2 or ancient_mentions >= 2),
    }


def select_biblio_rich_blocks(
    conn: sqlite3.Connection,
    *,
    book_pk: Optional[int] = None,
    min_score: int = 4,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Seleziona a €0 i blocchi più ricchi di fonti e bibliografie ragionate (anche ex-`low_or_paratext`)."""
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT
            bl.block_pk,
            bl.block_uid,
            bl.book_pk,
            bk.title AS book_title,
            bk.author AS book_author,
            bl.page_start,
            bl.printed_page,
            bl.section_title,
            bl.block_role,
            bl.content,
            bel.yield AS extraction_yield
        FROM blocks bl
        JOIN books bk ON bk.book_pk = bl.book_pk
        LEFT JOIN block_extraction_log bel ON bel.block_pk = bl.block_pk
        WHERE bl.is_active = 1
          AND bk.is_active = 1
          AND LENGTH(bl.content) >= 250
    """
    params: List[Any] = []
    if book_pk is not None:
        sql += " AND bl.book_pk = ?"
        params.append(int(book_pk))
    sql += " ORDER BY bl.book_pk, bl.page_start, bl.block_pk"

    candidates: List[Dict[str, Any]] = []
    for r in conn.execute(sql, params):
        metrics = score_block_bibliographic_density(str(r["section_title"] or ""), str(r["content"] or ""))
        if metrics["score"] >= min_score and metrics["is_biblio_rich"]:
            candidates.append(
                {
                    "block_pk": int(r["block_pk"]),
                    "block_uid": r["block_uid"],
                    "book_pk": int(r["book_pk"]),
                    "book_title": r["book_title"],
                    "book_author": r["book_author"],
                    "page_start": r["page_start"],
                    "printed_page": r["printed_page"],
                    "section_title": r["section_title"],
                    "extraction_yield": r["extraction_yield"],
                    **metrics,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["book_pk"], item["page_start"] or 0))
    return candidates[: max(1, int(limit))]


def resolve_cited_book_pk(
    conn: sqlite3.Connection,
    cited_author: str,
    cited_work: str,
) -> Optional[int]:
    """Risolve deterministicamente se un'opera citata è presente in `books` (altrimenti None -> Wishlist)."""
    author_tokens = [t for t in normalize_for_match(cited_author).split() if len(t) >= 4]
    work_tokens = [t for t in normalize_for_match(cited_work).split() if len(t) >= 4]
    if not work_tokens and not author_tokens:
        return None

    rows = conn.execute(
        "SELECT book_pk, title, author FROM books WHERE is_active = 1"
    ).fetchall()
    best_pk: Optional[int] = None
    best_score = 0
    for r in rows:
        btitle = normalize_for_match(str(r["title"] or ""))
        bauth = normalize_for_match(str(r["author"] or ""))
        combined = f"{bauth} {btitle}".strip()
        a_hits = sum(1 for t in author_tokens if t in combined)
        w_hits = sum(1 for t in work_tokens if t in btitle)
        if work_tokens and w_hits == 0:
            continue
        if author_tokens and a_hits == 0 and w_hits < 2:
            continue
        score = w_hits * 2 + a_hits * 3
        if score > best_score and (w_hits >= 1 and (a_hits >= 1 or w_hits >= 2)):
            best_score = score
            best_pk = int(r["book_pk"])
    return best_pk


def validate_and_store_citations(
    conn: sqlite3.Connection,
    *,
    source_block_pk: int,
    block_content: str,
    citations: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Valida citazioni contro `block_content` (zero allucinazioni) e salva in `bibliographic_citations`."""
    inserted = 0
    rejected: List[Dict[str, str]] = []

    for item in citations:
        quote = " ".join(str(item.get("verbatim_quote") or "").split()).strip()
        author = " ".join(str(item.get("cited_author") or "").split()).strip()
        work = " ".join(str(item.get("cited_work") or "").split()).strip()
        year = str(item.get("cited_year") or "").strip() or None
        layer = str(item.get("source_layer") or "modern_historiography").strip()
        stance = str(item.get("stance") or "uses_as_source").strip()
        note = " ".join(str(item.get("appraisal_note") or "").split()).strip()
        trans_from = " ".join(str(item.get("transmission_from") or "").split()).strip() or None

        if not quote or not author or not work or not note:
            rejected.append({"cited_work": work, "reason": "campi obbligatori mancanti"})
            continue
        if layer not in SOURCE_LAYERS:
            rejected.append({"cited_work": work, "reason": f"source_layer non valido: {layer}"})
            continue
        if stance not in CITATION_STANCES:
            rejected.append({"cited_work": work, "reason": f"stance non valida: {stance}"})
            continue
        if not quote_matches_block_ocr_tolerant(quote, block_content):
            rejected.append({"cited_work": work, "reason": "verbatim_quote assente dal blocco sorgente"})
            continue

        resolved_pk = resolve_cited_book_pk(conn, author, work)
        exists = conn.execute(
            """
            SELECT citation_pk FROM bibliographic_citations
            WHERE source_block_pk = ? AND cited_author = ? AND cited_work = ?
            """,
            (source_block_pk, author, work),
        ).fetchone()
        if exists is not None:
            continue

        conn.execute(
            """
            INSERT INTO bibliographic_citations (
                source_block_pk, verbatim_quote, cited_author, cited_work, cited_year,
                source_layer, stance, appraisal_note, transmission_from, resolved_book_pk
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_block_pk, quote, author, work, year, layer, stance, note, trans_from, resolved_pk),
        )
        inserted += 1

    conn.commit()
    return {"source_block_pk": source_block_pk, "inserted": inserted, "rejected": rejected}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Selettore ed estrattore Grafo delle Fonti (ADR-0005).")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--book-pk", type=int, default=None, help="Filtra per singolo book_pk (es. 992 Geymonat)")
    parser.add_argument("--min-score", type=int, default=4)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--init-schema", action="store_true", help="Inizializza le tabelle additive ADR-0005")
    args = parser.parse_args(argv)

    if args.init_schema:
        conn = init_corpus_db(args.db)
    else:
        conn = connect_corpus_db(args.db, read_only=True)
    try:
        rows = select_biblio_rich_blocks(conn, book_pk=args.book_pk, min_score=args.min_score, limit=args.limit)
        print(json.dumps({"count": len(rows), "candidates": rows}, indent=2, ensure_ascii=False))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
