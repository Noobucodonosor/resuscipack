"""Sonda Viva di Sintagma & Processo alla Proposizione a €0 (ADR-0005, TASK-PROBE-01).

Costruisce gli indici derivati `units_fts` e `concept_edges` in `pack_corpus.db`
e fornisce due lenti deterministiche (`<150 ms`, zero costi API):
- Lente 1 (Sonda di Sintagma): pulizia parole-guscio e ricerca su `units_fts` + `passages_fts`.
- Lente 2 (Processo alla Proposizione): scomposizione di un'intera frase in assunzioni/concetti,
  confronto tra conferme e tesi rivali (`critiques`/`dispute`/`vs_dispute`) + concetti-ponte.
"""

from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db
from resuscipack.epistemic.decompressor import (
    _extract_query_terms,
    _parse_json_tuple,
    _safe_morph_variants,
    parse_historical_year,
)
from resuscipack.epistemic.schema_v21 import normalizza_testo

_CLEAN_TITLE_RE = re.compile(r"^\[[^\]]+\]\s*")
_LIBGEN_SUFFIX_RE = re.compile(r"\s*\b(?:libgen(?:\.lc)?|z-lib)\b.*$", re.IGNORECASE)


def _clean_title(raw: str) -> str:
    s = _CLEAN_TITLE_RE.sub("", str(raw or "").strip())
    s = _LIBGEN_SUFFIX_RE.sub("", s).strip(" -_")
    return s or str(raw or "")


def rebuild_phrase_indices(db_path: Path | str = DEFAULT_DB_PATH) -> Dict[str, int]:
    """Ricostruisce idempotentemente `units_fts` e `concept_edges` da `epistemic_units` (€0)."""
    conn = init_corpus_db(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM units_fts;")
            conn.execute(
                """
                INSERT INTO units_fts(rowid, stmt, verbatim_quote, concepts_json, vs_dispute)
                SELECT
                    unit_pk,
                    COALESCE(stmt, ''),
                    COALESCE(verbatim_quote, ''),
                    COALESCE(concepts_json, ''),
                    COALESCE(vs_dispute, '')
                FROM epistemic_units
                """
            )

            edge_counts: Counter[Tuple[str, str]] = Counter()
            sample_unit: Dict[Tuple[str, str], int] = {}
            rows = conn.execute(
                "SELECT unit_pk, concepts_json FROM epistemic_units WHERE concepts_json IS NOT NULL AND concepts_json != '[]'"
            ).fetchall()
            for r in rows:
                upk = int(r["unit_pk"])
                concepts = sorted(
                    {
                        normalizza_testo(c)
                        for c in _parse_json_tuple(r["concepts_json"])
                        if len(normalizza_testo(c)) >= 3
                    }
                )
                if len(concepts) < 2:
                    continue
                for a, b in itertools.combinations(concepts[:6], 2):
                    if a == b:
                        continue
                    pair = (a, b) if a < b else (b, a)
                    edge_counts[pair] += 1
                    if pair not in sample_unit:
                        sample_unit[pair] = upk

            conn.execute("DELETE FROM concept_edges;")
            conn.executemany(
                "INSERT INTO concept_edges (concept_a, concept_b, weight, sample_unit_pk) VALUES (?, ?, ?, ?)",
                [(a, b, w, sample_unit[(a, b)]) for (a, b), w in edge_counts.items() if w >= 1],
            )

        fts_cnt = int(conn.execute("SELECT COUNT(*) FROM units_fts").fetchone()[0])
        edges_cnt = int(conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0])
        return {"units_fts_rows": fts_cnt, "concept_edges_rows": edges_cnt}
    finally:
        conn.close()


def _build_or_fts_query(terms: Sequence[str], *, require_all_if_pair: bool = False) -> str:
    clauses: List[str] = []
    for tok in terms[:6]:
        variants = _safe_morph_variants(tok)
        if not variants:
            continue
        if len(variants) == 1:
            clauses.append(f'"{variants[0]}"')
        else:
            clauses.append("(" + " OR ".join(f'"{v}"' for v in variants) + ")")
    if not clauses:
        return ""
    if require_all_if_pair and len(clauses) == 2:
        return f"({clauses[0]} AND {clauses[1]})"
    return " OR ".join(clauses)


