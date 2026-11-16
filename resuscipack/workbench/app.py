#!/usr/bin/env python3
"""Server Flask del Tavolo di Studio a 2 Colonne per SecAI (ADR-0003, TASK-SECAI-03).

Caratteristiche chiave:
- `pack_corpus.db` sempre aperto in sola lettura (`file:...?mode=ro`);
- `student_state.db` separato per progressi, Fast-Forward `SymPy` e Portfolio Hero;
- Barra superiore Bussola dell'Hero, Scheda Decisione di Progetto v3 + ponti "Libro Sbagliato"
  a sinistra (60%), Lettore del Libro Vero integrale con navigazione adiacente a destra (40%).
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request

from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db
from resuscipack.curriculum.cards import (
    DEFAULT_CARDS_DIR,
    list_available_card_ids,
    load_card,
)
from resuscipack.curriculum.dag import (
    DEFAULT_DAG_PATH,
    DEFAULT_OPEN_ACCESS_PATH,
    compute_frontier_nodes,
    load_open_access_registry,
    load_unified_dag,
)
from resuscipack.curriculum.drills_sympy import (
    evaluate_proof_rubric,
    generate_drill_set,
    grade_drill_answer,
    verify_graph_invariants,
)
from resuscipack.curriculum.student_state import (
    DEFAULT_STATE_DB_PATH,
    flag_card_issue,
    get_student_snapshot,
    init_student_state_db,
    record_drill_attempt,
    record_hero_artifact,
)
from resuscipack.epistemic.bridge import get_bridges_for_node


def sanitize_fts5_query(raw_query: str) -> str:
    """Sanifica una stringa utente in sintassi valida per SQLite FTS5 MATCH."""
    if not raw_query or not raw_query.strip():
        return ""
    trimmed = raw_query.strip()[:400]
    raw_tokens = re.findall(r'"([^"]*)"|(\S+)', trimmed)
    tokens: list[str] = []
    for phrase, word in raw_tokens:
        if phrase:
            clean_p = phrase.replace('"', '""').strip()
            if clean_p:
                tokens.append(f'"{clean_p}"')
        elif word:
            upper = word.upper()
            if upper in {"AND", "OR", "NOT"}:
                if tokens and tokens[-1] not in {"AND", "OR", "NOT"}:
                    tokens.append(upper)
            else:
                for sub in re.sub(r"[^0-9A-Za-zÀ-ÿ\s]", " ", word).split():
                    if sub:
                        tokens.append(f'"{sub}"')
    while tokens and tokens[-1] in {"AND", "OR", "NOT"}:
        tokens.pop()
    return " ".join(tokens[:24])


def highlight_verbatim_quote(full_text: str, quote: str | None) -> tuple[str, bool]:
    """Restituisce HTML sicuro del testo completo del blocco evidenziando in `<mark>` la citazione
    anche se nel testo originale sono presenti a capo o punteggiatura tipografica equivalente."""
    if not quote or not quote.strip():
        return html.escape(full_text, quote=False), False

    words = [w for w in re.findall(r"\S+", quote.strip()) if w]
    if not words:
        return html.escape(full_text, quote=False), False

    def _word_regex(token: str) -> str:
        # Tollera apostrofi dritti/curvi, virgolette e sillabazione morbida
        core = re.escape(token)
        core = core.replace(r"\'", r"['’‘]").replace("’", r"['’‘]")
        core = core.replace("«", r'[«"“]').replace("»", r'[»"”]')
        core = core.replace(r"\"", r'[«»"“”]')
        return core

    pattern_str = r"\s+".join(_word_regex(w) for w in words)
    m = re.search(pattern_str, full_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return html.escape(full_text, quote=False), False

    before = html.escape(full_text[: m.start()], quote=False)
    matched = html.escape(full_text[m.start() : m.end()], quote=False)
    after = html.escape(full_text[m.end() :], quote=False)
    return f'{before}<mark class="verbatim-highlight">{matched}</mark>{after}', True


def create_app(
    *,
    corpus_db_path: Path | str = DEFAULT_DB_PATH,
    state_db_path: Path | str = DEFAULT_STATE_DB_PATH,
    dag_path: Path | str = DEFAULT_DAG_PATH,
    open_access_path: Path | str = DEFAULT_OPEN_ACCESS_PATH,
    cards_dir: Path | str = DEFAULT_CARDS_DIR,
) -> Flask:
    here = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(here / "templates"),
        static_folder=str(here / "static"),
    )
    app.config["CORPUS_DB_PATH"] = Path(corpus_db_path)
    app.config["STATE_DB_PATH"] = Path(state_db_path)
    app.config["DAG_PATH"] = Path(dag_path)
    app.config["OPEN_ACCESS_PATH"] = Path(open_access_path)
    app.config["CARDS_DIR"] = Path(cards_dir)

    dag_payload = load_unified_dag(app.config["DAG_PATH"])
    oa_registry = load_open_access_registry(app.config["OPEN_ACCESS_PATH"])
    oa_by_id = {item["id"]: item for item in oa_registry.get("open_access_acquisitions", [])}

    # Inizializza il DB separato dello stato studente (mai pack_corpus.db!)
    init_student_state_db(app.config["STATE_DB_PATH"]).close()

    def _state_conn():
        return init_student_state_db(app.config["STATE_DB_PATH"])

    def _corpus_ro_conn():
        db_p: Path = app.config["CORPUS_DB_PATH"]
        if not db_p.exists():
            return None
        return connect_corpus_db(db_p, read_only=True)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/overview")
    def api_overview():
        with _state_conn() as sconn:
            snap = get_student_snapshot(sconn)
        mastered_set = set(snap["mastered_ids"])
        failed_set = set(snap["failed_ids"])
        frontier = compute_frontier_nodes(dag_payload, mastered_set, failed_set)
        card_ids = list_available_card_ids(app.config["CARDS_DIR"])

        topo_nodes = []
        for nid in dag_payload["metadata"]["topological_order"]:
            node = dict(dag_payload["nodes"][nid])
            prog = snap["progress_by_node"].get(nid)
            node["student_status"] = prog["status"] if prog else "not_started"
            node["has_card"] = nid in card_ids
            topo_nodes.append(node)

        ofa_gate = dag_payload["nodes"]["G00"]
        ofa_reqs = ofa_gate["prerequisites"]
        ofa_ready_count = sum(1 for r in ofa_reqs if r in mastered_set)

        return jsonify(
            {
                "metadata": dag_payload["metadata"],
                "hero_profile": dag_payload["hero_profile"],
                "nodes": topo_nodes,
                "frontier_nodes": frontier,
                "mastered_ids": snap["mastered_ids"],
                "failed_ids": snap["failed_ids"],
                "hero_artifacts": snap["hero_artifacts"],
                "ofa_readiness": {
                    "gate_id": "G00",
                    "required_units": ofa_reqs,
                    "ready_count": ofa_ready_count,
                    "total_count": len(ofa_reqs),
                    "deadline": ofa_gate.get("window", ""),
                },
                "open_access_registry": oa_registry,
            }
        )

    @app.get("/api/node/<path:node_id>")
    def api_node(node_id: str):
        nodes = dag_payload["nodes"]
        if node_id not in nodes:
            abort(404, description=f"Nodo curricolare sconosciuto: {node_id}")

        node = dict(nodes[node_id])
        card = load_card(node_id, app.config["CARDS_DIR"])

        bridges: list[dict[str, Any]] = []
        cconn = _corpus_ro_conn()
        if cconn is not None:
            try:
                bridges = get_bridges_for_node(cconn, node_id, only_validated=True, prefix_fallback=False)
            finally:
                cconn.close()

        seed_param = request.args.get("seed", type=int)
        drills = generate_drill_set(
            node_id=node_id,
            drill_key=node.get("drill_key"),
            count=5,
            seed=seed_param,
        )

        with _state_conn() as sconn:
            snap = get_student_snapshot(sconn)
        prog = snap["progress_by_node"].get(
            node_id,
            {
                "node_id": node_id,
                "status": "not_started",
                "card_governance": card["status"] if card else "validata_auto",
                "correct_count": 0,
                "attempt_count": 0,
                "distinct_pass_days": 0,
            },
        )

        open_access_books = [
            oa_by_id[oid] for oid in node.get("open_access_ids", []) if oid in oa_by_id
        ]

        return jsonify(
            {
                "node": node,
                "hero_compass": node["hero_compass"],
                "progress": prog,
                "card": card,
                "wrong_book_bridges": bridges,
                "drills": drills,
                "open_access_books": open_access_books,
            }
        )

    @app.post("/api/drill/submit")
    def api_drill_submit():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "").strip()
        drill_id = str(data.get("drill_id") or f"{node_id}#q1").strip()
        expected = str(data.get("expected") or "").strip()
        student_answer = str(data.get("student_answer") or "").strip()
        attempt_day = data.get("attempt_day")

        if node_id not in dag_payload["nodes"] or not expected:
            abort(400, description="Parametri node_id ed expected obbligatori")

        grade = grade_drill_answer(expected=expected, student_answer=student_answer)
        with _state_conn() as sconn:
            updated_prog = record_drill_attempt(
                sconn,
                node_id=node_id,
                drill_id=drill_id,
                student_answer=student_answer,
                expected_answer=expected,
                is_correct=grade["is_correct"],
                attempt_day=str(attempt_day) if attempt_day else None,
            )
            snap = get_student_snapshot(sconn)

        frontier = compute_frontier_nodes(
            dag_payload,
            set(snap["mastered_ids"]),
            set(snap["failed_ids"]),
        )
        return jsonify(
            {
                "grade": grade,
                "progress": updated_prog,
                "frontier_nodes": frontier,
                "mastered_ids": snap["mastered_ids"],
            }
        )

    @app.post("/api/hero/graph-check")
    def api_hero_graph_check():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "P0.6").strip()
        spec_id = str(data.get("spec_id") or "abs_shifted_log").strip()
        answers = data.get("answers") or {}
        try:
            res = verify_graph_invariants(spec_id, answers)
        except ValueError as exc:
            abort(400, description=str(exc))

        with _state_conn() as sconn:
            record_hero_artifact(
                sconn,
                node_id=node_id,
                proof_family="graph_invariants",
                payload={"spec_id": spec_id, "answers": answers, "passed_count": res["passed_count"]},
                passed=res["all_passed"],
            )
        return jsonify(res)

    @app.post("/api/hero/proof-check")
    def api_hero_proof_check():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "P0.4").strip()
        rubric_id = str(data.get("rubric_id") or "sqrt2_irrational").strip()
        proof_text = str(data.get("proof_text") or "")
        try:
            res = evaluate_proof_rubric(rubric_id, proof_text)
        except ValueError as exc:
            abort(400, description=str(exc))

        with _state_conn() as sconn:
            record_hero_artifact(
                sconn,
                node_id=node_id,
                proof_family="rubric_proof",
                payload={"rubric_id": rubric_id, "passed_count": res["passed_count"]},
                passed=res["all_passed"],
            )
        return jsonify(res)

    @app.post("/api/card/flag")
    def api_card_flag():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "").strip()
        note = str(data.get("note") or "").strip()
        if not node_id or not note:
            abort(400, description="node_id e note sono obbligatori")
        with _state_conn() as sconn:
            res = flag_card_issue(sconn, node_id=node_id, note=note)
        return jsonify(res)

    @app.get("/api/block/<int:block_pk>")
    def api_block(block_pk: int):
        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            row = cconn.execute(
                """
                SELECT
                    bl.block_pk,
                    bl.block_uid,
                    bl.book_pk,
                    bl.book_title,
                    bl.is_active,
                    bl.superseded_by_pk,
                    bl.block_role,
                    bl.page_start,
                    bl.page_end,
                    bl.printed_page,
                    bl.section_title,
                    bl.content,
                    bl.char_count,
                    bl.source_origin,
                    bk.author,
                    bk.year,
                    bk.surface_domain,
                    bk.source_kind
                FROM blocks bl
                JOIN books bk ON bk.book_pk = bl.book_pk
                WHERE bl.block_pk = ?
                """,
                (block_pk,),
            ).fetchone()
            if row is None:
                abort(404, description=f"Blocco {block_pk} non trovato in pack_corpus.db")

            prev_row = cconn.execute(
                """
                SELECT block_pk FROM blocks
                WHERE book_pk = ? AND is_active = 1 AND block_pk < ?
                ORDER BY block_pk DESC LIMIT 1
                """,
                (row["book_pk"], block_pk),
            ).fetchone()
            next_row = cconn.execute(
                """
                SELECT block_pk FROM blocks
                WHERE book_pk = ? AND is_active = 1 AND block_pk > ?
                ORDER BY block_pk ASC LIMIT 1
                """,
                (row["book_pk"], block_pk),
            ).fetchone()

            quote = request.args.get("quote", "")
            highlighted_html, quote_matched = highlight_verbatim_quote(str(row["content"]), quote)

            return jsonify(
                {
                    "block_pk": int(row["block_pk"]),
                    "block_uid": row["block_uid"],
                    "book_pk": int(row["book_pk"]),
                    "book_title": row["book_title"],
                    "author": row["author"],
                    "year": row["year"],
                    "surface_domain": row["surface_domain"],
                    "source_kind": row["source_kind"],
                    "source_origin": row["source_origin"],
                    "block_role": row["block_role"],
                    "page_start": row["page_start"],
                    "page_end": row["page_end"],
                    "printed_page": row["printed_page"],
                    "section_title": row["section_title"],
                    "is_active": bool(row["is_active"]),
                    "superseded_by_pk": row["superseded_by_pk"],
                    "char_count": int(row["char_count"]),
                    "content": row["content"],
                    "highlighted_html": highlighted_html,
                    "quote_matched": quote_matched,
                    "prev_block_pk": int(prev_row["block_pk"]) if prev_row else None,
                    "next_block_pk": int(next_row["block_pk"]) if next_row else None,
                }
            )
        finally:
            cconn.close()

    @app.get("/api/search")
    def api_search():
        raw_q = request.args.get("q", "")
        limit = min(max(request.args.get("limit", default=25, type=int), 1), 100)
        fts_q = sanitize_fts5_query(raw_q)
        if not fts_q:
            return jsonify({"query": raw_q, "sanitized_query": "", "results": []})

        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            rows = cconn.execute(
                """
                SELECT
                    bl.block_pk,
                    bl.block_uid,
                    bl.book_title,
                    bk.author,
                    bk.year,
                    bk.surface_domain,
                    bl.page_start,
                    bl.section_title,
                    snippet(passages_fts, 2, '<mark>', '</mark>', ' … ', 32) AS snippet_html,
                    bm25(passages_fts, 2.0, 1.5, 1.0) AS score
                FROM passages_fts
                JOIN blocks bl ON bl.block_pk = passages_fts.rowid
                JOIN books bk ON bk.book_pk = bl.book_pk
                WHERE passages_fts MATCH ?
                  AND bl.is_active = 1
                ORDER BY score
                LIMIT ?
                """,
                (fts_q, limit),
            ).fetchall()
            results = [dict(r) for r in rows]
            return jsonify({"query": raw_q, "sanitized_query": fts_q, "count": len(results), "results": results})
        finally:
            cconn.close()

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avvia il Tavolo di Studio SecAI di resuscipack")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
