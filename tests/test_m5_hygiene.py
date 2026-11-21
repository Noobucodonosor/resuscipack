"""Test per Milestone M5 Fase 1: prompt `w`, 3 micro-bug e bonifica deterministica €0 (TASK-HYG-01..02)."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from resuscipack.corpus.schema import init_corpus_db
from resuscipack.epistemic.batch_cli import (
    build_multiblock_extraction_prompt,
    build_v22_compact_item_schema,
    group_rows_into_book_windows,
)
from resuscipack.epistemic.curriculum_mapper import extract_objective_query_terms
from resuscipack.epistemic.decompressor import (
    _build_safe_fts_query,
    _extract_query_terms,
    _token_matches_hay,
    parse_historical_year,
)
from resuscipack.epistemic.hygiene_cleanup import clean_actor_list, run_hygiene_cleanup
from resuscipack.epistemic.spectrum import is_residual_paratext_block


def test_prompt_defines_w_thm_deep_blocks_and_window_overlap() -> None:
    prompt = build_multiblock_extraction_prompt(
        book_title="Storia della matematica",
        surface_domain="matematica",
        rows=[{"block_pk": 10, "page_start": 1, "section_title": "Cap. 1", "content": "Euclide e Proclo."}],
        max_units=6,
    )
    assert "`w` = nomi propri di persone, autori o scuole" in prompt
    assert "`k`='thm' SOLO per teoremi o leggi formali" in prompt
    assert "fino a 6 unità" in prompt

    schema = build_v22_compact_item_schema(6)
    assert schema["properties"]["u"]["maxItems"] == 6

    fake_rows = [{"book_pk": 1, "page_start": i} for i in range(1, 10)]
    windows = group_rows_into_book_windows(fake_rows, pack_size=5, overlap=1)  # type: ignore[arg-type]
    assert [w["page_start"] for w in windows[0]] == [1, 2, 3, 4, 5]
    assert [w["page_start"] for w in windows[1]] == [5, 6, 7, 8, 9]


def test_three_micro_bugs_fixed() -> None:
    # 1. Secoli romani d.C.
    assert parse_historical_year("III sec. d.C.") == (250, "III sec. d.C.")
    assert parse_historical_year("III d.C.") == (250, "III sec. d.C.")

    # 2. Stemmer sicuro: "cardinalità" non deve matchare "cardinali"; parole-guscio filtrate
    fts_card = _build_safe_fts_query(_extract_query_terms("cardinalità"))
    assert "cardinal*" not in fts_card
    assert not _token_matches_hay("cardinalità", "i cardinali alla corte papale", {"cardinali", "corte"})
    terms = _extract_query_terms("l'atto del contare")
    assert "atto" not in terms
    assert "contare" in terms

    # 3. Bibliografia ragionata NON è paratext, indice con puntini sì
    reasoned_biblio = (
        "NOTA BIBLIOGRAFICA\n\n"
        "Per l'esame critico delle fonti greche rimane fondamentale il commento storico di Heath, "
        "che ricostruisce con grande rigore il passaggio da Eudemo a Proclo.\n"
        "L'edizione critica curata da Frajese discute inoltre le divergenze testuali sui libri aritmetici "
        "e segnala i limiti filologici delle traduzioni ottocentesche."
    )
    assert is_residual_paratext_block("Nota bibliografica", reasoned_biblio) is False
    toc_dotted = "INDICE\nCapitolo I ................... 12\nCapitolo II .................. 24\nCapitolo III ................. 38\nCapitolo IV .................. 51\n"
    assert is_residual_paratext_block("Indice", toc_dotted) is True

    # 4. Filtro curriculum_mapper meno permissivo su parole generiche
    obj_terms = extract_objective_query_terms("Analisi economica classica delle teorie del valore assoluto")
    assert "economica" not in obj_terms
    assert "classica" not in obj_terms
    assert "teorie" not in obj_terms


def test_hygiene_cleanup_preserves_real_names_and_cleans_noise(tmp_path: Path) -> None:
    cleaned, changed = clean_actor_list(
        json.dumps(["sganciatore", "CEI", "Guglielmo Marconi", "Van der Waerden", "J.S. Bach", "vettori"])
    )
    assert changed is True
    assert cleaned == ["Guglielmo Marconi", "Van der Waerden", "J.S. Bach"]

    db_path = tmp_path / "hyg.db"
    conn = init_corpus_db(db_path)
    conn.execute(
        """
        INSERT INTO books (book_uid, title, author, year, surface_domain, source_kind, is_active)
        VALUES ('bk_1', '[Universale Bollati] Ludovico Ge…infinitesimale', NULL, 2008, 'storia_della_scienza', 'from_before', 1)
        """
    )
    bpk = conn.execute("SELECT book_pk FROM books WHERE book_uid='bk_1'").fetchone()[0]
    conn.execute(
        """
        INSERT INTO blocks (
            block_uid, book_pk, book_title, source_origin, page_start, page_end,
            section_title, content, norm_content, char_count, est_tokens, block_role, is_active
        ) VALUES (
            'blk_1', ?, 'Geymonat', 'from_before', 1, 1, 'Frontespizio',
            'Ludovico Geymonat\n\nStoria e filosofia dell’analisi infinitesimale\nBollati Boringhieri',
            'ludovico geymonat storia e filosofia dell analisi infinitesimale', 90, 20, 'body', 1
        )
        """,
        (bpk,),
    )
    blk_pk = conn.execute("SELECT block_pk FROM blocks WHERE block_uid='blk_1'").fetchone()[0]
    conn.execute(
        """
        INSERT INTO epistemic_units (unit_uid, block_pk, kind, mode, stmt, verbatim_quote, actors_json)
        VALUES ('u_1', ?, 'claim', 'narrates', 'Geymonat discute Proclo e E. du Bois-Reymond.', 'Ludovico Geymonat', ?)
        """,
        (blk_pk, json.dumps(["flogisto", "E. du Bois-Reymond", "Proclo", "vettori"])),
    )
    conn.commit()
    conn.close()

    rep_dry = run_hygiene_cleanup(db_path, apply=False)
    assert rep_dry.dry_run is True
    assert rep_dry.units_cleaned == 1
    assert rep_dry.books_author_updated == 1

    rep_apply = run_hygiene_cleanup(db_path, apply=True)
    assert rep_apply.dry_run is False
    assert rep_apply.units_cleaned == 1

    conn2 = sqlite3.connect(db_path)
    actors_after = json.loads(conn2.execute("SELECT actors_json FROM epistemic_units WHERE unit_uid='u_1'").fetchone()[0])
    author_after = conn2.execute("SELECT author FROM books WHERE book_uid='bk_1'").fetchone()[0]
    conn2.close()
    assert actors_after == ["E. du Bois-Reymond", "Proclo"]
    assert author_after == "Ludovico Geymonat"

    # Idempotenza: una seconda run non modifica nulla
    rep_again = run_hygiene_cleanup(db_path, apply=False)
    assert rep_again.units_cleaned == 0
    assert rep_again.books_author_updated == 0
