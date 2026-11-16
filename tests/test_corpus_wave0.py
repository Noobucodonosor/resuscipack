"""Suite di test completa per `resuscipack.corpus` (ADR-0001: TASK-CORPUS-01..03).
- Tutti i test di mutazione girano esclusivamente in `tempfile.TemporaryDirectory()`.
- Tutte le asserzioni sul DB reale `data/pack_corpus.db` aprono SQLite in sola lettura (`mode=ro`)."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile

import pytest

from resuscipack.corpus import (
    DEFAULT_DB_PATH,
    classify_block_role,
    clean_ocr_markdown,
    connect_corpus_db,
    init_corpus_db,
    make_block_uid,
    make_book_uid,
    normalize_for_match,
    supersede_block,
)
from resuscipack.corpus.ocr_manifest import DEFAULT_OCR_MANIFEST_OUT
from resuscipack.corpus.wave0_ingest import (
    DEFAULT_MIGRATION_JSON,
    build_merged_markdown_volume_blocks,
    extract_epub_blocks,
)


def test_schema_append_only_and_fts_triggers() -> None:
    """Verifica le 7 tabelle canoniche, l'immutabilità `block_pk` (no DELETE) e i trigger FTS5."""
    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "test_corpus.db"
        conn = init_corpus_db(db_file)

        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        expected_tables = {
            "books",
            "blocks",
            "passages_fts",
            "epistemic_units",
            "structural_signatures",
            "curiosity_bridges",
            "legacy_rowid_map",
        }
        assert expected_tables.issubset(tables)

        bk_uid = make_book_uid("Test Volume", "from_before")
        cur = conn.execute(
            """
            INSERT INTO books(book_uid, title, surface_domain, source_kind, is_active)
            VALUES (?, ?, 'fisica_ingegneria', 'from_before', 1)
            """,
            (bk_uid, "Test Volume"),
        )
        book_pk = int(cur.lastrowid)

        txt_v1 = "Testo sporco iniziale con errore OCR sulla parabola focale."
        norm_v1 = normalize_for_match(txt_v1)
        uid_v1 = make_block_uid(bk_uid, 10, 10, norm_v1)
        c1 = conn.execute(
            """
            INSERT INTO blocks(
                block_uid, book_pk, book_title, is_active, block_role,
                page_start, page_end, section_title, content, norm_content,
                char_count, est_tokens, source_origin
            ) VALUES (?, ?, 'Test Volume', 1, 'body', 10, 10, 'Cap 1', ?, ?, ?, 15, 'from_before')
            """,
            (uid_v1, book_pk, txt_v1, norm_v1, len(txt_v1)),
        )
        pk_v1 = int(c1.lastrowid)

        # Verifica che il trigger AFTER INSERT abbia indicizzato pk_v1 con rowid == block_pk
        fts_hits = conn.execute(
            "SELECT rowid FROM passages_fts WHERE passages_fts MATCH 'parabola'"
        ).fetchall()
        assert [r["rowid"] for r in fts_hits] == [pk_v1]

        # Verifica che DELETE fisico su blocks sia vietato
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM blocks WHERE block_pk = ?", (pk_v1,))

        # Inserimento nuova versione OCR migliorata (append-only -> nuovo block_pk)
        txt_v2 = "Testo pulito Baidu OCR sul riflettore parabolico di Santa Margherita."
        norm_v2 = normalize_for_match(txt_v2)
        uid_v2 = make_block_uid(bk_uid, 10, 10, norm_v2)
        c2 = conn.execute(
            """
            INSERT INTO blocks(
                block_uid, book_pk, book_title, is_active, block_role,
                page_start, page_end, section_title, content, norm_content,
                char_count, est_tokens, source_origin
            ) VALUES (?, ?, 'Test Volume', 1, 'body', 10, 10, 'Cap 1', ?, ?, ?, 18, 'from_baidu_ocr')
            """,
            (uid_v2, book_pk, txt_v2, norm_v2, len(txt_v2)),
        )
        pk_v2 = int(c2.lastrowid)
        assert pk_v2 > pk_v1

        supersede_block(conn, pk_v1, pk_v2)
        conn.commit()

        # Il blocco storico pk_v1 resta leggibile per citazioni pregresse, ma esce da FTS5 attivo
        old_row = conn.execute("SELECT * FROM blocks WHERE block_pk = ?", (pk_v1,)).fetchone()
        assert old_row is not None
        assert old_row["is_active"] == 0
        assert old_row["superseded_by_pk"] == pk_v2

        assert (
            conn.execute(
                "SELECT rowid FROM passages_fts WHERE passages_fts MATCH 'sporco'"
            ).fetchall()
            == []
        )
        active_hits = conn.execute(
            "SELECT rowid FROM passages_fts WHERE passages_fts MATCH 'riflettore'"
        ).fetchall()
        assert [r["rowid"] for r in active_hits] == [pk_v2]
        conn.close()


