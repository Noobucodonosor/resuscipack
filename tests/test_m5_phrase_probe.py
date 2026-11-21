"""Test per Milestone M5 Fase 3: indici `units_fts`/`concept_edges` e `phrase_analyzer` (TASK-PROBE-01)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db
from resuscipack.epistemic.phrase_analyzer import probe_selection, rebuild_phrase_indices
from resuscipack.workbench.app import create_app


def test_phrase_probe_handles_shell_words_cardinalita_and_proposition_trial(tmp_path: Path) -> None:
    db_path = tmp_path / "probe.db"
    conn = init_corpus_db(db_path)
    books = [
        ("bk_gal", "Dialogo sui massimi sistemi", "Galileo Galilei", 1632, "storia_della_scienza"),
        ("bk_fre", "Fondamenti dell'aritmetica", "Gottlob Frege", 1884, "matematica"),
        ("bk_sto", "Storia papale del Trecento", "Storico Test", 1990, "storia"),
    ]
    bpk_map: dict[str, int] = {}
    for buid, title, auth, yr, dom in books:
        conn.execute(
            "INSERT INTO books (book_uid, title, author, year, surface_domain, source_kind, is_active) VALUES (?, ?, ?, ?, ?, 'from_before', 1)",
            (buid, title, auth, yr, dom),
        )
        bpk_map[buid] = conn.execute("SELECT book_pk FROM books WHERE book_uid=?", (buid,)).fetchone()[0]

    blocks_data = [
        ("blk_gal", bpk_map["bk_gal"], "Il contare per corrispondenza biunivoca mostra l'infinito dei quadrati.", "Galileo"),
        ("blk_fre", bpk_map["bk_fre"], "La cardinalità non nasce da un atto psicologico del contare ma da un concetto logico.", "Frege"),
        ("blk_sto", bpk_map["bk_sto"], "I cardinali alla corte papale di Avignone discussero nel 1342.", "Papi"),
    ]
    for blk_uid, bpk, txt, sec in blocks_data:
        conn.execute(
            """
            INSERT INTO blocks (
                block_uid, book_pk, book_title, source_origin, page_start, page_end,
                section_title, content, norm_content, char_count, est_tokens, block_role, is_active
            ) VALUES (?, ?, ?, 'from_before', 1, 1, ?, ?, ?, ?, 15, 'body', 1)
            """,
            (blk_uid, bpk, sec, sec, txt, txt.lower(), len(txt)),
        )
        blk_pk = conn.execute("SELECT block_pk FROM blocks WHERE block_uid=?", (blk_uid,)).fetchone()[0]
        if blk_uid == "blk_gal":
            conn.execute(
                """
                INSERT INTO epistemic_units (unit_uid, block_pk, kind, mode, stmt, verbatim_quote, actors_json, concepts_json)
                VALUES ('u_gal', ?, 'def', 'defines', 'Galileo usa l atto del contare per mostrare l equipotenza.', 'contare per corrispondenza biunivoca', '["Galileo Galilei"]', '["contare", "corrispondenza biunivoca", "astrazione"]')
                """,
                (blk_pk,),
            )
        elif blk_uid == "blk_fre":
            conn.execute(
                """
                INSERT INTO epistemic_units (unit_uid, block_pk, kind, mode, stmt, verbatim_quote, actors_json, vs_dispute, concepts_json)
                VALUES ('u_fre', ?, 'dispute', 'critiques', 'Frege contesta che la cardinalita derivi dall atto psicologico del contare.', 'cardinalità non nasce da un atto psicologico del contare', '["Gottlob Frege"]', 'psicologismo nel contare', '["cardinalita", "astrazione", "matematica"]')
                """,
                (blk_pk,),
            )
        else:
            conn.execute(
                """
                INSERT INTO epistemic_units (unit_uid, block_pk, kind, mode, stmt, verbatim_quote, actors_json, concepts_json)
                VALUES ('u_sto', ?, 'claim', 'narrates', 'I cardinali di Avignone si riunirono nel 1342.', 'cardinali alla corte papale di Avignone', '[]', '["avignone", "corte papale"]')
                """,
                (blk_pk,),
            )
    conn.commit()
    conn.close()

    stats = rebuild_phrase_indices(db_path)
    assert stats["units_fts_rows"] == 3
    assert stats["concept_edges_rows"] >= 3

    ro = connect_corpus_db(db_path, read_only=True)
    try:
        # 1. Sintagma con parole-guscio ("l'atto del contare")
        res_phrase = probe_selection(ro, "l'atto del contare")
        assert res_phrase["mode"] == "phrase_probe"
        assert len(res_phrase["confirmations"]) >= 1
        assert res_phrase["confirmations"][0]["actors"] == ["Galileo Galilei"]

        # 2. "cardinalità" NON deve pescare i cardinali di Avignone!
        res_card = probe_selection(ro, "cardinalità")
        all_hits = res_card["confirmations"] + res_card["rivals"]
        assert all("Avignone" not in h["stmt"] for h in all_hits)
        assert len(res_card["rivals"]) >= 1

        # 3. Processo alla Proposizione (frase intera Vol. 1 Cap. 1)
        prop = "L'atto del contare rappresenta il primo, fondamentale passo dell'intelletto umano verso l'astrazione matematica"
        res_prop = probe_selection(ro, prop)
        assert res_prop["mode"] == "proposition_trial"
        assert len(res_prop["confirmations"]) >= 1
        assert len(res_prop["rivals"]) >= 1
        assert len(res_prop["bridges"]) >= 1
    finally:
        ro.close()

    # 4. Endpoint REST workbench su DB portabile + verifica UI /libro e /atlante
    app = create_app(corpus_db_path=db_path, state_db_path=tmp_path / "ui_state.db")
    client = app.test_client()

    r_probe = client.post("/api/probe/selection", json={"text": "l'atto del contare", "chapter_context": "Numeri"})
    assert r_probe.status_code == 200
    pdata = r_probe.get_json()
    assert pdata["mode"] == "phrase_probe"
    assert len(pdata["confirmations"]) >= 1

    r_bib = client.get("/api/atlas/bibliographic-citations")
    assert r_bib.status_code == 200
    assert "extracted" in r_bib.get_json()
    assert "candidates" in r_bib.get_json()

    r_fig = client.get("/api/atlas/figures?limit=5")
    assert r_fig.status_code == 200
    assert "figures" in r_fig.get_json()

    r_libro = client.get("/libro")
    assert r_libro.status_code == 200
    assert 'id="probeDrawer"' in r_libro.get_data(as_text=True)

    r_atl = client.get("/atlante")
    assert r_atl.status_code == 200
    atl_html = r_atl.get_data(as_text=True)
    assert 'id="tabSourcesBtn"' in atl_html
    assert 'id="tabStudyFiguresBtn"' in atl_html
    assert 'tabindex="-1"' in atl_html


@pytest.mark.real_corpus
@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_live_corpus_phrase_probe_returns_clean_results() -> None:
    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        res = probe_selection(conn, "l'atto del contare")
        assert res["mode"] == "phrase_probe"
        assert len(res["confirmations"]) + len(res["rivals"]) >= 1
    finally:
        conn.close()
