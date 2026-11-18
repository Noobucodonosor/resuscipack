"""Test di integrazione per l'Ontologia Ministeriale v6 consolidata, la spina estesa 1ª Elementare → 5ª Superiore e i drill liceali SymPy (TASK-SPEC-04)."""

from __future__ import annotations

from pathlib import Path

from resuscipack.curriculum.dag import load_unified_dag
from resuscipack.curriculum.drills_sympy import generate_drill_set, grade_drill_answer
from resuscipack.curriculum.ministerial_ontology import (
    DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    DEFAULT_V6_SOURCES_DIR,
    LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE,
    build_consolidated_ontology,
    load_consolidated_ontology,
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
