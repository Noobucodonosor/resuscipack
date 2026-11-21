"""Test di integrazione per l'Ontologia Ministeriale v6 consolidata, la spina estesa 1ª Elementare → 5ª Superiore e i drill liceali SymPy (TASK-SPEC-04)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from resuscipack.corpus.normalizer import make_block_uid, make_book_uid, normalize_for_match
from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db
from resuscipack.curriculum.dag import load_unified_dag
from resuscipack.curriculum.drills_sympy import generate_drill_set, grade_drill_answer
from resuscipack.curriculum.ministerial_ontology import (
    DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    DEFAULT_V6_SOURCES_DIR,
    LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE,
    build_consolidated_ontology,
    load_consolidated_ontology,
)
from resuscipack.epistemic import (
    DEFAULT_COVERAGE_REPORT_PATH,
    compute_all_book_spectra,
    find_objectives_for_block,
    find_objectives_for_book,
    get_objective_corpus_mapping,
    map_ontology_to_corpus,
    persist_block_extraction,
    validate_block_extraction,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_v6_sources_and_consolidated_ontology_integrity() -> None:
    v6_files = sorted(DEFAULT_V6_SOURCES_DIR.glob("*.json"))
    assert len(v6_files) == 53

    built = build_consolidated_ontology()
    loaded = load_consolidated_ontology(DEFAULT_CONSOLIDATED_ONTOLOGY_PATH)
    assert built["stats"] == loaded["stats"]

    stats = loaded["stats"]
    assert stats["source_json_files"] == 53
    assert stats["total_objectives"] >= 2825
    assert set(stats["by_cycle"].keys()) == {
        "primaria",
        "secondaria_i_grado",
        "secondaria_ii_grado_licei",
        "secondaria_ii_grado_professionali",
        "secondaria_ii_grado_tecnici",
    }

    # Verifica integrazione esplicita Quinto Anno Liceo Scientifico Matematica
    quinto_objs = [
        o for o in loaded["objectives"]
        if o["source_file"] == LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE
    ]
    assert len(quinto_objs) >= 12
    assert all(o["epistemic_layer"] == "institutional_declared" for o in loaded["objectives"])


def test_k13_math_objectives_100_percent_mapped_to_valid_dag_nodes() -> None:
    dag = load_unified_dag()
    valid_node_ids = set(dag["nodes"].keys())
    ontology = load_consolidated_ontology(DEFAULT_CONSOLIDATED_ONTOLOGY_PATH)

    k13_math = [
        o for o in ontology["objectives"]
        if Path(o["source_file"].split("#", 1)[0]).name in {
            "primaria_matematica.json",
            "media_matematica.json",
            "liceo_scientifico_matematica.json",
        }
        or o["source_file"] == LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE
    ]
    # 41 Primaria + 37 Medie + 59 Liceo bienni + 15 Quinto Anno = 152
    assert len(k13_math) == 152

    for obj in k13_math:
        mapped = obj["mapped_dag_node_ids"]
        assert mapped, f"Obiettivo matematico orfano: {obj['statement']}"
        for nid in mapped:
            assert nid in valid_node_ids, f"ID DAG inesistente {nid!r} in {obj['objective_uid']}"

    # Verifica presenza mappatura specifica verso i nodi liceali
    all_mapped_ids = {nid for obj in k13_math for nid in obj["mapped_dag_node_ids"]}
    for expected_hs in (
        "superiori.polinomi-prodotti-notevoli",
        "superiori.fattorizzazione-frazioni-algebriche",
        "superiori.coniche-luoghi-geometrici",
        "superiori.goniometria-formule-equazioni",
        "superiori.esponenziali-logaritmi",
        "superiori.numeri-complessi-gauss",
        "superiori.limiti-continuita-asintoti",
        "superiori.derivata-studio-funzione",
        "superiori.integrali-teorema-fondamentale",
        "superiori.equazioni-differenziali-modelli",
    ):
        assert expected_hs in all_mapped_ids


def test_high_school_sympy_drills_and_complex_support() -> None:
    keys = [
        "drill_polynomial_products",
        "drill_polynomial_ruffini",
        "drill_linear_systems_line",
        "drill_quadratic_radicals",
        "drill_conics_loci",
        "drill_progressions_sum",
        "drill_logarithms_exp",
        "drill_complex_numbers",
        "drill_combinatorics_binomial",
        "drill_limits_continuity",
        "drill_derivatives_extrema",
        "drill_definite_integrals",
        "drill_ode_separable",
    ]
    for key in keys:
        drills = generate_drill_set("test-hs", key, count=4, seed=42)
        assert len(drills) == 4
        for drill in drills:
            res = grade_drill_answer(drill["expected"], drill["expected"])
            assert res["is_correct"] is True, f"Fail {key}: {drill} -> {res}"

    # Verifica supporto esplicito forma complessa con `i` minuscola e equivalenza simbolica
    assert grade_drill_answer("3 + 4*I", "3 + 4*i")["is_correct"] is True
    assert grade_drill_answer("3 + 4*I", "4*i + 3")["is_correct"] is True
    assert grade_drill_answer("ln(8)", "3*ln(2)")["is_correct"] is True
    assert grade_drill_answer("16", "4^2")["is_correct"] is True
    assert grade_drill_answer("5*exp(2*x)", "5*e^(2*x)")["is_correct"] is True


def _insert_synth_book_block(
    conn,
    *,
    title: str,
    surface_domain: str,
    content: str,
    discs: list[str],
    topics: list[str],
    stmt: str,
    quote: str,
    page: int = 1,
) -> tuple[int, int]:
    bk_uid = make_book_uid(title, "test")
    conn.execute(
        """
        INSERT OR IGNORE INTO books (
            book_uid, title, author, year, surface_domain, language, source_kind, page_count, is_active
        ) VALUES (?, ?, 'Autore Test', 1980, ?, 'it', 'test', 200, 1)
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
        ) VALUES (?, ?, ?, 1, 'body', ?, ?, ?, 'Sezione', ?, ?, ?, ?, 'test')
        """,
        (blk_uid, book_pk, title, page, page, str(page), content, norm_c, len(content), max(1, len(content) // 4)),
    )
    block_pk = int(cur.lastrowid)
    ext = validate_block_extraction(
        {
            "yield": "high",
            "macro_disciplines": discs,
            "topics": topics,
            "places": [],
            "years": [],
            "units": [
                {
                    "kind": "def",
                    "mode": "defines",
                    "stmt": stmt,
                    "quote": quote,
                    "who": ["Autore Test"],
                    "vs": None,
                    "concepts": topics,
                }
            ],
            "sig": None,
        },
        block_content=content,
        require_v22_metadata=True,
    )
    persist_block_extraction(conn, block_pk=block_pk, block_uid=blk_uid, extraction=ext)
    conn.commit()
    return book_pk, block_pk


def test_curriculum_mapper_synthetic_r4_separation_and_bidirectional() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        db_path = tmp_dir / "mapper_synth.db"
        ont_path = tmp_dir / "mini_ont.json"
        conn = init_corpus_db(db_path)

        ont_payload = {
            "schema_version": "mini.v1",
            "objectives": [
                {
                    "objective_uid": "ont_cov_1",
                    "cycle": "primaria",
                    "school": "Primaria",
                    "subject": "Matematica",
                    "target_macro_discipline": "matematica",
                    "grade": "Classe quinta",
                    "nucleus": "Numeri",
                    "statement": "Utilizzare frazioni equivalenti e denominatore comune nei calcoli",
                    "source_file": "primaria_matematica.json",
                    "epistemic_layer": "institutional_declared",
                    "mapped_dag_node_ids": ["frazioni.denominatore-comune"],
                },
                {
                    "objective_uid": "ont_part_1",
                    "cycle": "secondaria_ii_grado_licei",
                    "school": "Liceo",
                    "subject": "Fisica",
                    "target_macro_discipline": "fisica",
                    "grade": "Quinto Anno",
                    "nucleus": "Elettromagnetismo",
                    "statement": "Propagazione delle onde elettromagnetiche e spettro",
                    "source_file": "liceo_fisica.json",
                    "epistemic_layer": "institutional_declared",
                    "mapped_dag_node_ids": [],
                },
                {
                    "objective_uid": "ont_gap_1",
                    "cycle": "primaria",
                    "school": "Primaria",
                    "subject": "Musica",
                    "target_macro_discipline": "musica_acustica",
                    "grade": "Classe terza",
                    "nucleus": "Pratica strumentale",
                    "statement": "Eseguire polifonie corali gregoriane con percussioni medievali",
                    "source_file": "primaria_musica.json",
                    "epistemic_layer": "institutional_declared",
                    "mapped_dag_node_ids": [],
                },
            ],
        }
        ont_path.write_text(json.dumps(ont_payload, ensure_ascii=False), encoding="utf-8")

        # 2 libri canonici di matematica per ont_cov_1
        _insert_synth_book_block(
            conn,
            title="Prodi - Aritmetica razionale",
            surface_domain="matematica",
            content="Le frazioni equivalenti condividono lo stesso valore tramite riduzione a denominatore comune.",
            discs=["matematica"],
            topics=["frazioni equivalenti", "denominatore comune"],
            stmt="Giovanni Prodi definisce le frazioni equivalenti e il denominatore comune nei calcoli.",
            quote="Le frazioni equivalenti condividono lo stesso valore tramite riduzione a denominatore comune",
            page=12,
        )
        _insert_synth_book_block(
            conn,
            title="Dodero - Elementi di Matematica",
            surface_domain="matematica",
            content="Ridurre due frazioni al minimo denominatore comune consente di sommare numeratori equivalenti.",
            discs=["matematica"],
            topics=["frazioni equivalenti", "denominatore comune"],
            stmt="Dodero espone i calcoli con frazioni equivalenti tramite denominatore comune.",
            quote="Ridurre due frazioni al minimo denominatore comune consente di sommare",
            page=24,
        )
        # 1 Libro Sbagliato (Fisica primaria) che contiene però un passaggio sulle frazioni equivalenti
        for p_idx in range(1, 5):
            _insert_synth_book_block(
                conn,
                title="Trattato di Idraulica Fisica",
                surface_domain="fisica_ingegneria",
                content=f"Esperimento {p_idx} sulla pressione dei fluidi, portata volumetrica e propagazione termica.",
                discs=["fisica"],
                topics=["idraulica"],
                stmt=f"Studio fisico numero {p_idx} sulla pressione e dinamica dei fluidi.",
                quote="pressione dei fluidi, portata volumetrica e propagazione",
                page=p_idx,
            )
        wb_book_pk, wb_block_pk = _insert_synth_book_block(
            conn,
            title="Trattato di Idraulica Fisica",
            surface_domain="fisica_ingegneria",
            content="Nella miscela dei condotti servono frazioni equivalenti con denominatore comune per bilanciare i flussi.",
            discs=["fisica", "matematica"],
            topics=["frazioni equivalenti", "denominatore comune"],
            stmt="Il modello idraulico applica frazioni equivalenti e denominatore comune per bilanciare le portate.",
            quote="servono frazioni equivalenti con denominatore comune per bilanciare i flussi",
            page=50,
        )

        # 1 blocco fisico per ont_part_1
        _insert_synth_book_block(
            conn,
            title="Trattato di Idraulica Fisica",
            surface_domain="fisica_ingegneria",
            content="La propagazione delle onde elettromagnetiche copre l'intero spettro dalle onde radio ai raggi gamma.",
            discs=["fisica"],
            topics=["onde elettromagnetiche", "spettro"],
            stmt="Le onde elettromagnetiche si propagano lungo lo spettro elettromagnetico.",
            quote="propagazione delle onde elettromagnetiche copre l'intero spettro",
            page=60,
        )

        compute_all_book_spectra(conn)
        summary = map_ontology_to_corpus(conn, ontology_path=ont_path)

        assert summary["total_objectives"] == 3
        assert summary["by_status"] == {"covered": 1, "gap": 1, "partial": 1}
        assert summary["objectives_with_wrong_book_evidence"] == 1

        mapped_cov = get_objective_corpus_mapping(conn, "ont_cov_1", ontology_path=ont_path)
        assert mapped_cov is not None
        assert mapped_cov["institutional_declared"]["epistemic_layer"] == "institutional_declared"
        assert mapped_cov["corpus_learnable"]["epistemic_layer"] == "corpus_learnable"
        assert mapped_cov["corpus_learnable"]["coverage_status"] == "covered"
        assert mapped_cov["corpus_learnable"]["wrong_book_evidence_count"] >= 1

        wb_objs = find_objectives_for_book(conn, wb_book_pk, only_wrong_book=True, ontology_path=ont_path)
        assert len(wb_objs) == 1
        assert wb_objs[0]["objective_uid"] == "ont_cov_1"
        assert wb_objs[0]["is_wrong_book"] is True

        blk_objs = find_objectives_for_block(conn, wb_block_pk, ontology_path=ont_path)
        assert [o["objective_uid"] for o in blk_objs] == ["ont_cov_1"]
        conn.close()


@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_curriculum_mapper_live_corpus_and_volume1_radar() -> None:
    ont = load_consolidated_ontology(DEFAULT_CONSOLIDATED_ONTOLOGY_PATH)
    assert len(ont["objectives"]) >= 2825
    assert all(o["epistemic_layer"] == "institutional_declared" for o in ont["objectives"])

    assert DEFAULT_COVERAGE_REPORT_PATH.exists(), "Manca corpus_coverage_report.json generato"
    report = json.loads(DEFAULT_COVERAGE_REPORT_PATH.read_text(encoding="utf-8"))
    assert report["epistemic_layer"] == "corpus_learnable"
    assert report["total_objectives"] == len(ont["objectives"])

    radar = report["volume1_gap_radar"]
    assert radar["k13_math_total"] == 152
    assert radar["k13_status_counts"].get("gap", 0) <= 38  # < 25% gap rate sul Volume I
    assert radar["volume1_dag_nodes_summary"]["layer0_count"] == 64
    assert radar["volume1_dag_nodes_summary"]["ofa_p0_count"] == 8

    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        db_total = int(conn.execute("SELECT COUNT(*) FROM objective_corpus_map").fetchone()[0])
        assert db_total == len(ont["objectives"])
        assert int(conn.execute("SELECT COUNT(*) FROM objective_corpus_map WHERE epistemic_layer = 'corpus_learnable'").fetchone()[0]) == db_total

        euclide_objs = find_objectives_for_book(conn, 1373)
        assert len(euclide_objs) >= 3

        marconi_wb = find_objectives_for_book(conn, 514, only_wrong_book=True)
        assert len(marconi_wb) >= 2
        assert all(o["is_wrong_book"] for o in marconi_wb)
    finally:
        conn.close()
