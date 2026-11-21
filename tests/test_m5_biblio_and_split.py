"""Test per Milestone M5 Fase 2: split 2-up OCR, schema `bibliographic_citations` ed estrattore fonti."""

from __future__ import annotations

from pathlib import Path

import pytest

from resuscipack.corpus.ocr_ingest import is_landscape_2up
from resuscipack.corpus.schema import init_corpus_db
from resuscipack.epistemic.biblio_extractor import (
    score_block_bibliographic_density,
    select_biblio_rich_blocks,
    validate_and_store_citations,
)


def test_is_landscape_2up_threshold() -> None:
    assert is_landscape_2up(837.0, 605.0) is True   # Geymonat 2-up
    assert is_landscape_2up(595.0, 842.0) is False  # A4 portrait


def test_bibliographic_density_and_anti_hallucination_storage(tmp_path: Path) -> None:
    db_path = tmp_path / "biblio.db"
    conn = init_corpus_db(db_path)
    conn.execute(
        """
        INSERT INTO books (book_uid, title, author, year, surface_domain, source_kind, is_active)
        VALUES ('bk_geym', 'Storia e filosofia dell analisi infinitesimale', 'Ludovico Geymonat', 2008, 'storia_della_scienza', 'from_before', 1),
               ('bk_eucl', 'Gli Elementi', 'Euclide', 1970, 'matematica', 'from_before', 1)
        """
    )
    geym_pk = conn.execute("SELECT book_pk FROM books WHERE book_uid='bk_geym'").fetchone()[0]
    eucl_pk = conn.execute("SELECT book_pk FROM books WHERE book_uid='bk_eucl'").fetchone()[0]

    block_text = (
        "Sguardo generale alla storia della matematica greca. "
        "Secondo Proclo, nel commento al primo libro di Euclide, la nostra fonte principale è il riassunto di Eudemo "
        "tramandato attraverso Gemino. Si veda anche Heath (1921) e l'edizione critica a cura di Frajese (1970)."
    )
    conn.execute(
        """
        INSERT INTO blocks (
            block_uid, book_pk, book_title, source_origin, page_start, page_end,
            section_title, content, norm_content, char_count, est_tokens, block_role, is_active
        ) VALUES (
            'blk_g1', ?, 'Geymonat', 'from_before', 1, 1,
            'Cap. 1 Sguardo generale', ?, ?, ?, 45, 'body', 1
        )
        """,
        (geym_pk, block_text, block_text.lower(), len(block_text)),
    )
    blk_pk = conn.execute("SELECT block_pk FROM blocks WHERE block_uid='blk_g1'").fetchone()[0]
    conn.commit()

    density = score_block_bibliographic_density("Cap. 1 Sguardo generale", block_text)
    assert density["is_biblio_rich"] is True
    assert density["score"] >= 4

    cands = select_biblio_rich_blocks(conn, book_pk=geym_pk, min_score=4)
    assert len(cands) == 1
    assert cands[0]["block_pk"] == blk_pk

    res = validate_and_store_citations(
        conn,
        source_block_pk=blk_pk,
        block_content=block_text,
        citations=[
            {
                "verbatim_quote": "la nostra fonte principale è il riassunto di Eudemo",
                "cited_author": "Eudemo",
                "cited_work": "Storia della geometria",
                "cited_year": "IV sec. a.C.",
                "source_layer": "commentator_transmission",
                "stance": "transmits_from",
                "appraisal_note": "Geymonat segnala che la conoscenza passa tramite Proclo e Gemino.",
                "transmission_from": "Proclo -> Gemino -> Eudemo",
            },
            {
                "verbatim_quote": "l'edizione critica a cura di Frajese (1970)",
                "cited_author": "Euclide",
                "cited_work": "Elementi",
                "cited_year": "1970",
                "source_layer": "critical_edition",
                "stance": "recommends",
                "appraisal_note": "Edizione italiana di riferimento curata da Attilio Frajese.",
            },
            {
                "verbatim_quote": "frase inventata inesistente nel testo",
                "cited_author": "Fake",
                "cited_work": "Opera Falsa",
                "source_layer": "primary_ancient",
                "stance": "uses_as_source",
                "appraisal_note": "Deve essere scartata dal gate anti-allucinazione.",
            },
        ],
    )
    assert res["inserted"] == 2
    assert len(res["rejected"]) == 1

    rows = conn.execute("SELECT cited_author, resolved_book_pk FROM bibliographic_citations ORDER BY citation_pk").fetchall()
    assert rows[0]["cited_author"] == "Eudemo"
    assert rows[0]["resolved_book_pk"] is None  # Wishlist Epistemica
    assert rows[1]["cited_author"] == "Euclide"
    assert rows[1]["resolved_book_pk"] == eucl_pk  # Presente in casa
    conn.close()