def _row_to_probe_hit(r: sqlite3.Row, *, terms: Sequence[str], context_terms: Sequence[str]) -> Dict[str, Any]:
    stmt = str(r["stmt"] or "")
    quote = str(r["verbatim_quote"] or "")
    concepts = list(_parse_json_tuple(r["concepts_json"]))
    actors = list(_parse_json_tuple(r["actors_json"]))
    vs_dispute = str(r["vs_dispute"] or "").strip() or None
    mode = str(r["mode"] or "")
    kind = str(r["kind"] or "")

    hay = normalizza_testo(f"{stmt} {quote} {' '.join(concepts)} {vs_dispute or ''}")
    term_hits = sum(1 for t in terms if any(v in hay for v in _safe_morph_variants(t)))
    ctx_hits = sum(1 for t in context_terms if t in hay)
    is_rival = bool(vs_dispute or mode == "critiques" or kind == "dispute")
    def_boost = 0.6 if (mode == "defines" or kind in ("def", "thm")) else 0.0
    score = round(
        term_hits * 2.0 + ctx_hits * 0.5 + def_boost + (0.6 if actors else 0.0) + (0.8 if is_rival else 0.0),
        3,
    )

    when_label = ""
    if r["year"] is not None:
        parsed_y = parse_historical_year(str(r["year"]))
        when_label = parsed_y[1] if parsed_y else str(r["year"])

    return {
        "unit_pk": int(r["unit_pk"]),
        "block_pk": int(r["block_pk"]),
        "book_pk": int(r["book_pk"]),
        "book_title": _clean_title(str(r["book_title"] or "")),
        "author": r["author"],
        "when": when_label,
        "surface_domain": r["surface_domain"],
        "kind": kind,
        "mode": mode,
        "is_rival": is_rival,
        "stmt": stmt,
        "verbatim_quote": quote,
        "actors": actors,
        "concepts": concepts,
        "vs_dispute": vs_dispute,
        "relevance": score,
    }