def test_normalizer_splicing_and_epub_in_tempdir() -> None:
    """Testa pulizia `Cultura_in_Ita5`, page-level splicing Baidu, parser EPUB e filtro paratesto."""
    dirty = (
        "<|det|>text [[10, 20, 300, 400]]<|/det|>La dimostra-\nzione procede per assurdo.\n"
        "www.scribd.com/Cultura_in_Ita5\n"
        "<|det|>image [[0,0,10,10]]<|/det|>figura\n"
    )
    cleaned = clean_ocr_markdown(dirty)
    assert cleaned == "La dimostrazione procede per assurdo."
    assert "Cultura_in_Ita5" not in cleaned

    toc_text = "\n".join(
        [
            "Capitolo 1 ........................ 12",
            "Capitolo 2 ........................ 45",
            "Capitolo 3 ........................ 88",
            "Indice analitico .................. 210",
        ]
    )
    assert classify_block_role(toc_text, "Indice") == "paratext"
    assert (
        classify_block_role(
            "Ogni insieme finito equipotente a una sua parte propria genera una contraddizione.",
            "Capitolo 1",
        )
        == "body"
    )

    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        before_md = tdir / "LibroIbrido.md"
        before_md.write_text(
            "<!-- Pagina 1 -->\n"
            + ("Testo valido della pagina uno proveniente da estrazione precedente. " * 30)
            + "\n<!-- Pagina 2 -->\nwww.scribd.com/Cultura_in_Ita5\n"
            + "<!-- Pagina 3 -->\n"
            + ("Testo valido della pagina tre con conclusioni matematiche chiare. " * 30),
            encoding="utf-8",
        )
        baidu_dir = tdir / "LibroIbrido_baidu"
        (baidu_dir / "pages").mkdir(parents=True)
        (baidu_dir / "pages" / "page_0002.md").write_text(
            "# Sezione Due\n"
            + ("Pagina due interamente recuperata tramite Baidu Unlimited OCR con formule esatte. " * 4),
            encoding="utf-8",
        )

        blocks, kind, _, spliced_cnt = build_merged_markdown_volume_blocks(before_md, baidu_dir)
        assert kind == "hybrid_baidu_spliced"
        assert spliced_cnt == 1
        assert [b["page_start"] for b in blocks] == [1, 2, 3]
        assert blocks[1]["source_origin"] == "from_baidu_spliced"
        assert "Baidu Unlimited OCR" in blocks[1]["content"]

        # Test sintetico EPUB con container.xml + content.opf + capitolo XHTML
        epub_path = tdir / "ManualeTest.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?>'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
                "</container>",
            )
            zf.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0" encoding="utf-8"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
                '<manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                '<spine><itemref idref="c1"/></spine>'
                "</package>",
            )
            zf.writestr(
                "OEBPS/ch1.xhtml",
                "<html><body><h1>Crittografia Hash</h1>"
                "<p>Una funzione crittografica SHA-256 mappa un messaggio arbitrario in un digest fisso di 256 bit "
                "rendendo computazionalmente infattibile invertire la preimmagine.</p></body></html>",
            )
        ep_blocks = extract_epub_blocks(epub_path)
        assert len(ep_blocks) == 1
        assert ep_blocks[0]["section_title"] == "Crittografia Hash"
        assert "SHA-256" in ep_blocks[0]["content"]


