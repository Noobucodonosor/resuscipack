"""Test end-to-end per Tappa 1 (M1): BlockExtraction v2.2 universale a 22 macro-discipline,
normalizzazione citazioni tollerante agli OCR storici, riconciliazione kind/mode,
ingestione OCR append-only e packer multi-blocco + Batch JSONL."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Mapping

import pytest

from resuscipack.corpus.ocr_ingest import ingest_ocr_pages_append_only, parse_page_spec
from resuscipack.corpus.schema import init_corpus_db
from resuscipack.epistemic.batch_cli import (
    _parse_window_extractions_payload,
    export_multiblock_batch_jsonl,
    group_rows_into_book_windows,
    import_multiblock_batch_jsonl,
    run_batch_extraction,
)
from resuscipack.epistemic.schema_v21 import (
    ALL_MACRO_DISCIPLINES,
    BlockYield,
    MacroDiscipline,
    SchemaValidationError,
    UnitKind,
    UnitMode,
    persist_block_extraction,
    persist_v22_metadata_only,
    quote_matches_block_ocr_tolerant,
    validate_block_extraction,
)
from tests.test_epistemic_v21 import _insert_book_and_block


def test_v22_macro_disciplines_ocr_quote_tolerance_and_kind_mode_repair() -> None:
    assert len(ALL_MACRO_DISCIPLINES) == 22
    assert MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO.value in ALL_MACRO_DISCIPLINES

    block_text = (
        "Il panfilo Elettra mantenne la rotta lungo la costa della Cornovaglia verso Capo Lizard "
        "tra due boe ancorate a cinquanta metri l'una dall'altra nel mare mosso d'onda corta."
    )

    # 1. Tolleranza OCR reale (distanza <= 1 e spazio su apostrofo) vs citazione inventata
    assert quote_matches_block_ocr_tolerant(
        "ancorate a cinquanta metri l' una dall' altra nel mare",
        block_text,
    )
    assert quote_matches_block_ocr_tolerant(
        "a cinquanta metri l'una dali'altra nel mare mosso",
        block_text,
    )
    assert not quote_matches_block_ocr_tolerant(
        "questa frase del tutto inventata non compare mai nel testo",
        block_text,
    )

    # 2. Auto-riconciliazione quando il modello mette `narrates` dentro `kind`
    payload = {
        "yield": "high",
        "macro_disciplines": ["telecomunicazioni_segnali", "geografia_cartografia_territorio", "nautica_navigazione_meteo"],
        "topics": ["radiofaro direzionale", "navigazione costiera in Cornovaglia"],
        "places": ["Cornovaglia", "Capo Lizard"],
        "years": ["1934"],
        "units": [
            {
                "kind": "narrates",
                "mode": "",
                "stmt": "Il panfilo Elettra sperimenta il radiofaro lungo la costa della Cornovaglia verso Capo Lizard.",
                "quote": "la rotta lungo la costa della Cornovaglia verso Capo Lizard",
                "who": ["Guglielmo Marconi"],
                "vs": None,
                "concepts": ["radiofaro", "navigazione costiera"],
            }
        ],
        "sig": None,
    }
    ext = validate_block_extraction(payload, block_content=block_text, require_v22_metadata=True)
    assert ext.units[0].kind is UnitKind.CLAIM
    assert ext.units[0].mode is UnitMode.NARRATES
    assert tuple(d.value for d in ext.macro_disciplines) == (
        "telecomunicazioni_segnali",
        "geografia_cartografia_territorio",
        "nautica_navigazione_meteo",
    )

    # Citazione inventata continua a sollevare SchemaValidationError
    bad_payload = dict(payload)
    bad_payload["units"] = [{**payload["units"][0], "quote": "citazione falsa mai scritta nel libro"}]
    with pytest.raises(SchemaValidationError, match="non trovata verbatim"):
        validate_block_extraction(bad_payload, block_content=block_text, require_v22_metadata=True)

    # Macro-disciplina inventata viene rifiutata
    bad_disc = {**payload, "macro_disciplines": ["disciplina_inventata"]}
    with pytest.raises(SchemaValidationError, match="22 macro-discipline"):
        validate_block_extraction(bad_disc, block_content=block_text, require_v22_metadata=True)


def test_multiblock_packer_batch_jsonl_roundtrip_and_Selective_repair() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        db_path = tmp_dir / "corpus.db"
        conn = init_corpus_db(db_path)

        pks = []
        for idx in range(5):
            bpk, _ = _insert_book_and_block(
                conn,
                title="Euclide - Elementi (Libro I)",
                surface_domain="matematica",
                content=(
                    f"Proposizione {idx + 1}: Sopra un segmento rettilineo dato AB costruire un triangolo equilatero "
                    f"con apertura di compasso pari al raggio AB nel caso numero {idx + 1}."
                ),
                page=60 + idx,
            )
            pks.append(bpk)

        conn.close()

        # Test raggruppamento e dry-run estimate
        dry = run_batch_extraction(db_path, limit=10, dry_run=True, pack_size=5)
        assert dry["pending_blocks"] == 5
        assert dry["packed_v22_estimate"]["window_count"] == 1
        assert dry["packed_v22_estimate"]["pack_size"] == 5

        calls: list[int] = []

        def fake_multiblock_llm(prompt: str, rows_arg: Any) -> Mapping[str, Any]:
            assert isinstance(rows_arg, list)
            assert len(rows_arg) == 5
            calls.append(len(rows_arg))
            return {
                "extractions": [
                    {
                        "block_pk": int(r["block_pk"]),
                        "yield": "high",
                        "macro_disciplines": ["matematica", "logica"],
                        "topics": ["costruzione riga e compasso", "triangolo equilatero"],
                        "places": [],
                        "years": [],
                        "units": [
                            {
                                "kind": "proc",
                                "mode": "proves",
                                "stmt": f"Euclide dimostra nella proposizione {i + 1} come costruire un triangolo equilatero su AB.",
                                "quote": f"Sopra un segmento rettilineo dato AB costruire un triangolo equilatero",
                                "who": ["Euclide"],
                                "vs": None,
                                "concepts": ["triangolo equilatero", "compasso"],
                            }
                        ],
                        "sig": None,
                    }
                    for i, r in enumerate(rows_arg)
                ]
            }

        res = run_batch_extraction(
            db_path,
            limit=10,
            pack_size=5,
            require_v22_metadata=True,
            workers=1,
            llm_fn=fake_multiblock_llm,
        )
        assert calls == [5]
        assert res["windows_sent"] == 1
        assert res["blocks_processed"] == 5
        assert res["v22_metadata_written"] == 5

        # Verifica export + import Vertex Batch JSONL roundtrip su un nuovo libro
        conn2 = sqlite3.connect(str(db_path))
        conn2.row_factory = sqlite3.Row
        bpk_new, _ = _insert_book_and_block(
            conn2,
            title="Giancarlo Masini - Marconi Coste",
            surface_domain="storia_della_scienza",
            content="Dalla stazione di Poldhu in Cornovaglia i segnali raggiunsero Capo Cod superando l'Atlantico.",
            page=215,
        )
        conn2.commit()

        jsonl_in = tmp_dir / "batch_in.jsonl"
        exp = export_multiblock_batch_jsonl(conn2, jsonl_in, pack_size=5)
        assert exp["blocks_exported"] == 1
        assert exp["windows_exported"] == 1

        jsonl_out = tmp_dir / "batch_out.jsonl"
        pred_line = {
            "custom_id": f"win_000001_bk{bpk_new}",
            "response": {
                "usageMetadata": {"promptTokenCount": 420, "candidatesTokenCount": 140},
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "extractions": [
                                                {
                                                    "block_pk": bpk_new,
                                                    "yield": "high",
                                                    "macro_disciplines": [
                                                        "telecomunicazioni_segnali",
                                                        "geografia_cartografia_territorio",
                                                    ],
                                                    "topics": ["collegamento transatlantico", "stazione di Poldhu"],
                                                    "places": ["Poldhu", "Cornovaglia", "Capo Cod", "Atlantico"],
                                                    "years": [],
                                                    "units": [
                                                        {
                                                            "kind": "exp",
                                                            "mode": "applies",
                                                            "stmt": "I segnali radio da Poldhu in Cornovaglia attraversano l'Atlantico fino a Capo Cod.",
                                                            "quote": "i segnali raggiunsero Capo Cod superando l'Atlantico",
                                                            "who": ["Guglielmo Marconi"],
                                                            "vs": None,
                                                            "concepts": ["radiotelegrafia transoceanica"],
                                                        }
                                                    ],
                                                    "sig": None,
                                                }
                                            ]
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ],
            },
        }
        jsonl_out.write_text(json.dumps(pred_line) + "\n", encoding="utf-8")

        imp = import_multiblock_batch_jsonl(conn2, jsonl_out)
        assert imp["blocks_committed"] == 1
        assert imp["v22_written"] == 1
        assert imp["input_tokens"] == 420
        assert imp["output_tokens"] == 140

        meta_row = conn2.execute(
            "SELECT macro_disciplines_json, places_json FROM block_metadata_v22 WHERE block_pk = ?",
            (bpk_new,),
        ).fetchone()
        assert meta_row is not None
        assert "geografia_cartografia_territorio" in json.loads(meta_row["macro_disciplines_json"])
        assert "Cornovaglia" in json.loads(meta_row["places_json"])
        conn2.close()


def test_ocr_ingest_append_only_and_supersede_preserves_existing_block_pks() -> None:
    assert parse_page_spec("65-68,70,70", total_pages=100) == [65, 66, 67, 68, 70]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "ocr_test.db"
        conn = init_corpus_db(db_path)

        # Inseriamo prima un blocco legacy degradato dello stesso libro
        old_pk, _ = _insert_book_and_block(
            conn,
            title="Testo Sotto Estratto (UTET)",
            surface_domain="matematica",
            content="Cultura_in_Ita5 solo frammento parziale",
            page=1,
        )

        # Inseriamo le nuove pagine OCR con supersede_under_extracted=True
        res = ingest_ocr_pages_append_only(
            conn,
            title="Testo Sotto Estratto (UTET)",
            source_path="/readonly/dummy.pdf",
            source_kind="vertex_vision_ocr",
            total_pages=200,
            supersede_under_extracted=True,
            transcribed_pages=[
                {
                    "pdf_page": 10,
                    "printed_page": "8",
                    "section_title": "Libro I - Definizioni",
                    "block_role": "body",
                    "text": "Cultura_in_Ita5\n1. Punto è ciò che non ha parti.\n2. Linea è lunghezza senza larghezza.",
                },
                {
                    "pdf_page": 11,
                    "printed_page": "9",
                    "section_title": "Libro I - Postulati",
                    "block_role": "body",
                    "text": "Risulti postulato che da qualsiasi punto si possa condurre una retta ad ogni altro punto.",
                },
            ],
        )
        assert res["blocks_inserted"] == 2
        assert res["blocks_superseded"] == 1
        new_first_pk = res["inserted_block_pks"][0]

        # Il vecchio block_pk NON è stato cancellato, ma disattivato e collegato al nuovo blocco
        old_row = conn.execute(
            "SELECT is_active, superseded_by_pk FROM blocks WHERE block_pk = ?",
            (old_pk,),
        ).fetchone()
        assert old_row["is_active"] == 0
        assert old_row["superseded_by_pk"] == new_first_pk

        # La ricerca FTS5 trova il testo pulito di Euclide e non restituisce più il blocco disattivato
        fts_hits = conn.execute(
            "SELECT rowid FROM passages_fts WHERE passages_fts MATCH '\"lunghezza\" AND \"larghezza\"'"
        ).fetchall()
        assert [int(r[0]) for r in fts_hits] == [new_first_pk]
        conn.close()


def test_v22_latex_greek_short_ocr_ellipsis_places_and_compact_wire_backfill() -> None:
    euclid_block = (
        r"Discutibile se tradurre $\pi\epsilon\pi\epsilon\rho\alpha\sigma\mu\epsilon\nu\eta$ greco "
        "con limitata o terminata nei postulati geometrici.\n"
        "Nei giorni ro, 11, 12 e 13 luglio furono eseguite prove a terra a La Spezia.\n"
        "Procarioti ribosomi 70 S, contenenti il 65% di RNA e flagelli semplici senza membrana.\n"
        "Eucarioti ribosomi 80 S, contenenti il 55% di RNA e flagelli complessi (9+2)."
    )
    assert quote_matches_block_ocr_tolerant(
        "Discutibile se tradurre πεπερασμένη greco con limitata o terminata",
        euclid_block,
    )
    assert quote_matches_block_ocr_tolerant(
        "Nei giorni 10, 11, 12 e 13 luglio furono eseguite prove a terra",
        euclid_block,
    )
    assert quote_matches_block_ocr_tolerant(
        "ribosomi 70 S, contenenti il 65% di RNA [...] ribosomi 80 S, contenenti il 55% di RNA",
        euclid_block,
    )
    assert not quote_matches_block_ocr_tolerant(
        "ribosomi 70 S, contenenti il 65% di RNA [...] frase totalmente assente dal testo",
        euclid_block,
    )
    array_block = (
        r"Eubatteri \( \left\{\begin{array}{l}eterotrofi, chemioautotrofi o \\"
        r"fotosintetici senza produzione di O_{2}\\fotosintetici con produzione di O_{2}"
        r"\end{array}\right. \) — Bacteriophyta"
    )
    assert quote_matches_block_ocr_tolerant(
        "Eubatteri eterotrofi, chemioautotrofi o fotosintetici senza produzione di O2 fotosintetici con produzione",
        array_block,
    )

    twelve_places = [
        "Londra", "Poole", "Poldhu", "Cornovaglia", "La Panne", "Ostenda",
        "Dover", "Washington", "Cape Cod", "Cape Lizard", "La Spezia", "Roma",
    ]
    compact_wire = {
        "items": [
            {
                "b": 777,
                "y": "high",
                "d": ["geografia_cartografia_territorio", "telecomunicazioni_segnali"],
                "t": ["collegamenti costieri", "sperimentazione radio"],
                "p": twelve_places,
                "yr": ["1897", "1901"],
                "u": [
                    {
                        "k": "exp",
                        "m": "applies",
                        "st": "Marconi eseguì prove a terra a La Spezia nei giorni dall'undici al tredici luglio.",
                        "q": "Nei giorni 10, 11, 12 e 13 luglio furono eseguite prove a terra",
                        "w": ["Guglielmo Marconi"],
                        "v": None,
                        "c": ["radiotelegrafia", "prove a terra"],
                    }
                ],
                "s": None,
            }
        ]
    }
    parsed = _parse_window_extractions_payload(compact_wire)
    assert 777 in parsed
    ext = validate_block_extraction(parsed[777], block_content=euclid_block, require_v22_metadata=True)
    assert len(ext.places) == 12

    with tempfile.TemporaryDirectory() as tmp:
        conn = init_corpus_db(Path(tmp) / "meta_only.db")
        bpk, buid = _insert_book_and_block(
            conn,
            title="Giancarlo Masini - Guglielmo Marconi",
            surface_domain="storia_della_scienza",
            content=euclid_block,
            page=144,
        )
        base_ext = validate_block_extraction(
            {
                "yield": "high",
                "units": [parsed[777]["units"][0]],
                "sig": {
                    "op_tags": ["BOUNDED_TOLERANCE"],
                    "role": "embodied_intuition",
                    "mech": "Verifica sperimentale della ricezione progressiva lungo una serie discreta di stazioni costiere.",
                },
            },
            block_content=euclid_block,
            require_v22_metadata=False,
        )
        persist_block_extraction(conn, block_pk=bpk, block_uid=buid, extraction=base_ext)

        wrote = persist_v22_metadata_only(
            conn,
            block_pk=bpk,
            payload={
                "yield": "high",
                "macro_disciplines": ["geografia_cartografia_territorio", "telecomunicazioni_segnali"],
                "topics": ["stazioni costiere", "La Spezia"],
                "places": twelve_places,
                "years": ["1897"],
            },
        )
        assert wrote is True
        assert conn.execute("SELECT COUNT(*) FROM epistemic_units WHERE block_pk=?", (bpk,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM structural_signatures WHERE block_pk=?", (bpk,)).fetchone()[0] == 1
        meta_places = json.loads(
            conn.execute("SELECT places_json FROM block_metadata_v22 WHERE block_pk=?", (bpk,)).fetchone()[0]
        )
        assert len(meta_places) == 12
        conn.close()