def _query_units_fts(
    conn: sqlite3.Connection,
    fts_expr: str,
    *,
    limit: int = 40,
) -> List[sqlite3.Row]:
    if not fts_expr:
        return []
    has_units_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='units_fts'"
    ).fetchone()
    if has_units_fts is None:
        return []
    try:
        return conn.execute(
            """
            SELECT
                eu.unit_pk,
                eu.block_pk,
                eu.kind,
                eu.mode,
                eu.stmt,
                eu.verbatim_quote,
                eu.actors_json,
                eu.vs_dispute,
                eu.concepts_json,
                bl.book_pk,
                bl.book_title,
                bk.author,
                bk.year,
                bk.surface_domain
            FROM units_fts
            JOIN epistemic_units eu ON eu.unit_pk = units_fts.rowid
            JOIN blocks bl ON bl.block_pk = eu.block_pk
            JOIN books bk ON bk.book_pk = bl.book_pk
            WHERE units_fts MATCH ?
              AND bl.is_active = 1
              AND bk.is_active = 1
            ORDER BY bm25(units_fts, 2.0, 1.5, 1.8, 1.2)
            LIMIT ?
            """,
            (fts_expr, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _find_bridging_concepts(conn: sqlite3.Connection, terms: Sequence[str], *, limit: int = 8) -> List[Dict[str, Any]]:
    has_edges = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='concept_edges'"
    ).fetchone()
    if has_edges is None or len(terms) < 2:
        return []

    neighbors_by_term: List[Tuple[str, Dict[str, int]]] = []
    for tok in terms[:4]:
        nmap: Dict[str, int] = {}
        like_pat = f"%{tok}%"
        rows = conn.execute(
            """
            SELECT concept_a, concept_b, weight
            FROM concept_edges
            WHERE concept_a LIKE ? OR concept_b LIKE ?
            ORDER BY weight DESC
            LIMIT 40
            """,
            (like_pat, like_pat),
        ).fetchall()
        for r in rows:
            ca = str(r["concept_a"])
            cb = str(r["concept_b"])
            w = int(r["weight"])
            other = cb if tok in ca else ca
            if tok not in other:
                nmap[other] = max(nmap.get(other, 0), w)
        if nmap:
            neighbors_by_term.append((tok, nmap))

    if len(neighbors_by_term) < 2:
        return []

    bridge_scores: Counter[str] = Counter()
    bridge_sources: Dict[str, set[str]] = {}
    for tok, nmap in neighbors_by_term:
        for concept, w in nmap.items():
            bridge_sources.setdefault(concept, set()).add(tok)
            bridge_scores[concept] += w

    bridges = [
        {
            "concept": concept,
            "connected_terms": sorted(bridge_sources[concept]),
            "strength": int(bridge_scores[concept]),
        }
        for concept, srcs in bridge_sources.items()
        if len(srcs) >= 2
    ]
    bridges.sort(key=lambda item: (-len(item["connected_terms"]), -item["strength"], item["concept"]))
    return bridges[:limit]


def probe_selection(
    conn: sqlite3.Connection,
    selection_text: str,
    *,
    chapter_context: str = "",
    limit: int = 12,
) -> Dict[str, Any]:
    """Interroga il corpus a partire da un sintagma o da un'intera frase selezionata nel Lettore."""
    raw = " ".join(str(selection_text or "").split()).strip()
    if not raw:
        return {"mode": "empty", "query": "", "terms": [], "confirmations": [], "rivals": [], "bridges": []}

    conn.row_factory = sqlite3.Row
    terms = list(_extract_query_terms(raw))
    ctx_terms = [t for t in _extract_query_terms(chapter_context) if t not in terms][:6]
    words = raw.split()
    is_proposition = len(words) >= 7 or len(raw) > 55

    if not terms:
        return {"mode": "empty", "query": raw, "terms": [], "confirmations": [], "rivals": [], "bridges": []}

    # Prova prima con matching stretto su <=2 termini, poi OR mirato
    rows = []
    if not is_proposition and len(terms) <= 2:
        strict_q = _build_or_fts_query(terms, require_all_if_pair=True)
        rows = _query_units_fts(conn, strict_q, limit=max(40, limit * 3))
    if len(rows) < 6:
        broad_q = _build_or_fts_query(terms, require_all_if_pair=False)
        extra = _query_units_fts(conn, broad_q, limit=max(60, limit * 4))
        seen_upk = {int(r["unit_pk"]) for r in rows}
        for er in extra:
            if int(er["unit_pk"]) not in seen_upk:
                rows.append(er)
                seen_upk.add(int(er["unit_pk"]))

    scored: List[Dict[str, Any]] = []
    for r in rows:
        hit = _row_to_probe_hit(r, terms=terms, context_terms=ctx_terms)
        if hit["relevance"] > 0:
            scored.append(hit)

    scored.sort(key=lambda h: (-h["relevance"], h["book_pk"], h["unit_pk"]))

    # Diversità per libro (al massimo 2 unità per libro nel top set)
    confirmations: List[Dict[str, Any]] = []
    rivals: List[Dict[str, Any]] = []
    book_counts_conf: Counter[int] = Counter()
    book_counts_riv: Counter[int] = Counter()

    for hit in scored:
        bpk = hit["book_pk"]
        if hit["is_rival"]:
            if book_counts_riv[bpk] < 2 and len(rivals) < limit:
                rivals.append(hit)
                book_counts_riv[bpk] += 1
        else:
            if book_counts_conf[bpk] < 2 and len(confirmations) < limit:
                confirmations.append(hit)
                book_counts_conf[bpk] += 1

    bridges = _find_bridging_concepts(conn, terms, limit=8) if is_proposition or len(terms) >= 2 else []

    return {
        "mode": "proposition_trial" if is_proposition else "phrase_probe",
        "query": raw,
        "terms": terms,
        "confirmations": confirmations,
        "rivals": rivals,
        "bridges": bridges,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Costruttore indici e sonda sintagmi ADR-0005.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--rebuild", action="store_true", help="Ricostruisce units_fts e concept_edges")
    parser.add_argument("--probe", type=str, default=None, help="Testa una selezione dal vivo")
    args = parser.parse_args(argv)

    if args.rebuild:
        stats = rebuild_phrase_indices(args.db)
        print(json.dumps(stats, indent=2, ensure_ascii=False))

    if args.probe:
        conn = connect_corpus_db(args.db, read_only=True)
        try:
            res = probe_selection(conn, args.probe)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        finally:
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
