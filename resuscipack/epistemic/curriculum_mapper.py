"""Mappatura Bidirezionale dell'Ontologia Ministeriale v6 sulla Contezza Simultanea (ADR-0004, TASK-SPEC-04).

Mantiene rigorosamente distinti per il Principio R4 (`SPEC.md`):
- `institutional_declared`: gli obiettivi ufficiali consolidati in
  `data/curriculum/ministerial_ontology/ontology_v6_consolidated.json` (mai sovrascritti).
- `corpus_learnable`: ciò che è effettivamente dimostrato e apprendibile nei blocchi attivi di
  `pack_corpus.db` (`objective_corpus_map` + `objective_block_evidence` +
  `data/curriculum/ministerial_ontology/corpus_coverage_report.json`), evidenziando lacune reali
  e scoperte interdisciplinari da "Libro Sbagliato" prima della stesura del Volume I (`#8`).

Costi API esterni: 0 EUR.
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..corpus.schema import DEFAULT_DB_PATH, SCHEMA_DDL, connect_corpus_db
from ..curriculum.dag import DEFAULT_DAG_PATH, load_unified_dag
from ..curriculum.ministerial_ontology import (
    DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    DEFAULT_ONTOLOGY_DIR,
    LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE,
    load_consolidated_ontology,
)
from .schema_v21 import normalizza_testo
from .spectrum import is_residual_paratext_block, label_for_discipline

DEFAULT_COVERAGE_REPORT_PATH = DEFAULT_ONTOLOGY_DIR / "corpus_coverage_report.json"

ONTOLOGY_TO_CORPUS_DISCIPLINES: Dict[str, frozenset[str]] = {
    "matematica": frozenset({"matematica", "logica"}),
    "fisica": frozenset({"fisica", "astronomia_cosmologia"}),
    "informatica_tecnologia": frozenset(
        {
            "informatica",
            "ingegneria_meccanica_elettronica",
            "telecomunicazioni_segnali",
            "crittografia_sicurezza",
            "arti_pratiche_artigianato",
        }
    ),
    "storia_economia": frozenset({"storia_politica_militare", "economia_commercio_assicurazioni"}),
    "geografia_territorio": frozenset({"geografia_cartografia_territorio", "nautica_navigazione_meteo"}),
    "filosofia_scienze_umane": frozenset(
        {"filosofia_epistemologia", "psicologia_pedagogia_societa", "logica"}
    ),
    "scienze_chimica_biologia": frozenset(
        {
            "biologia_fisiologia_medicina",
            "chimica_materiali",
            "agronomia_scienze_naturali_cibo",
            "astronomia_cosmologia",
        }
    ),
    "letteratura_lingue": frozenset({"letteratura_retorica_filologia"}),
    "arte_architettura": frozenset({"arte_architettura_disegno", "arti_pratiche_artigianato"}),
    "musica_acustica": frozenset({"musica_acustica"}),
    "diritto_societa": frozenset(
        {"diritto_istituzioni", "economia_commercio_assicurazioni", "psicologia_pedagogia_societa"}
    ),
    "discipline_generali_e_indirizzo": frozenset(),
}

_K13_MATH_SOURCE_FILES = frozenset(
    {
        "primaria_matematica.json",
        "media_matematica.json",
        "liceo_scientifico_matematica.json",
    }
)

_MINISTERIAL_STOPWORDS = frozenset(
    {
        # Funzionali italiane
        "il", "lo", "la", "le", "gli", "un", "uno", "una", "del", "dello", "della",
        "dei", "degli", "delle", "al", "allo", "alla", "ai", "agli", "alle", "dal",
        "dallo", "dalla", "dai", "dagli", "dalle", "nel", "nello", "nella", "nei",
        "negli", "nelle", "sul", "sullo", "sulla", "sui", "sugli", "sulle", "con",
        "per", "tra", "fra", "che", "chi", "cui", "come", "dove", "quando", "anche",
        "solo", "piu", "meno", "ogni", "tutti", "tutte", "tutto", "tutta", "sono",
        "essere", "avere", "fare", "puo", "loro", "suo", "sua", "suoi", "sue",
        "questo", "questa", "questi", "queste", "quello", "quella", "quelli", "quelle",
        "quale", "quali", "oltre", "senza", "circa", "entro", "verso", "sotto", "sopra",
        # Lessico burocratico / scolastico ministeriale privo di potere discriminante
        "conoscere", "comprendere", "utilizzare", "usare", "saper", "sapere", "grado",
        "individuare", "analizzare", "sviluppare", "acquisire", "applicare", "riconoscere",
        "descrivere", "rappresentare", "risolvere", "eseguire", "calcolare", "interpretare",
        "valutare", "elaborare", "costruire", "confrontare", "elementi", "elemento",
        "concetti", "concetto", "principali", "principale", "fondamentali", "fondamentale",
        "semplici", "semplice", "problemi", "problema", "contesto", "contesti", "attivita",
        "diversi", "diverse", "diverso", "diversa", "attraverso", "mediante", "relazione",
        "relazioni", "sistema", "sistemi", "processo", "processi", "fenomeno", "fenomeni",
        "strumenti", "strumento", "metodi", "metodo", "tecniche", "tecnica", "base",
        "generali", "generale", "specifici", "specifico", "specifiche", "uso", "ruolo",
        "significato", "cogliere", "identificazione", "identificare", "aspetti", "aspetto",
        "modo", "varie", "vari", "propri", "proprie", "proprio", "propria", "vario",
        "capire", "mostrare", "indicare", "spiegare", "stabilire", "trovare", "dare",
        "ottenere", "passare", "muoversi", "leggere", "scrivere", "produrre", "comunicare",
        "partire", "situazioni", "situazione", "realta", "esperienza", "ambito", "ambiti",
        "studio", "studi", "forma", "forme", "caso", "casi", "dato", "valore", "criteri",
        "definizione", "definizioni", "proprieta", "caratteristiche", "nozioni", "principi",
        "conoscenze", "competenze", "abilita", "capacita", "livello", "livelli", "maniera",
        "particolare", "esempi", "esempio", "alcuno", "alcuni", "alcune", "possibili",
        "conoscenza", "funzionale", "funzionalita", "completamento", "realizzazione",
        "affrontare", "utili", "comprensione", "esecuzione", "produzione", "interpretazione",
        "rapporto", "rapporti", "strutture", "struttura", "ampliamento", "introduzione",
        "gradualita", "familiarita", "consolidamento", "approfondimento", "sviluppo",
        "verifica", "analisi", "sintesi", "origine", "origini", "storica", "storico",
        "generali", "fondamento", "fondamenti", "pratica", "pratico", "teorica", "teorico",
        "relativo", "relativa", "relativi", "relative", "corretto", "corretta", "corretta",
        "adeguato", "adeguata", "specifica", "specifico", "principale", "secondario",
    }
)

_SHORT_DOMAIN_TOKENS = frozenset(
    {
        "mcd", "mcm", "ode", "sql", "cpu", "ram", "rom", "gpu", "dna", "rna",
        "rsa", "aes", "sha", "tls", "ssl", "tcp", "udp", "http", "html", "css",
        "xml", "json", "api", "bit", "byte", "area", "zero", "rete", "reti",
        "dati", "moto", "onde", "onda", "luce", "peso", "lati", "lato", "base",
        "arco", "cono", "cubo", "asse", "assi", "seno", "pila", "pile", "coda",
        "eta", "oro", "gas", "ph", "ohm", "volt", "watt", "jazz", "rock",
    }
)


def _ascii_lower(text: str) -> str:
    n = unicodedata.normalize("NFKD", normalizza_testo(text))
    return n.encode("ascii", "ignore").decode("ascii")


def extract_objective_query_terms(statement: str, nucleus: str = "") -> Tuple[str, ...]:
    """Estrae fino a 8 termini ad alto segnale da un obiettivo ministeriale eliminando il burocratese."""
    raw_stmt = str(statement or "")
    expanded_parts = [raw_stmt]
    if "√2" in raw_stmt or "√" in raw_stmt:
        expanded_parts.append("radice quadrata irrazionale")
    if "|x|" in raw_stmt:
        expanded_parts.append("valore assoluto modulo")
    if "π" in raw_stmt:
        expanded_parts.append("pi greco circonferenza")
    if "y = ax" in raw_stmt.lower() or "a/x" in raw_stmt.lower():
        expanded_parts.append("proporzionalita diretta inversa")
    if "f(x)" in raw_stmt.lower():
        expanded_parts.append("funzione retta grafico")

    stmt_clean = _ascii_lower(" ".join(expanded_parts))
    nuc_clean = _ascii_lower(nucleus)

    def _collect(text: str) -> List[str]:
        found: List[str] = []
        for tok in re.findall(r"[a-z0-9]{2,}", text):
            if tok.isdigit():
                continue
            if tok in _MINISTERIAL_STOPWORDS:
                continue
            if len(tok) >= 4 or tok in _SHORT_DOMAIN_TOKENS:
                found.append(tok)
        return found

    stmt_tokens = _collect(stmt_clean)
    nuc_tokens = _collect(nuc_clean)

    ranked: List[str] = []
    seen: set[str] = set()
    # Priorità ai termini dello statement (ordinati per specificità/lunghezza, mantenendo ancoraggio)
    for tok in sorted(stmt_tokens, key=lambda t: (-min(len(t), 12), stmt_tokens.index(t))):
        if tok not in seen:
            seen.add(tok)
            ranked.append(tok)
    if len(ranked) < 5:
        for tok in sorted(nuc_tokens, key=lambda t: (-min(len(t), 12), nuc_tokens.index(t))):
            if tok not in seen:
                seen.add(tok)
                ranked.append(tok)
            if len(ranked) >= 6:
                break

    # Fallback se lo statement era composto solo da parole molto generiche
    if not ranked:
        for tok in re.findall(r"[a-z]{4,}", f"{stmt_clean} {nuc_clean}"):
            if tok not in seen:
                seen.add(tok)
                ranked.append(tok)
            if len(ranked) >= 4:
                break

    return tuple(ranked[:8])


def _build_fts_or_query(terms: Sequence[str], *, use_prefix: bool = False) -> str:
    parts: List[str] = []
    for t in terms[:8]:
        clean = re.sub(r"[^a-z0-9]+", "", t.lower())
        if not clean:
            continue
        if use_prefix and len(clean) >= 7:
            stem = clean[: max(7, len(clean) - 2)]
            parts.append(f'("{clean}" OR "{stem}"*)')
        else:
            parts.append(f'"{clean}"')
    return " OR ".join(parts)


def _term_in_hay(term: str, hay_norm: str, hay_words: set[str]) -> bool:
    if term in hay_words:
        return True
    if len(term) >= 6:
        stem = term[: max(5, len(term) - 2)]
        for w in hay_words:
            if len(w) >= 6 and w.startswith(stem):
                return True
    return False


def _ensure_mapper_schema(conn: sqlite3.Connection) -> None:
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('objective_corpus_map', 'objective_block_evidence')"
        ).fetchall()
    }
    if len(existing) < 2:
        conn.executescript(SCHEMA_DDL)


def _chunked(seq: Sequence[int], size: int = 500) -> Iterable[Sequence[int]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _is_k13_math_objective(obj: Dict[str, Any]) -> bool:
    src = str(obj.get("source_file", ""))
    return (
        src.split("#", 1)[0] in _K13_MATH_SOURCE_FILES
        or src == LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE
    )


def map_ontology_to_corpus(
    db_or_conn: Path | str | sqlite3.Connection = DEFAULT_DB_PATH,
    *,
    ontology_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    max_fts_per_objective: int = 35,
    max_evidence_per_objective: int = 8,
) -> Dict[str, Any]:
    """Mappa i `2.828` obiettivi di `ontology_v6_consolidated.json` sui blocchi reali del corpus."""
    owns_conn = not isinstance(db_or_conn, sqlite3.Connection)
    conn = connect_corpus_db(db_or_conn, read_only=False) if owns_conn else db_or_conn
    conn.row_factory = sqlite3.Row

    try:
        _ensure_mapper_schema(conn)
        now_iso = datetime.now(timezone.utc).isoformat()
        ont_payload = load_consolidated_ontology(ontology_path)
        objectives: List[Dict[str, Any]] = list(ont_payload.get("objectives", []))

        # Precaricamento metadati libri + spettro primario
        has_spec_meta = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'book_spectrum_meta'"
            ).fetchone()
            is not None
        )
        book_info: Dict[int, Dict[str, Any]] = {}
        if has_spec_meta:
            bk_rows = conn.execute(
                """
                SELECT bk.book_pk, bk.title, bk.surface_domain,
                       COALESCE(bsm.quality_tier, 'canonical_book') AS quality_tier,
                       bsm.primary_discipline
                FROM books bk
                LEFT JOIN book_spectrum_meta bsm ON bsm.book_pk = bk.book_pk
                WHERE bk.is_active = 1
                """
            ).fetchall()
        else:
            bk_rows = conn.execute(
                """
                SELECT book_pk, title, surface_domain,
                       'canonical_book' AS quality_tier,
                       NULL AS primary_discipline
                FROM books
                WHERE is_active = 1
                """
            ).fetchall()
        for br in bk_rows:
            book_info[int(br["book_pk"])] = {
                "title": str(br["title"]),
                "surface_domain": str(br["surface_domain"] or ""),
                "quality_tier": str(br["quality_tier"] or "canonical_book"),
                "primary_discipline": br["primary_discipline"],
            }

        # Precaricamento ponti `curiosity_bridges` validati indicizzati per `node_id` e prefisso
        bridges_by_node: Dict[str, List[int]] = defaultdict(list)
        bridges_by_prefix: Dict[str, List[int]] = defaultdict(list)
        for cb in conn.execute(
            "SELECT bridge_pk, node_id FROM curiosity_bridges WHERE status = 'validated'"
        ).fetchall():
            bpk = int(cb["bridge_pk"])
            nid = str(cb["node_id"])
            bridges_by_node[nid].append(bpk)
            if "." in nid:
                bridges_by_prefix[nid.rsplit(".", 1)[0]].append(bpk)

        # Fase A: estrazione keyword + raccolta candidati FTS5 per tutti gli obiettivi
        obj_terms_list: List[Tuple[str, ...]] = []
        obj_candidates: List[List[int]] = []
        all_candidate_pks: set[int] = set()

        for obj in objectives:
            q_terms = extract_objective_query_terms(
                str(obj.get("statement", "")), str(obj.get("nucleus", ""))
            )
            obj_terms_list.append(q_terms)
            fts_q = _build_fts_or_query(q_terms, use_prefix=False)
            cands: List[int] = []
            if fts_q:
                try:
                    rows = conn.execute(
                        """
                        SELECT rowid
                        FROM passages_fts
                        WHERE passages_fts MATCH ?
                        ORDER BY bm25(passages_fts)
                        LIMIT ?
                        """,
                        (fts_q, int(max_fts_per_objective)),
                    ).fetchall()
                    cands = [int(r[0]) for r in rows]
                except sqlite3.OperationalError:
                    cands = []
            # Fallback con prefissi FTS5 solo quando l'OR esatto trova pochissimi candidati
            if len(cands) < 8 and q_terms:
                fts_pref = _build_fts_or_query(q_terms, use_prefix=True)
                if fts_pref and fts_pref != fts_q:
                    try:
                        extra = conn.execute(
                            """
                            SELECT rowid
                            FROM passages_fts
                            WHERE passages_fts MATCH ?
                            ORDER BY bm25(passages_fts)
                            LIMIT ?
                            """,
                            (fts_pref, int(max_fts_per_objective)),
                        ).fetchall()
                        seen_c = set(cands)
                        for er in extra:
                            pk = int(er[0])
                            if pk not in seen_c:
                                seen_c.add(pk)
                                cands.append(pk)
                    except sqlite3.OperationalError:
                        pass
            obj_candidates.append(cands)
            all_candidate_pks.update(cands)

        # Fase B: caricamento in blocco dei soli `block_pk` candidati (a chunk da 500)
        block_cache: Dict[int, Dict[str, Any]] = {}
        sorted_cands = sorted(all_candidate_pks)
        for chunk in _chunked(sorted_cands, size=500):
            ph = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT
                    b.block_pk,
                    b.block_uid,
                    b.book_pk,
                    b.block_role,
                    b.page_start,
                    b.printed_page,
                    b.section_title,
                    b.content,
                    b.norm_content,
                    m.macro_disciplines_json,
                    m.emergent_topics_json
                FROM blocks b
                LEFT JOIN block_metadata_v22 m ON m.block_pk = b.block_pk
                WHERE b.block_pk IN ({ph})
                  AND b.is_active = 1
                  AND b.block_role != 'paratext'
                """,
                tuple(chunk),
            ).fetchall()

            valid_chunk_pks: List[int] = []
            for r in rows:
                bpk = int(r["block_pk"])
                book_pk = int(r["book_pk"])
                bmeta = book_info.get(book_pk)
                if bmeta is None:
                    continue
                if bmeta["quality_tier"] in {"non_book_noise", "reference_manual"}:
                    continue
                if is_residual_paratext_block(str(r["section_title"] or ""), str(r["content"] or "")):
                    continue

                macro_discs = set(json.loads(r["macro_disciplines_json"] or "[]"))
                topics = json.loads(r["emergent_topics_json"] or "[]")
                norm_ascii = _ascii_lower(r["norm_content"] or "")
                block_cache[bpk] = {
                    "block_pk": bpk,
                    "block_uid": str(r["block_uid"]),
                    "book_pk": book_pk,
                    "page_start": r["page_start"],
                    "printed_page": r["printed_page"],
                    "macro_disciplines": macro_discs,
                    "topics_ascii": _ascii_lower(" ".join(str(t) for t in topics)),
                    "norm_ascii": norm_ascii,
                    "norm_words": set(re.findall(r"[a-z0-9]{2,}", norm_ascii)),
                    "has_unit": False,
                    "stmt_ascii": "",
                    "concepts_ascii": "",
                    "best_stmt": "",
                    "verbatim_quote": "",
                }
                valid_chunk_pks.append(bpk)

            if valid_chunk_pks:
                ph_u = ",".join("?" for _ in valid_chunk_pks)
                u_rows = conn.execute(
                    f"""
                    SELECT block_pk, stmt, verbatim_quote, concepts_json
                    FROM epistemic_units
                    WHERE block_pk IN ({ph_u})
                    ORDER BY block_pk ASC, unit_pk ASC
                    """,
                    tuple(valid_chunk_pks),
                ).fetchall()
                for ur in u_rows:
                    binfo = block_cache.get(int(ur["block_pk"]))
                    if binfo is None:
                        continue
                    binfo["has_unit"] = True
                    s_val = " ".join(str(ur["stmt"] or "").split()).strip()
                    q_val = " ".join(str(ur["verbatim_quote"] or "").split()).strip()
                    if s_val:
                        binfo["stmt_ascii"] = f"{binfo['stmt_ascii']} {_ascii_lower(s_val)}".strip()
                        if not binfo["best_stmt"]:
                            binfo["best_stmt"] = s_val
                    if q_val and not binfo["verbatim_quote"]:
                        binfo["verbatim_quote"] = q_val
                    c_list = json.loads(ur["concepts_json"] or "[]")
                    if c_list:
                        binfo["concepts_ascii"] = (
                            f"{binfo['concepts_ascii']} {_ascii_lower(' '.join(str(c) for c in c_list))}"
                        ).strip()

                for bpk in valid_chunk_pks:
                    binfo = block_cache[bpk]
                    epistemic_str = f"{binfo['stmt_ascii']} {binfo['concepts_ascii']} {binfo['topics_ascii']}".strip()
                    binfo["epistemic_ascii"] = epistemic_str
                    binfo["epistemic_words"] = set(re.findall(r"[a-z0-9]{2,}", epistemic_str))
                    binfo["all_ascii"] = f"{epistemic_str} {binfo['norm_ascii']}".strip()
                    binfo["all_words"] = binfo["epistemic_words"] | binfo["norm_words"]

        # Fase C: scoring deterministico e costruzione righe `objective_corpus_map` & `objective_block_evidence`
        map_inserts: List[Tuple[Any, ...]] = []
        ev_inserts: List[Tuple[Any, ...]] = []

        status_counts: Counter[str] = Counter()
        cycle_status: Dict[str, Counter[str]] = defaultdict(Counter)
        disc_status: Dict[str, Counter[str]] = defaultdict(Counter)
        k13_status: Counter[str] = Counter()
        objectives_with_wb = 0

        for idx, obj in enumerate(objectives):
            uid = str(obj["objective_uid"])
            cycle = str(obj["cycle"])
            school = str(obj["school"])
            subject = str(obj["subject"])
            grade = str(obj["grade"])
            nucleus = str(obj["nucleus"])
            target_disc = str(obj["target_macro_discipline"])
            mapped_nodes = [str(n) for n in obj.get("mapped_dag_node_ids", [])]
            q_terms = obj_terms_list[idx]
            expected_discs = ONTOLOGY_TO_CORPUS_DISCIPLINES.get(target_disc, frozenset())

            min_needed = 1 if len(q_terms) <= 2 else 2

            scored_hits: List[Tuple[float, int, int, int, bool, List[str], Dict[str, Any], Dict[str, Any]]] = []
            for bpk in obj_candidates[idx]:
                binfo = block_cache.get(bpk)
                if binfo is None:
                    continue
                bmeta = book_info[binfo["book_pk"]]

                all_words = binfo["all_words"]
                all_ascii = binfo["all_ascii"]
                epi_words = binfo.get("epistemic_words", set())
                epi_ascii = binfo.get("epistemic_ascii", "")

                matched_terms: List[str] = []
                epi_hits = 0
                for term in q_terms:
                    if _term_in_hay(term, all_ascii, all_words):
                        matched_terms.append(term)
                        if _term_in_hay(term, epi_ascii, epi_words):
                            epi_hits += 1

                if len(matched_terms) < min_needed:
                    continue

                match_ratio = len(matched_terms) / max(1, len(q_terms))
                disc_overlap = bool(expected_discs & binfo["macro_disciplines"])
                has_v22_discs = bool(binfo["macro_disciplines"])

                # Guard rail anti-omonimia: se la disciplina del blocco (v2.2) e' nota ma NON
                # interseca la disciplina attesa dall'obiettivo, accetta il blocco solo se il match
                # epistemico (`stmt`/`concepts`/`topics`) e' forte (evita 'motori elettrici' <-> 'scienze motorie').
                if expected_discs and has_v22_discs and not disc_overlap:
                    strong_min = min(len(q_terms), max(3, min_needed + 1))
                    if not (len(matched_terms) >= strong_min and epi_hits >= 2 and match_ratio >= 0.55):
                        continue
                if not binfo["has_unit"] and not (match_ratio >= 0.6 and (disc_overlap or not expected_discs)):
                    continue

                prim_disc = bmeta["primary_discipline"]
                is_wb = bool(expected_discs) and (
                    (prim_disc is not None and prim_disc not in expected_discs)
                    or (prim_disc is None and has_v22_discs and not disc_overlap)
                )

                raw_score = (
                    (2.0 * epi_hits + (len(matched_terms) - epi_hits)) / max(1.0, 2.0 * len(q_terms))
                    + (0.15 if disc_overlap else 0.0)
                    + (0.10 if binfo["has_unit"] else 0.0)
                )
                norm_score = round(min(1.0, raw_score), 4)
                if norm_score < 0.45:
                    continue
                scored_hits.append(
                    (
                        norm_score,
                        epi_hits,
                        len(matched_terms),
                        bpk,
                        is_wb,
                        matched_terms,
                        binfo,
                        bmeta,
                    )
                )

            scored_hits.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))

            # Ponti `curiosity_bridges` associati ai nodi DAG dell'obiettivo
            linked_bridge_pks_set: set[int] = set()
            for nid in mapped_nodes:
                linked_bridge_pks_set.update(bridges_by_node.get(nid, []))
                if "." in nid:
                    linked_bridge_pks_set.update(bridges_by_prefix.get(nid.rsplit(".", 1)[0], []))
            linked_bridge_pks = sorted(linked_bridge_pks_set)

            matched_blocks_count = len(scored_hits)
            distinct_books_count = len({h[6]["book_pk"] for h in scored_hits})
            wrong_book_count = sum(1 for h in scored_hits if h[4])
            linked_bridge_count = len(linked_bridge_pks)

            if wrong_book_count > 0:
                objectives_with_wb += 1

            if (matched_blocks_count >= 3 and distinct_books_count >= 2) or (
                matched_blocks_count >= 2 and linked_bridge_count >= 1
            ):
                cov_status = "covered"
            elif matched_blocks_count >= 1 or linked_bridge_count >= 1:
                cov_status = "partial"
            else:
                cov_status = "gap"

            status_counts[cov_status] += 1
            cycle_status[cycle][cov_status] += 1
            disc_status[target_disc][cov_status] += 1
            if _is_k13_math_objective(obj):
                k13_status[cov_status] += 1

            # Seleziona le migliori evidenze garantendo almeno 1 `is_wrong_book` se presente
            top_ev = list(scored_hits[:max_evidence_per_objective])
            if wrong_book_count > 0 and not any(h[4] for h in top_ev):
                first_wb = next(h for h in scored_hits if h[4])
                if top_ev:
                    top_ev[-1] = first_wb
                else:
                    top_ev.append(first_wb)

            evidence_json_list: List[Dict[str, Any]] = []
            for score_v, _, _, bpk, is_wb, m_terms, binfo, bmeta in top_ev:
                evidence_json_list.append(
                    {
                        "block_pk": bpk,
                        "block_uid": binfo["block_uid"],
                        "book_pk": binfo["book_pk"],
                        "book_title": bmeta["title"],
                        "page_start": binfo["page_start"],
                        "printed_page": binfo["printed_page"],
                        "primary_discipline": bmeta["primary_discipline"],
                        "match_score": score_v,
                        "is_wrong_book": is_wb,
                        "matched_terms": m_terms,
                        "best_stmt": binfo["best_stmt"],
                        "verbatim_quote": binfo["verbatim_quote"],
                    }
                )
                ev_inserts.append(
                    (
                        uid,
                        bpk,
                        binfo["book_pk"],
                        score_v,
                        1 if is_wb else 0,
                        json.dumps(m_terms, ensure_ascii=False),
                    )
                )

            map_inserts.append(
                (
                    uid,
                    cycle,
                    school,
                    subject,
                    grade,
                    nucleus,
                    target_disc,
                    "corpus_learnable",
                    cov_status,
                    matched_blocks_count,
                    distinct_books_count,
                    wrong_book_count,
                    linked_bridge_count,
                    json.dumps(mapped_nodes, ensure_ascii=False),
                    json.dumps(evidence_json_list, ensure_ascii=False),
                    json.dumps(linked_bridge_pks, ensure_ascii=False),
                    json.dumps(list(q_terms), ensure_ascii=False),
                    now_iso,
                )
            )

        conn.execute("DELETE FROM objective_block_evidence")
        conn.execute("DELETE FROM objective_corpus_map")
        conn.executemany(
            """
            INSERT INTO objective_corpus_map (
                objective_uid, cycle, school, subject, grade, nucleus,
                target_macro_discipline, epistemic_layer, coverage_status,
                matched_blocks_count, distinct_books_count,
                wrong_book_evidence_count, linked_bridge_count,
                mapped_dag_node_ids_json, evidence_blocks_json,
                linked_bridge_pks_json, matched_terms_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            map_inserts,
        )
        conn.executemany(
            """
            INSERT INTO objective_block_evidence (
                objective_uid, block_pk, book_pk, match_score, is_wrong_book, matched_terms_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ev_inserts,
        )
        conn.commit()

        return {
            "epistemic_layer": "corpus_learnable",
            "total_objectives": len(objectives),
            "by_status": dict(sorted(status_counts.items())),
            "by_cycle": {k: dict(sorted(v.items())) for k, v in sorted(cycle_status.items())},
            "by_discipline": {k: dict(sorted(v.items())) for k, v in sorted(disc_status.items())},
            "objectives_with_wrong_book_evidence": objectives_with_wb,
            "evidence_links_written": len(ev_inserts),
            "k13_math_summary": dict(sorted(k13_status.items())),
        }
    finally:
        if owns_conn:
            conn.close()


def get_objective_corpus_mapping(
    conn: sqlite3.Connection,
    objective_uid: str,
    *,
    ontology_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
) -> Optional[Dict[str, Any]]:
    """Restituisce la vista R4 separata (`institutional_declared` vs `corpus_learnable`) di un obiettivo."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM objective_corpus_map WHERE objective_uid = ?",
        (str(objective_uid),),
    ).fetchone()
    if row is None:
        return None

    declared_obj: Optional[Dict[str, Any]] = None
    p = Path(ontology_path)
    if p.exists():
        ont = load_consolidated_ontology(p)
        for o in ont.get("objectives", []):
            if str(o.get("objective_uid")) == str(objective_uid):
                declared_obj = o
                break

    return {
        "objective_uid": str(row["objective_uid"]),
        "institutional_declared": {
            "epistemic_layer": "institutional_declared",
            "cycle": str(row["cycle"]),
            "school": str(row["school"]),
            "subject": str(row["subject"]),
            "grade": str(row["grade"]),
            "nucleus": str(row["nucleus"]),
            "target_macro_discipline": str(row["target_macro_discipline"]),
            "statement": declared_obj.get("statement") if declared_obj else None,
            "source_file": declared_obj.get("source_file") if declared_obj else None,
            "mapped_dag_node_ids": json.loads(row["mapped_dag_node_ids_json"] or "[]"),
        },
        "corpus_learnable": {
            "epistemic_layer": str(row["epistemic_layer"]),
            "coverage_status": str(row["coverage_status"]),
            "matched_blocks_count": int(row["matched_blocks_count"]),
            "distinct_books_count": int(row["distinct_books_count"]),
            "wrong_book_evidence_count": int(row["wrong_book_evidence_count"]),
            "linked_bridge_count": int(row["linked_bridge_count"]),
            "matched_terms": json.loads(row["matched_terms_json"] or "[]"),
            "linked_bridge_pks": json.loads(row["linked_bridge_pks_json"] or "[]"),
            "evidence_blocks": json.loads(row["evidence_blocks_json"] or "[]"),
            "updated_at": str(row["updated_at"]),
        },
    }


def _enrich_reverse_rows(
    rows: Sequence[sqlite3.Row],
    stmt_by_uid: Dict[str, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        uid = str(r["objective_uid"])
        out.append(
            {
                "objective_uid": uid,
                "cycle": str(r["cycle"]),
                "school": str(r["school"]),
                "subject": str(r["subject"]),
                "grade": str(r["grade"]),
                "nucleus": str(r["nucleus"]),
                "target_macro_discipline": str(r["target_macro_discipline"]),
                "statement": stmt_by_uid.get(uid, ""),
                "coverage_status": str(r["coverage_status"]),
                "block_pk": int(r["block_pk"]),
                "book_pk": int(r["book_pk"]),
                "page_start": r["page_start"],
                "printed_page": r["printed_page"],
                "match_score": float(r["match_score"]),
                "is_wrong_book": bool(r["is_wrong_book"]),
                "matched_terms": json.loads(r["matched_terms_json"] or "[]"),
                "mapped_dag_node_ids": json.loads(r["mapped_dag_node_ids_json"] or "[]"),
            }
        )
    return out


def find_objectives_for_book(
    conn: sqlite3.Connection,
    book_pk: int,
    *,
    only_wrong_book: bool = False,
    ontology_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
) -> List[Dict[str, Any]]:
    """Query inversa: quali obiettivi ministeriali si possono imparare da questo libro."""
    conn.row_factory = sqlite3.Row
    wb_clause = "AND e.is_wrong_book = 1" if only_wrong_book else ""
    rows = conn.execute(
        f"""
        SELECT
            e.objective_uid, e.block_pk, e.book_pk, e.match_score,
            e.is_wrong_book, e.matched_terms_json,
            m.cycle, m.school, m.subject, m.grade, m.nucleus,
            m.target_macro_discipline, m.coverage_status, m.mapped_dag_node_ids_json,
            b.page_start, b.printed_page
        FROM objective_block_evidence e
        JOIN objective_corpus_map m ON m.objective_uid = e.objective_uid
        JOIN blocks b ON b.block_pk = e.block_pk
        WHERE e.book_pk = ?
          {wb_clause}
        ORDER BY e.is_wrong_book DESC, e.match_score DESC, b.page_start ASC, e.objective_uid ASC
        """,
        (int(book_pk),),
    ).fetchall()

    stmt_by_uid: Dict[str, str] = {}
    p = Path(ontology_path)
    if rows and p.exists():
        ont = load_consolidated_ontology(p)
        stmt_by_uid = {str(o["objective_uid"]): str(o.get("statement", "")) for o in ont.get("objectives", [])}
    return _enrich_reverse_rows(rows, stmt_by_uid)


def find_objectives_for_block(
    conn: sqlite3.Connection,
    block_pk: int,
    *,
    ontology_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
) -> List[Dict[str, Any]]:
    """Query inversa: quali obiettivi ministeriali tocca un singolo blocco del corpus."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            e.objective_uid, e.block_pk, e.book_pk, e.match_score,
            e.is_wrong_book, e.matched_terms_json,
            m.cycle, m.school, m.subject, m.grade, m.nucleus,
            m.target_macro_discipline, m.coverage_status, m.mapped_dag_node_ids_json,
            b.page_start, b.printed_page
        FROM objective_block_evidence e
        JOIN objective_corpus_map m ON m.objective_uid = e.objective_uid
        JOIN blocks b ON b.block_pk = e.block_pk
        WHERE e.block_pk = ?
        ORDER BY e.match_score DESC, e.objective_uid ASC
        """,
        (int(block_pk),),
    ).fetchall()

    stmt_by_uid: Dict[str, str] = {}
    p = Path(ontology_path)
    if rows and p.exists():
        ont = load_consolidated_ontology(p)
        stmt_by_uid = {str(o["objective_uid"]): str(o.get("statement", "")) for o in ont.get("objectives", [])}
    return _enrich_reverse_rows(rows, stmt_by_uid)


def build_volume1_gap_report(
    conn: sqlite3.Connection,
    *,
    ontology_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    dag_path: Path | str = DEFAULT_DAG_PATH,
) -> Dict[str, Any]:
    """Costruisce il Radar Anti-Lacune completo per il Volume I (152 obiettivi K-13 + 64 nodi Strato 0 + P0.1..P0.8)."""
    conn.row_factory = sqlite3.Row
    ont = load_consolidated_ontology(ontology_path)
    dag = load_unified_dag(dag_path)
    dag_nodes: Dict[str, Dict[str, Any]] = dag["nodes"]

    map_rows = {
        str(r["objective_uid"]): r
        for r in conn.execute("SELECT * FROM objective_corpus_map").fetchall()
    }
    if not map_rows:
        raise RuntimeError(
            "La tabella `objective_corpus_map` è vuota: esegui prima `map_ontology_to_corpus()`."
        )

    k13_objectives = [o for o in ont["objectives"] if _is_k13_math_objective(o)]

    status_counts: Counter[str] = Counter()
    by_cycle_grade: Dict[str, Counter[str]] = defaultdict(Counter)
    gaps: List[Dict[str, Any]] = []
    partials: List[Dict[str, Any]] = []
    canonical_book_hits: Counter[Tuple[int, str]] = Counter()
    wrong_book_discoveries: List[Dict[str, Any]] = []
    seen_wb_pairs: set[Tuple[str, int]] = set()
    bridges_seen: set[int] = set()

    node_to_objs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for obj in k13_objectives:
        uid = str(obj["objective_uid"])
        mrow = map_rows.get(uid)
        status = str(mrow["coverage_status"]) if mrow else "gap"
        status_counts[status] += 1
        cg_key = f"{obj['cycle']} :: {obj['grade']}"
        by_cycle_grade[cg_key][status] += 1

        ev_list = json.loads(mrow["evidence_blocks_json"] or "[]") if mrow else []
        bridge_pks = json.loads(mrow["linked_bridge_pks_json"] or "[]") if mrow else []
        bridges_seen.update(int(pk) for pk in bridge_pks)

        for ev in ev_list:
            canonical_book_hits[(int(ev["book_pk"]), str(ev["book_title"]))] += 1
            if ev.get("is_wrong_book") and (uid, int(ev["block_pk"])) not in seen_wb_pairs:
                seen_wb_pairs.add((uid, int(ev["block_pk"])))
                wrong_book_discoveries.append(
                    {
                        "objective_uid": uid,
                        "grade": str(obj["grade"]),
                        "statement": str(obj["statement"]),
                        "book_pk": int(ev["book_pk"]),
                        "book_title": str(ev["book_title"]),
                        "primary_discipline": ev.get("primary_discipline"),
                        "block_pk": int(ev["block_pk"]),
                        "page_start": ev.get("page_start"),
                        "printed_page": ev.get("printed_page"),
                        "verbatim_quote": ev.get("verbatim_quote"),
                    }
                )

        summary_item = {
            "objective_uid": uid,
            "cycle": str(obj["cycle"]),
            "grade": str(obj["grade"]),
            "nucleus": str(obj["nucleus"]),
            "statement": str(obj["statement"]),
            "mapped_dag_node_ids": list(obj.get("mapped_dag_node_ids", [])),
            "matched_blocks_count": int(mrow["matched_blocks_count"]) if mrow else 0,
            "linked_bridge_count": int(mrow["linked_bridge_count"]) if mrow else 0,
        }
        if status == "gap":
            gaps.append(summary_item)
        elif status == "partial":
            partials.append(summary_item)

        for nid in obj.get("mapped_dag_node_ids", []):
            node_to_objs[str(nid)].append(
                {
                    "status": status,
                    "blocks_count": int(mrow["matched_blocks_count"]) if mrow else 0,
                }
            )

    # Analisi 64 nodi Strato 0 + 8 nodi Strato 1 (`P0.1..P0.8`)
    validated_bridges_by_node: Counter[str] = Counter()
    for br in conn.execute(
        "SELECT node_id, COUNT(*) AS n FROM curiosity_bridges WHERE status = 'validated' GROUP BY node_id"
    ).fetchall():
        validated_bridges_by_node[str(br["node_id"])] = int(br["n"])

    target_node_ids = [nid for nid, n in dag_nodes.items() if int(n.get("layer", -1)) == 0]
    ofa_p0_ids = sorted(nid for nid in dag_nodes if nid.startswith("P0."))
    all_volume1_nodes = target_node_ids + ofa_p0_ids

    dag_readiness: List[Dict[str, Any]] = []
    dag_status_counts: Counter[str] = Counter()
    for nid in all_volume1_nodes:
        node = dag_nodes[nid]
        linked = node_to_objs.get(nid, [])
        covered_n = sum(1 for x in linked if x["status"] == "covered")
        partial_n = sum(1 for x in linked if x["status"] == "partial")
        total_blks = sum(x["blocks_count"] for x in linked)
        br_count = validated_bridges_by_node.get(nid, 0)

        if (covered_n >= 1 and total_blks >= 3) or br_count >= 1:
            readiness = "ready"
        elif partial_n >= 1 or total_blks >= 1:
            readiness = "partial"
        else:
            readiness = "needs_attention"

        dag_status_counts[readiness] += 1
        dag_readiness.append(
            {
                "node_id": nid,
                "layer": int(node.get("layer", 0)),
                "title": str(node.get("title", nid)),
                "linked_objectives_count": len(linked),
                "covered_objectives_count": covered_n,
                "empirical_blocks_total": total_blks,
                "validated_bridges_count": br_count,
                "readiness": readiness,
            }
        )

    return {
        "k13_math_total": len(k13_objectives),
        "k13_status_counts": dict(sorted(status_counts.items())),
        "by_cycle_grade": {k: dict(sorted(v.items())) for k, v in sorted(by_cycle_grade.items())},
        "gaps_count": len(gaps),
        "gaps": gaps,
        "partials_count": len(partials),
        "partials": partials,
        "top_canonical_books": [
            {"book_pk": bpk, "title": title, "objective_hits": cnt}
            for (bpk, title), cnt in canonical_book_hits.most_common(20)
        ],
        "wrong_book_discoveries": wrong_book_discoveries[:30],
        "validated_bridges_linked_count": len(bridges_seen),
        "volume1_dag_nodes_summary": {
            "layer0_count": len(target_node_ids),
            "ofa_p0_count": len(ofa_p0_ids),
            "total_nodes": len(all_volume1_nodes),
            "readiness_counts": dict(sorted(dag_status_counts.items())),
        },
        "volume1_dag_nodes": dag_readiness,
    }


def save_corpus_coverage_report(
    conn: sqlite3.Connection,
    *,
    out_path: Path | str = DEFAULT_COVERAGE_REPORT_PATH,
    ontology_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    dag_path: Path | str = DEFAULT_DAG_PATH,
) -> Dict[str, Any]:
    """Salva il report aggregato `corpus_learnable` + Radar Volume I in JSON versionato."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM objective_corpus_map").fetchall()
    if not rows:
        raise RuntimeError(
            "La tabella `objective_corpus_map` è vuota: esegui prima `map_ontology_to_corpus()`."
        )

    by_status: Counter[str] = Counter()
    by_cycle: Dict[str, Counter[str]] = defaultdict(Counter)
    by_disc: Dict[str, Counter[str]] = defaultdict(Counter)
    wb_objectives = 0
    total_links = 0
    for r in rows:
        st = str(r["coverage_status"])
        by_status[st] += 1
        by_cycle[str(r["cycle"])][st] += 1
        by_disc[str(r["target_macro_discipline"])][st] += 1
        if int(r["wrong_book_evidence_count"]) > 0:
            wb_objectives += 1
        total_links += min(8, int(r["matched_blocks_count"]))

    radar = build_volume1_gap_report(conn, ontology_path=ontology_path, dag_path=dag_path)
    payload = {
        "schema_version": "ministerial-corpus-coverage.v1",
        "epistemic_layer": "corpus_learnable",
        "epistemic_principle": "R4: Report empirico corpus_learnable separato da ontology_v6_consolidated.json (institutional_declared).",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_objectives": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_cycle": {k: dict(sorted(v.items())) for k, v in sorted(by_cycle.items())},
        "by_discipline": {k: dict(sorted(v.items())) for k, v in sorted(by_disc.items())},
        "objectives_with_wrong_book_evidence": wb_objectives,
        "volume1_gap_radar": radar,
    }

    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mappatura bidirezionale dell'Ontologia Ministeriale v6 su pack_corpus.db (TASK-SPEC-04)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso a pack_corpus.db")
    parser.add_argument("--rebuild", action="store_true", help="Ricalcola `objective_corpus_map` su tutti i 2.828 obiettivi")
    parser.add_argument("--save-report", action="store_true", help="Salva `corpus_coverage_report.json`")
    parser.add_argument("--volume1-radar", action="store_true", help="Stampa il radar anti-lacune per Volume I")
    parser.add_argument("--book-pk", type=int, help="Query inversa: obiettivi toccati da questo libro")
    parser.add_argument("--only-wrong-book", action="store_true", help="Filtra solo i ruoli di Libro Sbagliato")
    parser.add_argument("--limit", type=int, default=15, help="Limite righe query inversa")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary: Optional[Dict[str, Any]] = None
    if args.rebuild:
        summary = map_ontology_to_corpus(args.db)

    conn = connect_corpus_db(args.db, read_only=True)
    try:
        out: Dict[str, Any] = {}
        if summary is not None:
            out["mapping_summary"] = summary

        if args.save_report:
            report_payload = save_corpus_coverage_report(conn)
            out["report_saved_to"] = str(DEFAULT_COVERAGE_REPORT_PATH)
            out["by_status"] = report_payload["by_status"]
            out["volume1_radar"] = report_payload["volume1_gap_radar"]
        elif args.volume1_radar:
            out["volume1_radar"] = build_volume1_gap_report(conn)

        if args.book_pk is not None:
            hits = find_objectives_for_book(conn, args.book_pk, only_wrong_book=args.only_wrong_book)
            out["book_objectives_total"] = len(hits)
            out["book_objectives"] = hits[: args.limit] if args.limit > 0 else hits

        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            if "mapping_summary" in out:
                ms = out["mapping_summary"]
                print(
                    f"Mappatura completata: {ms['total_objectives']} obiettivi | "
                    f"stato={ms['by_status']} | wrong_book_objs={ms['objectives_with_wrong_book_evidence']} | "
                    f"K13 Math={ms['k13_math_summary']}"
                )
            if "report_saved_to" in out:
                print(f"Report salvato in: {out['report_saved_to']}")
            if "volume1_radar" in out:
                vr = out["volume1_radar"]
                print(
                    f"\n=== Radar Volume I (K-13 Math {vr['k13_math_total']} obiettivi) ===\n"
                    f"  Stato K-13: {vr['k13_status_counts']} | "
                    f"DAG 64+8 nodi: {vr['volume1_dag_nodes_summary']['readiness_counts']}"
                )
                if vr["gaps"]:
                    print("  Lacune pure (`gap`):")
                    for g in vr["gaps"][:10]:
                        print(f"    - [{g['grade']}] {g['statement']}")
                if vr["wrong_book_discoveries"]:
                    print("  Scoperte 'Libro Sbagliato' su K-13:")
                    for wb in vr["wrong_book_discoveries"][:6]:
                        prim = label_for_discipline(wb["primary_discipline"]) if wb["primary_discipline"] else "Altra"
                        print(
                            f"    - [{wb['grade']}] {wb['book_title'][:50]} ({prim}, p.{wb['printed_page'] or wb['page_start']}): "
                            f"{wb['statement'][:85]}"
                        )
            if "book_objectives" in out:
                print(
                    f"\n=== Obiettivi ministeriali nel libro pk={args.book_pk} "
                    f"(tot={out['book_objectives_total']}, only_wrong_book={args.only_wrong_book}) ==="
                )
                for h in out["book_objectives"]:
                    tag = " [LIBRO SBAGLIATO]" if h["is_wrong_book"] else ""
                    print(
                        f"  - [{h['cycle']} | {h['subject']} | {h['grade']}]{tag} "
                        f"p.{h['printed_page'] or h['page_start']} score={h['match_score']:.2f}: {h['statement'][:105]}"
                    )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
