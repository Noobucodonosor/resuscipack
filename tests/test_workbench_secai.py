"""Test end-to-end e unitari per Spina Dorsale Curricolare SecAI, Motore SymPy,
Schede v3 a 6 Gate e Tavolo di Studio Flask a 2 Colonne (ADR-0003, TASK-SECAI-01..03)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from resuscipack.curriculum.cards import list_available_card_ids, load_card
from resuscipack.curriculum.dag import (
    compute_frontier_nodes,
    load_open_access_registry,
    load_unified_dag,
    topological_sort,
)
from resuscipack.curriculum.drills_sympy import (
    evaluate_proof_rubric,
    generate_drill_set,
    grade_drill_answer,
    verify_graph_invariants,
)
from resuscipack.curriculum.student_state import (
    get_student_snapshot,
    init_student_state_db,
    record_drill_attempt,
)
from resuscipack.epistemic.verifica_citazioni import verifica_scheda_report
from resuscipack.workbench.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB = REPO_ROOT / "data" / "pack_corpus.db"
CARDS_DIR = REPO_ROOT / "data" / "cards"


def test_dag_4_layers_acyclic_and_zero_dead_ends() -> None:
    dag = load_unified_dag()
    meta = dag["metadata"]
    assert meta["acyclic"] is True
    assert meta["total_nodes"] == 108
    assert meta["layer_counts"] == {
        "layer_0_foundations": 64,
        "layer_1_ofa_pre": 11,
        "layer_2_shadow_bridges": 12,
        "layer_3_secai_gates": 21,
    }

    superiori_nodes = [nid for nid in dag["nodes"] if nid.startswith("superiori.")]
    assert len(superiori_nodes) == 19
    for snid in superiori_nodes:
        assert dag["nodes"][snid]["hero_compass"]["gates_unlocked_count"] >= 1

    # Dal mattone #1 della 1ª elementare la Bussola dell'Hero punta a G00 (OFA formale) e oltre
    q_node = dag["nodes"]["numeri.quantita"]
    assert q_node["hero_compass"]["serves_ofa_formal"] is True
    assert q_node["hero_compass"]["target_gate_id"] == "G00"
    assert "G09" in q_node["hero_compass"]["gates_unlocked"]  # Defensive Security

    # Verifica presenza del ponte critico 0 CFU (P3.1, P3.2, P3.3) verso G05 Machine Learning
    ml_gate = dag["nodes"]["G05"]
    for bridge_unit in ("P3.1", "P3.2", "P3.3"):
        assert bridge_unit in ml_gate["prerequisites"]

    # Verifica che l'introduzione artificiale di un ciclo venga bloccata da topological_sort
    corrupted = copy.deepcopy(dag["nodes"])
    corrupted["numeri.quantita"]["prerequisites"].append("G20")
    with pytest.raises(ValueError, match="Ciclo rilevato"):
        topological_sort(corrupted)

    oa = load_open_access_registry()
    assert len(oa["open_access_acquisitions"]) == 5
    reclassified_ids = {item["unit_id"] for item in oa["reclassified_as_covered_in_wave0"]}
    assert {"P0.8", "P0.5"} <= reclassified_ids


def test_migrated_cards_pass_all_6_gates() -> None:
    card_ids = list_available_card_ids(CARDS_DIR)
    expected_cards = {
        "numeri.quantita",
        "numeri.ordine",
        "numeri.posizionale",
        "operazioni.addizione",
        "operazioni.sottrazione",
        "frazioni.denominatore-comune",
        "P0.5",
    }
    assert expected_cards <= card_ids

    for cid in sorted(card_ids):
        card_path = CARDS_DIR / f"{cid}.md"
        report = verifica_scheda_report(card_path, db_path=CORPUS_DB)
        assert report.ok, f"Scheda {cid} ha fallito i Gate: {report.all_errors}"

    parsed_q = load_card("numeri.quantita", CARDS_DIR)
    assert parsed_q is not None
    assert len(parsed_q["footnotes"]) == 7
    assert 'data-block-pk="13581"' in parsed_q["html"]
    assert "stmt-definizione" in parsed_q["html"]
    assert "stmt-teorema" in parsed_q["html"]

    parsed_p05 = load_card("P0.5", CARDS_DIR)
    assert parsed_p05 is not None
    assert "wrong-book-callout" in parsed_p05["html"]
    assert 'data-block-pk="28379"' in parsed_p05["html"]


def test_drills_sympy_equivalence_graph_and_proof_rubrics() -> None:
    # 7/20 e 0.35 (o 0,35) devono essere accettati entrambi da SymPy
    assert grade_drill_answer("7/20", "7/20")["is_correct"] is True
    assert grade_drill_answer("7/20", "0.35")["is_correct"] is True
    assert grade_drill_answer("7/20", "0,35")["is_correct"] is True
    assert grade_drill_answer("7/20", "2/9")["is_correct"] is False

    # Fattorizzazione quadratica equivalente in qualunque ordine dei fattori
    assert grade_drill_answer("(x - 2)*(x - 5)", "(x - 5)*(x - 2)")["is_correct"] is True
    assert grade_drill_answer("(x - 2)*(x - 5)", "x^2 - 7*x + 10")["is_correct"] is True

    # Intervallo Marconi |x - 120| <= 25 -> [95, 145]
    drills_p05 = generate_drill_set("P0.5", "drill_p0_symbolic_inequalities", count=4, seed=42)
    assert len(drills_p05) == 4
    assert grade_drill_answer("[95, 145]", "[95, 145]")["is_correct"] is True

    # Verifica grafico a mano P0.6: y = |ln(x - 2)| + 1
    bad_graph = verify_graph_invariants(
        "abs_shifted_log",
        {
            "domain_lower_bound": "0",
            "vertical_asymptote_x": "2",
            "cusp_x": "3",
            "cusp_y": "1",
            "probe_y_at_2_plus_e": "2",
            "left_branch": "decrescente",
            "right_branch": "crescente",
        },
    )
    assert bad_graph["all_passed"] is False
    assert bad_graph["reference_curve_points"] == []

    good_graph = verify_graph_invariants(
        "abs_shifted_log",
        {
            "domain_lower_bound": "2",
            "vertical_asymptote_x": "2",
            "cusp_x": "3",
            "cusp_y": "1",
            "probe_y_at_2_plus_e": "2",
            "left_branch": "decrescente",
            "right_branch": "crescente",
        },
    )
    assert good_graph["all_passed"] is True
    assert len(good_graph["reference_curve_points"]) >= 50

    # Verifica rubrica dimostrazione sqrt(2) irrazionale: dimenticare MCD(a,b)=1 deve fallire!
    incomplete_proof = (
        "Supponiamo sqrt(2) = a/b. Allora a^2 = 2b^2 quindi a è pari. "
        "Poniamo a = 2k, allora b^2 = 2k^2 quindi b è pari. Assurdo."
    )
    res_inc = evaluate_proof_rubric("sqrt2_irrational", incomplete_proof)
    assert res_inc["all_passed"] is False
    assert res_inc["results"][0]["lemma_id"] == "L1_coprime_assumption"
    assert res_inc["results"][0]["present"] is False

    complete_proof = (
        "Supponiamo per assurdo che sqrt(2) = a/b con frazione ridotta ai minimi termini, cioè MCD(a,b)=1. "
        "Elevando al quadrato otteniamo a^2 = 2b^2, dunque a^2 è pari e quindi a è pari. "
        "Sostituendo a = 2k otteniamo 4k^2 = 2b^2 ossia b^2 = 2k^2, perciò anche b è pari. "
        "Questo è in contraddizione con l'ipotesi MCD(a,b)=1."
    )
    res_ok = evaluate_proof_rubric("sqrt2_irrational", complete_proof)
    assert res_ok["all_passed"] is True


def test_student_state_fast_forward_and_2day_consolidation(tmp_path: Path) -> None:
    dag = load_unified_dag()
    state_db = tmp_path / "student_state.db"
    conn = init_student_state_db(state_db)
    try:
        for i in range(4):
            prog = record_drill_attempt(
                conn,
                node_id="numeri.quantita",
                drill_id=f"numeri.quantita#q{i+1}",
                student_answer="24",
                expected_answer="24",
                is_correct=True,
                attempt_day="2026-11-16",
            )
        assert prog["status"] == "fast_forwarded"

        # Conferma il giorno successivo -> promozione a `consolidated`
        prog_day2 = record_drill_attempt(
            conn,
            node_id="numeri.quantita",
            drill_id="numeri.quantita#q5",
            student_answer="iniettiva",
            expected_answer="iniettiva",
            is_correct=True,
            attempt_day="2026-11-17",
        )
        assert prog_day2["status"] == "consolidated"
        assert prog_day2["card_governance"] == "consolidata"

        # Errore su `numeri.ordine` lo porta in cima ai Nodi Frontiera come `punto_debole_rilevato`
        record_drill_attempt(
            conn,
            node_id="numeri.ordine",
            drill_id="numeri.ordine#q1",
            student_answer="999",
            expected_answer="100",
            is_correct=False,
            attempt_day="2026-11-17",
        )
        snap = get_student_snapshot(conn)
        frontier = compute_frontier_nodes(
            dag,
            set(snap["mastered_ids"]),
            set(snap["failed_ids"]),
        )
        assert frontier[0]["id"] == "numeri.ordine"
        assert frontier[0]["frontier_reason"] == "punto_debole_rilevato"
    finally:
        conn.close()


def test_workbench_flask_endpoints_and_true_book_reader(tmp_path: Path) -> None:
    import json

    status_file = tmp_path / "wave1_status.json"
    status_file.write_text(
        json.dumps({"state": "running", "wave": 1, "blocks_completed": 40, "blocks_total_in_wave": 5000}),
        encoding="utf-8",
    )
    app = create_app(
        corpus_db_path=CORPUS_DB,
        state_db_path=tmp_path / "workbench_state.db",
        status_file_path=status_file,
    )
    client = app.test_client()

    # 0. Endpoint /api/extraction_status
    r_st = client.get("/api/extraction_status")
    assert r_st.status_code == 200
    st = r_st.get_json()
    assert st["books_active"] >= 1370
    assert st["blocks_active"] >= 100000
    assert st["blocks_extracted"] >= 5
    assert st["validated_bridges"] >= 9
    assert st["state"] == "running"
    assert st["live_wave"]["blocks_completed"] == 40

    # 1. Pagina principale HTML + Bussola Hero
    r_index = client.get("/")
    assert r_index.status_code == 200
    html_text = r_index.get_data(as_text=True)
    assert "heroCompassBar" in html_text
    assert "bookReaderContainer" in html_text

    # 2. Overview del grafo a 4 strati
    r_ov = client.get("/api/overview")
    assert r_ov.status_code == 200
    ov = r_ov.get_json()
    assert ov["metadata"]["total_nodes"] == 108
    assert len(ov["frontier_nodes"]) >= 1

    # 3. Nodo P0.5 e apertura libro vero su Marconi a Santa Margherita (block_pk=28379)
    r_node = client.get("/api/node/P0.5?seed=42")
    assert r_node.status_code == 200
    nd = r_node.get_json()
    assert nd["hero_compass"]["target_gate_id"] == "G00"
    assert nd["card"]["id"] == "P0.5"
    assert len(nd["wrong_book_bridges"]) >= 1
    assert nd["wrong_book_bridges"][0]["block_pk"] == 28379
    fn1 = nd["card"]["footnotes"][0]
    assert fn1["block_pk"] == 28379

    # Verifica anche Galvani su P0.2 e Cartesio su P4.1 da curiosity_bridges
    assert client.get("/api/node/P0.2").get_json()["wrong_book_bridges"][0]["block_pk"] == 2036
    assert client.get("/api/node/P4.1").get_json()["wrong_book_bridges"][0]["block_pk"] == 46349

    r_blk = client.get(f"/api/block/{fn1['block_pk']}?quote={fn1['quote']}")
    assert r_blk.status_code == 200
    blk = r_blk.get_json()
    assert blk["block_uid"] == "blk_91211199164d867ea4c8"
    assert "Marconi" in blk["book_title"]
    assert "Santa Margherita Ligure" in blk["content"]
    assert blk["quote_matched"] is True
    assert '<mark class="verbatim-highlight">' in blk["highlighted_html"]
    assert blk["prev_block_pk"] is not None

    # Verifica che il blocco precedente appartenga allo stesso volume di Masini
    r_prev = client.get(f"/api/block/{blk['prev_block_pk']}")
    assert r_prev.status_code == 200
    assert r_prev.get_json()["book_pk"] == blk["book_pk"]

    # 4. Ricerca FTS5 diretta nella biblioteca
    r_search = client.get('/api/search?q=Marconi "Santa Margherita"&limit=10')
    assert r_search.status_code == 200
    s_data = r_search.get_json()
    assert s_data["count"] >= 1
    assert any(h["block_pk"] == 28379 for h in s_data["results"])

    # 5. Invio risposta drill SymPy via API
    d0 = nd["drills"][0]
    r_sub = client.post(
        "/api/drill/submit",
        json={
            "node_id": "P0.5",
            "drill_id": d0["drill_id"],
            "expected": d0["expected"],
            "student_answer": d0["expected"],
        },
    )
    assert r_sub.status_code == 200
    assert r_sub.get_json()["grade"]["is_correct"] is True

    # 6. Assenza assoluta di `.slice(` nei sorgenti frontend/backend del workbench
    for src_file in (REPO_ROOT / "resuscipack" / "workbench").rglob("*"):
        if src_file.is_file() and src_file.suffix in {".py", ".js", ".html"}:
            assert ".slice(" not in src_file.read_text(encoding="utf-8")
