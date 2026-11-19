"""Test suite completa per Spettro Disciplinare Percentuale (`TASK-SPEC-01`)
e Ricostruzione delle Discipline dal Basso (`TASK-SPEC-02`, ADR-0004).

I test sintetici operano esclusivamente dentro `tempfile.TemporaryDirectory()`.
I test sul corpus reale usano `connect_corpus_db(..., read_only=True)`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, Sequence, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resuscipack.corpus.normalizer import make_block_uid, make_book_uid, normalize_for_match
from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db
from resuscipack.epistemic import (
    ALL_MACRO_DISCIPLINES,
    MACRO_DISCIPLINE_LABELS_IT,
    MacroDiscipline,
    classify_book_quality_tier,
    compute_all_book_spectra,
    get_book_spectrum,
    is_residual_paratext_block,
    list_books_by_discipline,
    persist_block_extraction,
    reconstruct_discipline,
    resolve_macro_discipline,
    validate_block_extraction,
)


def _seed_book_block_v22(
    conn: sqlite3.Connection,
    *,
    title: str,
    surface_domain: str,
    content: str,
    macro_disciplines: Sequence[str],
    topics: Sequence[str],
    places: Sequence[str],
    years: Sequence[str] = (),
    page: int = 1,
    role: str = "body",
    section_title: str = "Capitolo 1",
    with_unit: bool = True,
    quote: str | None = None,
    stmt: str | None = None,
) -> Tuple[int, int]:
    bk_uid = make_book_uid(title, "test")
    conn.execute(
        """
        INSERT OR IGNORE INTO books (
            book_uid, title, author, year, surface_domain, language, source_kind, page_count, is_active
        ) VALUES (?, ?, 'Autore Test', 1975, ?, 'it', 'test', 300, 1)
        """,
        (bk_uid, title, surface_domain),
    )
    book_pk = int(conn.execute("SELECT book_pk FROM books WHERE book_uid = ?", (bk_uid,)).fetchone()[0])

    norm_c = normalize_for_match(content)
    blk_uid = make_block_uid(bk_uid, page, page, norm_c)
    cur = conn.execute(
        """
        INSERT INTO blocks (
            block_uid, book_pk, book_title, is_active, block_role, page_start, page_end,
            printed_page, section_title, content, norm_content, char_count, est_tokens, source_origin
        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'test')
        """,
        (
            blk_uid,
            book_pk,
            title,
            role,
            page,
            page,
            str(page),
            section_title,
            content,
            norm_c,
            len(content),
            max(1, len(content) // 4),
        ),
    )
    block_pk = int(cur.lastrowid)

    units = []
    if with_unit:
        used_quote = quote or content[:90].strip()
        used_stmt = stmt or f"L'autore espone nella pagina {page} un passaggio verificato su {topics[0] if topics else 'argomento'}."
        units = [
            {
                "kind": "exp",
                "mode": "narrates",
                "stmt": used_stmt,
                "quote": used_quote,
                "who": ["Autore Test"],
                "vs": None,
                "concepts": list(topics[:2]) or ["concetto"],
            }
        ]

    payload = {
        "yield": "high",
        "macro_disciplines": list(macro_disciplines),
        "topics": list(topics),
        "places": list(places),
        "years": list(years),
        "units": units,
        "sig": None,
    }
    if with_unit:
        ext = validate_block_extraction(payload, block_content=content, require_v22_metadata=True)
        persist_block_extraction(conn, block_pk=block_pk, block_uid=blk_uid, extraction=ext)
    else:
        conn.execute(
            """
            INSERT INTO block_metadata_v22 (
                block_pk, macro_disciplines_json, emergent_topics_json,
                places_json, historical_years_json, schema_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'block-extraction.v2.2', datetime('now'))
            """,
            (
                block_pk,
                json.dumps(list(macro_disciplines), ensure_ascii=False),
                json.dumps(list(topics), ensure_ascii=False),
                json.dumps(list(places), ensure_ascii=False),
                json.dumps(list(years), ensure_ascii=False),
            ),
        )
    conn.commit()
    return book_pk, block_pk


def test_resolve_macro_discipline_aliases_and_errors() -> None:
    assert len(MACRO_DISCIPLINE_LABELS_IT) == len(ALL_MACRO_DISCIPLINES) == 22

    for canon in ALL_MACRO_DISCIPLINES:
        assert resolve_macro_discipline(canon).value == canon

    assert resolve_macro_discipline("geografia_territorio") is MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO
    assert resolve_macro_discipline("Geografia e Territorio") is MacroDiscipline.GEOGRAFIA_CARTOGRAFIA_TERRITORIO
    assert resolve_macro_discipline("nautica_mare") is MacroDiscipline.NAUTICA_NAVIGAZIONE_METEO
    assert resolve_macro_discipline("economia") is MacroDiscipline.ECONOMIA_COMMERCIO_ASSICURAZIONI
    assert resolve_macro_discipline("medicina_biologia") is MacroDiscipline.BIOLOGIA_FISIOLOGIA_MEDICINA
    assert resolve_macro_discipline("telecomunicazioni_elettronica") is MacroDiscipline.TELECOMUNICAZIONI_SEGNALI
    assert resolve_macro_discipline("Musica e Acustica") is MacroDiscipline.MUSICA_ACUSTICA

    with pytest.raises(ValueError, match="sconosciuta"):
        resolve_macro_discipline("disciplina_che_non_esiste_xyz")
    with pytest.raises(ValueError, match="vuota"):
        resolve_macro_discipline("   ")


def test_classify_book_quality_tier_precision() -> None:
    noise_titles = [
        "PRIMIGI",
        "PRIMIGI AI 15  AL 12.10",
        "disponibilitaPE2018",
        "Disponibilità Primigi PE 18 al 06.03.18",
        "S18 MISS SIXTY DISPONIBILITA' €",
        "CV-Daniele Bertuccio",
        "cv english",
        "bando_selezione_corsisti_2016_ict",
        "barbara - 52_brochure_4_percorso_its",
        "triax_catalogo-ita_2016",
        "Layout 1 (2)",
        "tavola programmazione FISICA I biennio I periodo 2017-18",
    ]
    for title in noise_titles:
        tier, reason = classify_book_quality_tier(
            title, active_blocks_count=10, v22_blocks_count=8, total_v22_chars=12000
        )
        assert tier == "non_book_noise", f"{title!r} classificato come {tier} ({reason})"

    ref_tier, _ = classify_book_quality_tier(
        "fullrefman", active_blocks_count=3606, v22_blocks_count=3333, total_v22_chars=8_500_000
    )
    assert ref_tier == "reference_manual"

    notes_tier, reason_notes = classify_book_quality_tier(
        "Beethoven - Sinfonia 7", active_blocks_count=20, v22_blocks_count=0, total_v22_chars=0
    )
    assert notes_tier == "didactic_notes"
    assert reason_notes == "zero_substantive_v22_blocks"

    real_titles = [
        "Giancarlo Masini - Guglielmo Marconi (1975, UTET) - libgen.lc",
        "Euclide, a cura di Attilio Frajese e Lamberto Maccioni - Elementi",
        "Galileo Galilei - Opere Vol. 1(1964, UTET) - libgen.lc",
        "scuola di scienze umanistiche-Water management and land use in the terramare and a po",
        "Il pendolo di Foucault - Umberto Eco",
        "Tom Apostol - Calcolo - Analisi 1. 1-Bollati Boringhieri (1987)",
    ]
    for title in real_titles:
        tier, reason = classify_book_quality_tier(
            title, active_blocks_count=100, v22_blocks_count=90, total_v22_chars=200000
        )
        assert tier == "canonical_book", f"{title!r} classificato erroneamente come {tier} ({reason})"


def test_compute_book_spectrum_exact_math_and_no_truncation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "spectrum_test.db"
        conn = init_corpus_db(db_path)

        # Libro con 35 blocchi multi-disciplina di lunghezze disuguali (200 char fisica pura vs 600 char fisica+geografia)
        book_pk = -1
        expected_pks_fisica: list[int] = []
        expected_pks_geo: list[int] = []
        total_chars = 0
        raw_fisica = 0.0
        raw_geo = 0.0
        cov_fisica = 0
        cov_geo = 0

        for idx in range(35):
            if idx % 2 == 0:
                discs = ["fisica"]
                base = f"Blocco sperimentale {idx:02d} sulle leggi della dinamica nei corpi rigidi."
                text = (base + " " * 10 + "Misure in laboratorio con oscillatore armonico.")[:195]
                text = text.ljust(200, ".")
            else:
                discs = ["fisica", "geografia_cartografia_territorio"]
                base = (
                    f"Spedizione sperimentale {idx:02d} tra la Cornovaglia, Capo Lizard e il Mediterraneo "
                    f"per misurare la propagazione delle onde elettromagnetiche oltre la curvatura terrestre."
                )
                text = base.ljust(600, "x")
                # Accorciamo appena con testo naturale valido senza puntini
                text = (base + " " + ("rilievo costiero e misure radio " * 15))[:600]

            book_pk, blk_pk = _seed_book_block_v22(
                conn,
                title="Trattato Sperimentale Sintetico",
                surface_domain="fisica_ingegneria",
                content=text,
                macro_disciplines=discs,
                topics=["propagazione", "costa"] if len(discs) > 1 else ["dinamica"],
                places=["Cornovaglia", "Capo Lizard"] if len(discs) > 1 else [],
                page=idx + 1,
                quote=base[:75],
            )
            w = len(text)
            total_chars += w
            expected_pks_fisica.append(blk_pk)
            cov_fisica += w
            raw_fisica += w / len(discs)
            if "geografia_cartografia_territorio" in discs:
                expected_pks_geo.append(blk_pk)
                cov_geo += w
                raw_geo += w / len(discs)

        summary1 = compute_all_book_spectra(conn)
        summary2 = compute_all_book_spectra(conn)  # idempotenza

        assert summary1["books_with_spectrum"] == 1
        assert summary2["books_with_spectrum"] == 1
        assert summary1["max_share_sum_deviation"] <= 0.01

        spec = get_book_spectrum(conn, book_pk)
        assert spec is not None
        assert spec["quality_tier"] == "canonical_book"
        assert spec["v22_blocks_count"] == 35
        assert 99.9 <= spec["share_sum_pct"] <= 100.1

        by_disc: Dict[str, dict] = {d["macro_discipline"]: d for d in spec["disciplines"]}
        assert len(by_disc["fisica"]["block_pks"]) == by_disc["fisica"]["block_count"] == 35
        assert by_disc["fisica"]["block_pks"] == expected_pks_fisica
        assert by_disc["geografia_cartografia_territorio"]["block_pks"] == expected_pks_geo
        assert len(by_disc["geografia_cartografia_territorio"]["block_pks"]) == 17

        expected_cov_geo = round(100.0 * cov_geo / total_chars, 2)
        expected_share_geo = round(100.0 * raw_geo / total_chars, 2)
        expected_share_fis = round(100.0 * raw_fisica / total_chars, 2)

        assert by_disc["fisica"]["coverage_pct"] == 100.0
        assert abs(by_disc["fisica"]["share_pct"] - expected_share_fis) <= 0.02
        assert by_disc["geografia_cartografia_territorio"]["coverage_pct"] == expected_cov_geo
        assert abs(by_disc["geografia_cartografia_territorio"]["share_pct"] - expected_share_geo) <= 0.02

        listed = list_books_by_discipline(conn, "geografia_territorio")
        assert len(listed) == 1 and listed[0]["book_pk"] == book_pk
        assert len(listed[0]["block_pks"]) == 17
        conn.close()


def test_discipline_reconstructor_synthetic_wrong_book_filtering() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "recon_synth.db"
        conn = init_corpus_db(db_path)

        # 1. Libro di Fisica con 3 passaggi di Geografia + 1 blocco Sommario residuo (da filtrare!)
        fisica_pk = -1
        for page, quote in [
            (12, "Le stazioni radiotelegrafiche di Poldhu in Cornovaglia e Glace Bay in Nuova Scozia"),
            (48, "Il piroscafo Carlo Alberto costeggiava la Penisola Iberica davanti a Gibilterra"),
            (91, "Le antenne lungo il promontorio di Capo Lizard guardano l'Atlantico settentrionale"),
        ]:
            content = (quote + ". Esperimenti fisici sulla diffrazione delle onde lunghe sul profilo montuoso e marino. " * 4)
            fisica_pk, _ = _seed_book_block_v22(
                conn,
                title="Storia sperimentale della radiofonia transoceanica",
                surface_domain="fisica_ingegneria",
                content=content,
                macro_disciplines=["fisica", "geografia_cartografia_territorio"],
                topics=["propagazione oltre l'orizzonte", "stazioni costiere"],
                places=["Cornovaglia", "Gibilterra", "Capo Lizard"],
                page=page,
                quote=quote,
                stmt=f"Analisi fisica e geografica condotta a pagina {page} lungo coste e stretti.",
            )
        # Blocco puramente fisico per rendere fisica la disciplina primaria (Share > 50%)
        for page in range(100, 108):
            _seed_book_block_v22(
                conn,
                title="Storia sperimentale della radiofonia transoceanica",
                surface_domain="fisica_ingegneria",
                content=("Calcolo del circuito risonante LC con induttanza e capacità variabile in laboratorio. " * 6),
                macro_disciplines=["fisica"],
                topics=["circuito risonante"],
                places=[],
                page=page,
                quote="Calcolo del circuito risonante LC con induttanza e capacità variabile in laboratorio",
            )
        # Blocco Sommario residuo etichettato per errore con geografia
        _seed_book_block_v22(
            conn,
            title="Storia sperimentale della radiofonia transoceanica",
            surface_domain="fisica_ingegneria",
            content="## Pagina 5\n\nSommario\n\nCapitolo 1 ... 12\nCapitolo 2 ... 48\n" + ("Riferimenti vari di impaginazione. " * 8),
            macro_disciplines=["fisica", "geografia_cartografia_territorio"],
            topics=["sommario"],
            places=["Londra"],
            page=5,
            section_title="Sommario",
            quote="Capitolo 1 ... 12",
        )
        assert is_residual_paratext_block("Sommario", "## Pagina 5\n\nSommario\n")

        # 2. Libro di Storia (altro "Libro Sbagliato" valido) con 2 passaggi geografici
        storia_pk = -1
        for page, quote in [
            (22, "Le rotte commerciali veneziane attraversavano il Mar Egeo fino al Mar Nero"),
            (55, "La fondazione di Genova e Pisa modificò gli equilibri del Tirreno"),
        ]:
            content = (quote + ". Documenti storici sui porti medievali e sulle carte nautiche portolaniche. " * 4)
            storia_pk, _ = _seed_book_block_v22(
                conn,
                title="Cronache del Mediterraneo medievale",
                surface_domain="storia_della_scienza",
                content=content,
                macro_disciplines=["storia_politica_militare", "geografia_cartografia_territorio"],
                topics=["portolani", "rotte commerciali"],
                places=["Venezia", "Genova", "Mar Egeo"],
                page=page,
                quote=quote,
            )
        for page in range(70, 75):
            _seed_book_block_v22(
                conn,
                title="Cronache del Mediterraneo medievale",
                surface_domain="storia_della_scienza",
                content=("Trattati diplomatici e cronologia delle assemblee comunali nel Duecento italiano. " * 6),
                macro_disciplines=["storia_politica_militare"],
                topics=["diplomazia comunale"],
                places=[],
                page=page,
                quote="Trattati diplomatici e cronologia delle assemblee comunali",
            )

        # 3. Libro classificato `miscellanea_tecnica`, ma primariamente GEOGRAFIA (deve essere ESCLUSO!)
        geo_native_pk = -1
        for page in range(1, 5):
            q = f"Atlante morfologico dei bacini idrografici e delle coste appenniniche nella tavola {page}"
            geo_native_pk, _ = _seed_book_block_v22(
                conn,
                title="Trattato di geomorfologia regionale",
                surface_domain="miscellanea_tecnica",
                content=(q + ". Descrizione sistematica dei versanti, dei fiumi e della cartografia nazionale. " * 5),
                macro_disciplines=["geografia_cartografia_territorio"],
                topics=["geomorfologia"],
                places=["Appennini", "Po"],
                page=page,
                quote=q,
            )

        # 4. Rumore commerciale `PRIMIGI` con blocchi geografici (deve essere ESCLUSO!)
        noise_pk = -1
        for page in range(1, 4):
            q = f"Magazzini distribuzione calzature Italia Francia Spagna Germania listino {page}"
            noise_pk, _ = _seed_book_block_v22(
                conn,
                title="PRIMIGI",
                surface_domain="miscellanea_tecnica",
                content=(q + ". Disponibilità stagionale taglie per negozi e distributori esteri e nazionali. " * 4),
                macro_disciplines=["economia_commercio_assicurazioni", "geografia_cartografia_territorio"],
                topics=["distribuzione"],
                places=["Italia", "Francia"],
                page=page,
                quote=q,
            )

        compute_all_book_spectra(conn)
        report = reconstruct_discipline(conn, "geografia_territorio")

        returned_pks = {b.book_pk for b in report.books}
        assert returned_pks == {fisica_pk, storia_pk}
        assert geo_native_pk not in returned_pks
        assert noise_pk not in returned_pks
        assert report.excluded_native_books_count == 1
        assert report.excluded_noise_books_count == 1

        by_bk = {b.book_pk: b for b in report.books}
        fis_passages = by_bk[fisica_pk].passages
        assert len(fis_passages) == 3  # Sommario sulla pag. 5 escluso!
        assert all(p.page_start != 5 for p in fis_passages)
        assert all(p.verbatim_quote and p.best_stmt and p.interdisciplinary_reason for p in fis_passages)
        conn.close()


@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_live_corpus_spectrum_invariants() -> None:
    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        books_with_spectrum = int(
            conn.execute("SELECT COUNT(DISTINCT book_pk) FROM book_discipline_spectrum").fetchone()[0]
        )
        assert books_with_spectrum >= 1150

        violations = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT book_pk, SUM(share_pct) AS s
                    FROM book_discipline_spectrum
                    GROUP BY book_pk
                    HAVING ABS(s - 100.0) > 0.1
                )
                """
            ).fetchone()[0]
        )
        assert violations == 0

        # Spot check Marconi (514), Euclide (1373), Galileo (1390), Apostol Analisi 1 (1391)
        for bpk, expected_top in [
            (514, "storia_politica_militare"),
            (1373, "matematica"),
            (1390, None),
            (1391, "matematica"),
        ]:
            sp = get_book_spectrum(conn, bpk)
            assert sp is not None, f"Spettro mancante per book_pk={bpk}"
            assert sp["quality_tier"] == "canonical_book"
            assert 99.9 <= sp["share_sum_pct"] <= 100.1
            assert sp["disciplines"], f"Nessuna disciplina per book_pk={bpk}"
            if expected_top is not None:
                assert sp["primary_discipline"] == expected_top
            for d in sp["disciplines"]:
                assert len(d["block_pks"]) == d["block_count"]
    finally:
        conn.close()


@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_discipline_reconstructor_live_geography() -> None:
    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        report = reconstruct_discipline(conn, "geografia_territorio")
        assert report.target_discipline == "geografia_cartografia_territorio"
        assert report.total_wrong_books >= 15
        assert report.total_wrong_books == len(report.books)
        assert report.total_passages >= 100
        assert len(report.distinct_primary_disciplines) >= 4

        returned_pks = {b.book_pk for b in report.books}
        for expected_bpk in (514, 1415, 1416, 976, 1390):  # Marconi, Laplace, Volta, Torricelli, Galileo
            assert expected_bpk in returned_pks, f"Manca book_pk={expected_bpk} nei Libri Sbagliati per Geografia"

        for forbidden_bpk in (744, 745, 746, 1080, 845, 101):  # PRIMIGI, fullrefman, nativi geo
            assert forbidden_bpk not in returned_pks, f"Trovato libro escluso book_pk={forbidden_bpk}"

        for book in report.books:
            assert book.passages
            for p in book.passages:
                assert p.block_pk > 0
                assert p.verbatim_quote.strip()
                assert p.best_stmt.strip()
                assert p.interdisciplinary_reason.strip()
    finally:
        conn.close()