def test_wave0_real_db_counts_and_buchi_closed() -> None:
    """Verifica in sola lettura (`mode=ro`) i numeri reali del DB generato da Wave 0."""
    assert DEFAULT_DB_PATH.exists(), "pack_corpus.db mancante: eseguire wave0_ingest.py"
    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)

    active_books = conn.execute("SELECT COUNT(*) AS n FROM books WHERE is_active = 1").fetchone()["n"]
    epub_books = conn.execute(
        "SELECT COUNT(*) AS n FROM books WHERE source_kind = 'epub' AND is_active = 1"
    ).fetchone()["n"]
    spliced_books = conn.execute(
        "SELECT COUNT(*) AS n FROM books WHERE source_kind = 'hybrid_baidu_spliced' AND is_active = 1"
    ).fetchone()["n"]
    spliced_pages = conn.execute(
        "SELECT COUNT(*) AS n FROM blocks WHERE source_origin = 'from_baidu_spliced' AND is_active = 1"
    ).fetchone()["n"]
    total_baidu_blocks = conn.execute(
        "SELECT COUNT(*) AS n FROM blocks WHERE source_origin IN ('from_baidu_ocr', 'from_baidu_spliced') AND is_active = 1"
    ).fetchone()["n"]
    active_blocks = conn.execute("SELECT COUNT(*) AS n FROM blocks WHERE is_active = 1").fetchone()["n"]
    fts_rows = conn.execute("SELECT COUNT(*) AS n FROM passages_fts").fetchone()["n"]
    paratext_blocks = conn.execute(
        "SELECT COUNT(*) AS n FROM blocks WHERE block_role = 'paratext' AND is_active = 1"
    ).fetchone()["n"]

    assert active_books >= 1350
    assert epub_books == 32, f"Attesi tutti i 32 EPUB, trovati {epub_books}"
    assert spliced_books >= 100, f"Attesi >=100 libri ibridi ricuciti, trovati {spliced_books}"
    assert spliced_pages >= 1800, f"Attese >=1800 pagine Baidu non vuote ricucite, trovate {spliced_pages}"
    assert total_baidu_blocks >= 7750, f"Attesi >=7750 blocchi Baidu puliti, trovati {total_baidu_blocks}"
    assert active_blocks == fts_rows, "Disallineamento tra blocks attivi e passages_fts"
    assert paratext_blocks >= 180, "Il pre-filtro deterministico del paratesto non ha classificato indici/TOC"

    # Verifica presenza volumi dove Baidu aveva solo pagine vuote ma from_before aveva il testo pieno
    for must_title in ("Sheldon M. Ross", "Enrico Fermi"):
        cnt = conn.execute(
            "SELECT COUNT(*) AS n FROM books WHERE title LIKE ? AND is_active = 1",
            (f"%{must_title}%",),
        ).fetchone()["n"]
        assert cnt >= 1, f"Volume {must_title!r} assente da books"

    # Nessun manuale ASUS multilingua né duplicato .split('.')[0] presente
    noise_check = conn.execute(
        "SELECT COUNT(*) AS n FROM books WHERE LOWER(title) IN ('0402', '0404', '0c0a', 'sheldon m')"
    ).fetchone()["n"]
    assert noise_check == 0
    conn.close()


def test_wave0_marconi_galvani_cartesio_verbatim() -> None:
    """Verifica in `mode=ro` i 3 casi empirici 'Libro Sbagliato' (Marconi, Galvani, Cartesio)."""
    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)

    cases = [
        (
            "Santa Margherita",
            "L’esperimento ebbe luogo il 30 giugno 1934 nel mare di Santa Margherita Ligure.",
            "storia_della_scienza",
        ),
        (
            "boe di traguardo",
            "due boe di traguardo, poste a cinquanta metri l’una dall’altra.",
            "storia_della_scienza",
        ),
        (
            "riflettore parabolico",
            "presso il fuoco di un riflettore parabolico avente l'apertura di due metri",
            "storia_della_scienza",
        ),
        (
            "catena elettrica",
            "si formasse come una specie di catena elettrica",
            "medicina_biologia",
        ),
        (
            "scrittura velata",
            "leggere una scrittura velata dai caratteri sconosciuti",
            "filosofia_scienze_umane",
        ),
    ]

    for fts_term, exact_quote, expected_domain in cases:
        norm_q = normalize_for_match(exact_quote)
        rows = conn.execute(
            """
            SELECT bl.block_pk, bl.block_uid, bl.norm_content, bk.title, bk.surface_domain
            FROM passages_fts f
            JOIN blocks bl ON bl.block_pk = f.rowid
            JOIN books bk ON bk.book_pk = bl.book_pk
            WHERE passages_fts MATCH ?
            """,
            (f'"{fts_term}"',),
        ).fetchall()
        matched = [r for r in rows if norm_q in r["norm_content"]]
        assert matched, f"Citazione verbatim non trovata per {exact_quote!r}"
        assert matched[0]["surface_domain"] == expected_domain
        assert matched[0]["surface_domain"] not in ("matematica", "informatica")
        assert matched[0]["block_uid"].startswith("blk_")

    conn.close()


def test_wave0_legacy_card_migration_100pct() -> None:
    """Verifica che tutti i 17 vecchi `rowid` delle 6 schede elementari siano migrati con match verbatim."""
    assert DEFAULT_MIGRATION_JSON.exists(), "legacy_card_migration.json mancante"
    mig = json.loads(DEFAULT_MIGRATION_JSON.read_text(encoding="utf-8"))
    assert mig["total_cards_inspected"] == 6
    assert mig["unique_legacy_rowids_mapped"] == 17
    assert "numeri.quantita" in mig["cards"]
    assert len(mig["cards"]["numeri.quantita"]) == 7

    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    db_map_cnt = conn.execute("SELECT COUNT(*) AS n FROM legacy_rowid_map").fetchone()["n"]
    assert db_map_cnt == 17

    for card_id, entries in mig["cards"].items():
        for item in entries:
            row = conn.execute(
                "SELECT block_uid, norm_content, is_active FROM blocks WHERE block_pk = ?",
                (item["block_pk"],),
            ).fetchone()
            assert row is not None, f"block_pk {item['block_pk']} mancante per {card_id}"
            assert row["is_active"] == 1
            assert row["block_uid"] == item["block_uid"]
            assert normalize_for_match(item["citazione"]) in row["norm_content"]
    conn.close()


def test_manifest_waves_and_cultura_in_ita5() -> None:
    """Verifica `data/ocr_wave_manifest.json` per Euclide, Galileo, Archimede, Apostol e i 7 DjVu."""
    assert DEFAULT_OCR_MANIFEST_OUT.exists(), "ocr_wave_manifest.json mancante"
    manifest = json.loads(DEFAULT_OCR_MANIFEST_OUT.read_text(encoding="utf-8"))

    assert set(manifest["waves"].keys()) == {"wave_1", "wave_2", "wave_3", "wave_4"}
    assert manifest["total_pages_needing_ocr"] >= 15000
    assert manifest["by_defect_category"]["buco_d_djvu"]["documents"] == 7

    w1_titles = " | ".join(d["title"].lower() for d in manifest["waves"]["wave_1"]["documents"])
    for must_have in ("euclide", "galileo galilei", "archimede", "apostol", "principi matematici", "ben-ari"):
        assert must_have in w1_titles, f"Volume canonico {must_have!r} assente da wave_1"

    all_titles = " | ".join(
        d["title"].lower()
        for w in manifest["waves"].values()
        for d in w["documents"]
    )
    assert "geymonat" not in all_titles, "Geymonat è già estratto col titolo '…' e non va ri-OCRizzato"
