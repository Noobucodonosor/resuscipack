"""Catalogo editoriale completo dei *Nuovi Libri* Continui (Volume I & Volume II, ADR-0004).

Definisce:
- `VOL1_CHAPTER_SPECS`: 11 capitoli continui *Dall'Ovvio al Simbolo (Verso l'OFA Matematica I)*,
  coprendo tutti i nodi K-13 (`1ª elementare -> 5ª superiore`) e i prerequisiti OFA (`P0.1..P0.8`, `P6.1`).
- `VOL2_CHAPTER_SPECS`: 9 capitoli continui *I Ponti Nascosti di SecAI (Dal Discreto al Software Sicuro)*,
  coprendo `P1.1..P6.2`, la lacuna a 0 CFU di Probabilità/Statistica e i 5 pacchetti Open-Access (€0).
- `export_ofa_30_real_questions`: estrattore deterministico dei 30 quesiti reali di ingresso/OFA
  ancorati verbatim ai `block_pk`/`block_uid` di `pack_corpus.db`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..corpus.schema import DEFAULT_DB_PATH, connect_corpus_db
from ..epistemic.schema_v21 import normalizza_testo
from .author_engine import DEFAULT_BOOKS_DIR, PILOT_CHAPTER_SPEC, ChapterSpec

VOL1_TITLE_DISPLAY = "Dall'Ovvio al Simbolo"
VOL2_TITLE_DISPLAY = "I Ponti Nascosti di SecAI"

OA_UID_PRO_GIT = "oa_01_pro_git_it"
OA_UID_BONEH_SHOUP = "oa_02_boneh_shoup_crypto"
OA_UID_OWASP_WSTG = "oa_03_owasp_wstg_v42"
OA_UID_SWE_GOOGLE = "oa_03_swe_google_testing"
OA_UID_OPENINTRO_STATS = "oa_04_openintro_stats4"
OA_UID_ARXIV_VASWANI = "oa_05_arxiv_vaswani_transformer"
OA_UID_ARXIV_GOODFELLOW = "oa_05_arxiv_goodfellow_advml"
OA_UID_ARXIV_BIGGIO = "oa_05_arxiv_biggio_wild_patterns"

ALL_OA_BOOK_UIDS: Tuple[str, ...] = (
    OA_UID_PRO_GIT,
    OA_UID_BONEH_SHOUP,
    OA_UID_OWASP_WSTG,
    OA_UID_SWE_GOOGLE,
    OA_UID_OPENINTRO_STATS,
    OA_UID_ARXIV_VASWANI,
    OA_UID_ARXIV_GOODFELLOW,
    OA_UID_ARXIV_BIGGIO,
)

VOL1_CHAPTER_SPECS: Tuple[ChapterSpec, ...] = (
    PILOT_CHAPTER_SPEC,
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=2,
        slug="le_operazioni_e_la_distributiva",
        title="Le operazioni fondamentali, il resto euclideo e la proprietà distributiva",
        subtitle="Dal riunire e sottrarre alla geometria delle aree e alla divisione con resto",
        node_ids=(
            "operazioni.addizione",
            "operazioni.sottrazione",
            "operazioni.colonna",
            "operazioni.moltiplicazione",
            "operazioni.distributiva",
            "operazioni.divisione",
        ),
        concept_queries=("proprietà distributiva", "divisione euclidea", "moltiplicazione"),
        drill_keys=(
            "drill_addition_properties",
            "drill_subtraction_inverse",
            "drill_column_carry",
            "drill_multiplication_grid",
            "drill_distributive_law",
            "drill_euclidean_division",
        ),
        svg_diagram_id="area_distributive_grid",
        svg_caption="Interpretazione geometrica della proprietà distributiva a(b + c) = ab + ac come scomposizione di rettangoli.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(1373, 1393, 974, 985, 515),
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=3,
        slug="frazioni_primi_decimali_e_segni",
        title="Dai numeri primi alle frazioni, ai decimali e ai numeri con segno",
        subtitle="Parti equivalenti, teorema fondamentale dell'aritmetica, potenze, radici e retta orientata",
        node_ids=(
            "frazioni.significato",
            "frazioni.equivalenza",
            "frazioni.denominatore-comune",
            "frazioni.moltiplicazione-divisione",
            "numeri.decimali",
            "divisibilita.multipli-primi",
            "divisibilita.mcm",
            "divisibilita.mcd",
            "numeri.relativi",
            "operazioni.potenze-base",
            "operazioni.radici-base",
        ),
        concept_queries=("numeri primi", "frazioni equivalenti", "numeri relativi"),
        drill_keys=(
            "drill_fraction_meaning",
            "drill_fraction_equivalence",
            "drill_fraction_addition",
            "drill_fraction_mul_div",
            "drill_decimals",
            "drill_prime_factorization",
            "drill_lcm",
            "drill_gcd",
            "drill_signed_integers",
            "drill_exponent_rules",
            "drill_square_roots",
        ),
        svg_diagram_id="fraction_number_line",
        svg_caption="Frazioni equivalenti dello stesso intero e collocazione simmetrica di interi relativi e razionali sulla retta.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(1373, 985, 974, 207, 515),
        target_length_words=1350,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=4,
        slug="rapporti_proporzioni_misure_e_lettere",
        title="Rapporti, proporzioni, misure e il linguaggio delle lettere",
        subtitle="Dal confronto tra grandezze omogenee alle leggi di proporzionalità e alle prime equazioni",
        node_ids=(
            "rapporti.proporzioni-percentuali",
            "misure.confronto-unita",
            "misure.equivalenze-decimali",
            "relazioni.sequenze-regole",
            "relazioni.lettere-formule",
            "relazioni.proporzionalita-diretta-inversa",
            "relazioni.equazione-primo-grado-base",
        ),
        concept_queries=("proporzioni", "grandezze proporzionali", "equazioni lineari"),
        drill_keys=(
            "drill_proportions_percent",
            "drill_unit_measurement",
            "drill_metric_conversions",
            "drill_sequence_pattern",
            "drill_literal_expressions",
            "drill_direct_inverse_prop",
            "drill_linear_equation",
        ),
        svg_diagram_id="proportional_scaling_hyperbola",
        svg_caption="Confronto geometrico tra proporzionalità diretta y = kx e legge iperbolica inversa x·y = k.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(1373, 1390, 974, 1374, 941),
        target_length_words=1250,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=5,
        slug="geometria_isometrie_pitagora_e_spazio",
        title="Geometria delle figure, isometrie, Pitagora e pi greco nello spazio",
        subtitle="Dalle definizioni euclidee al piano cartesiano, alle trasformazioni rigide e ai volumi",
        node_ids=(
            "geometria.punti-rette-segmenti",
            "geometria.angoli-rotazioni",
            "geometria.parallelismo-perpendicolarita",
            "geometria.poligoni-perimetro",
            "geometria.area-rettangolo-schieramento",
            "geometria.area-triangolo-poligoni",
            "geometria.simmetrie-traslazioni",
            "geometria.pitagora",
            "geometria.cerchio-pi-greco",
            "geometria.similitudine-scala",
            "geometria.solidi-volume",
            "geometria.coordinate-griglia",
        ),
        concept_queries=("teorema di pitagora", "pi greco", "cavalieri volume"),
        drill_keys=(
            "drill_segments_length",
            "drill_angles_degrees",
            "drill_perpendicular_angles",
            "drill_triangle_perimeter",
            "drill_rectangle_area",
            "drill_triangle_area",
            "drill_translation_coords",
            "drill_pythagoras",
            "drill_circle_pi",
            "drill_similarity_scale",
            "drill_volume_scaling",
            "drill_cartesian_points",
        ),
        svg_diagram_id="pythagoras_and_circle",
        svg_caption="Relazione metrica pitagorica sui cateti e misure di circonferenza e area del cerchio.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(1373, 1393, 531, 842, 974),
        target_length_words=1350,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=6,
        slug="logica_dimostrazione_e_circuiti",
        title="Dal vero e falso all'arte della dimostrazione e della logica formale",
        subtitle="Connettivi booleani, circuiti fisici, quantificatori e forza del controesempio",
        node_ids=(
            "logica.classificare-attributi",
            "logica.vero-falso-non-e-o",
            "logica.tutti-qualcuno-controesempio",
            "P0.1",
            "P0.2",
            "P6.1",
        ),
        concept_queries=("dimostrazione per assurdo", "logica booleana", "controesempio"),
        drill_keys=(
            "drill_set_classification",
            "drill_boolean_basics",
            "drill_counterexample",
            "drill_p0_logic_counterexample",
            "drill_p0_propositional",
        ),
        svg_diagram_id="series_conjunction_circuit",
        svg_caption="Isomorfismo strutturale tra circuiti elettrici in serie/parallelo e connettivi logici AND/OR.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(5, 1381, 3, 985, 1373),
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=7,
        slug="insiemi_relazioni_polinomi_e_sistemi",
        title="Insiemi, relazioni, polinomi e i numeri dagli interi ai reali",
        subtitle="Funzioni tra insiemi, irrazionalità di radice di due, scomposizione polinomiale e sistemi lineari",
        node_ids=(
            "P0.3",
            "P0.4",
            "superiori.polinomi-prodotti-notevoli",
            "superiori.fattorizzazione-frazioni-algebriche",
            "superiori.sistemi-lineari-retta",
        ),
        concept_queries=("numeri irrazionali", "funzione iniettiva suriettiva", "polinomi ruffini"),
        drill_keys=(
            "drill_p0_sets_functions",
            "drill_p0_radicals_powers",
            "drill_polynomial_products",
            "drill_polynomial_ruffini",
            "drill_linear_systems_line",
        ),
        svg_diagram_id="function_sets_mapping",
        svg_caption="Pannello sinistro: applicazione non iniettiva tra gli insiemi finiti A e B; pannello destro: rette r1 e r2 nel piano cartesiano (grafici di funzioni lineari) che si intersecano nel punto soluzione del sistema.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(515, 1391, 985, 974, 518),
        proof_rubric_id="sqrt2_irrational",
        target_length_words=1550,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=8,
        slug="equazioni_disequazioni_moduli_e_tolleranza",
        title="Equazioni, disequazioni, valori assoluti e il corridoio di tolleranza",
        subtitle="Dal calcolo algebrico di secondo grado alle disequazioni fratte, irrazionali e con modulo",
        node_ids=(
            "P0.5",
            "superiori.radicali-equazioni-secondo-grado",
            "superiori.equazioni-fratte-irrazionali-modulo",
        ),
        concept_queries=("valore assoluto", "disequazioni", "equazioni di secondo grado"),
        drill_keys=("drill_p0_symbolic_inequalities", "drill_quadratic_radicals"),
        svg_diagram_id="marconi_tolerance_corridor",
        svg_caption="Il modulo |x - x0| < delta come intervallo aperto simmetrico e corridoio di tolleranza fisica.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(514, 974, 515, 1391, 941),
        target_length_words=1250,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=9,
        slug="funzioni_coniche_logaritmi_e_complessi",
        title="Funzioni elementari, coniche, logaritmi e numeri complessi",
        subtitle="Dalle coniche come luoghi geometrici alle scale logaritmiche, ai grafici analitici e al piano di Gauss",
        node_ids=(
            "P0.6",
            "superiori.coniche-luoghi-geometrici",
            "superiori.esponenziali-logaritmi",
            "superiori.numeri-complessi-gauss",
        ),
        concept_queries=("parabola fuoco", "logaritmi", "numeri complessi"),
        drill_keys=(
            "drill_p0_functions_parabola",
            "drill_conics_loci",
            "drill_logarithms_exp",
            "drill_complex_numbers",
        ),
        svg_diagram_id="parabola_focal_rays",
        svg_caption="La parabola come luogo dei punti equidistanti dal fuoco F e dalla direttrice d, con proprietà riflettente assiale.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(1390, 1374, 1391, 515, 974),
        graph_invariant_id="abs_shifted_log",
        target_length_words=1350,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=10,
        slug="angoli_circonferenza_e_trigonometria",
        title="Angoli, circonferenza goniometrica e risoluzione dei triangoli",
        subtitle="Dalla geometria sintetica euclidea alla similitudine, alle identità goniometriche e ai teoremi trigonometrici",
        node_ids=(
            "P0.7",
            "superiori.geometria-sintetica-congruenza",
            "superiori.circonferenza-euclide-talete",
            "superiori.goniometria-formule-equazioni",
            "superiori.trigonometria-triangoli",
        ),
        concept_queries=("trigonometria seno coseno", "teorema di talete", "circonferenza angoli"),
        drill_keys=(
            "drill_p0_trigonometry",
            "drill_euclid_similarity",
            "drill_goniometry_identities",
            "drill_cosine_law",
        ),
        svg_diagram_id="unit_circle_trig",
        svg_caption="Proiezione di coseno e seno sulla circonferenza unitaria e genesi della sinusoide periodica.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(1373, 1393, 974, 1391, 515),
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol1_ofa",
        chapter_number=11,
        slug="successioni_analisi_dati_e_stime_ofa",
        title="Successioni, introduzione all'analisi e stime a tempo",
        subtitle="Progressioni, combinatoria, limiti, derivate, integrali, equazioni differenziali e problemi d'ingresso",
        node_ids=(
            "P0.8",
            "dati.tabelle-grafici",
            "dati.media-frequenza-incertezza",
            "superiori.successioni-progressioni",
            "superiori.combinatoria-probabilita-composta",
            "superiori.limiti-continuita-asintoti",
            "superiori.derivata-studio-funzione",
            "superiori.integrali-teorema-fondamentale",
            "superiori.equazioni-differenziali-modelli",
        ),
        concept_queries=("derivata tangente", "integrale definito", "progressioni geometriche"),
        drill_keys=(
            "drill_p0_fermi_logic",
            "drill_frequency_table",
            "drill_mean_median_prob",
            "drill_progressions_sum",
            "drill_combinatorics_binomial",
            "drill_limits_continuity",
            "drill_derivatives_extrema",
            "drill_definite_integrals",
            "drill_ode_separable",
        ),
        svg_diagram_id="derivative_tangent_integral",
        svg_caption="Dualità del calcolo infinitesimale: pendenza della retta tangente e accumulo dell'area sottesa alla curva.",
        book_title_display=VOL1_TITLE_DISPLAY,
        preferred_book_pks=(941, 515, 1391, 1374, 1361),
        target_length_words=1400,
    ),
)

VOL2_CHAPTER_SPECS: Tuple[ChapterSpec, ...] = (
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=1,
        slug="induzione_ricorsione_e_discreto",
        title="Induzione, ricorsione e matematica del discreto",
        subtitle="Dal principio del buon ordinamento alle definizioni ricorsive, alle congruenze e al conteggio combinatorio",
        node_ids=("P2.1", "P2.2"),
        concept_queries=("induzione matematica", "ricorsione", "matematica discreta"),
        drill_keys=("drill_p2_induction", "drill_p2_discrete_combinatorics"),
        svg_diagram_id="algorithm_invariant_testing",
        svg_caption="Schema dimostrativo per induzione matematica e mantenimento dell'invariante lungo passi discreti.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(1381, 518, 985, 515),
        proof_rubric_id="induction_sum_n",
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=2,
        slug="calcolo_differenziale_e_catena",
        title="Calcolo differenziale e regola della catena per l'apprendimento automatico",
        subtitle="Tassi di variazione composti, gradienti multivariabili e ottimizzazione lungo curve e superfici",
        node_ids=("P2.3",),
        concept_queries=("regola della catena derivata", "gradiente", "funzioni composte"),
        drill_keys=("drill_p2_calculus_chain", "drill_derivatives_extrema"),
        svg_diagram_id="derivative_tangent_integral",
        svg_caption="Dalla derivata direzionale e regola della catena all'accumulo integrale dei contributi locali.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(1391, 1386, 515, 1374),
        target_length_words=1250,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=3,
        slug="algebra_lineare_operativa",
        title="Algebra lineare operativa: vettori, matrici e trasformazioni",
        subtitle="Spazi vettoriali nello spazio 3D, determinanti, autovettori e geometria delle trasformazioni lineari",
        node_ids=("P3.1", "superiori.geometria-spazio-vettori"),
        concept_queries=("algebra lineare matrici", "autovalori autovettori", "spazi vettoriali"),
        drill_keys=("drill_p3_linear_algebra", "drill_space_vectors"),
        svg_diagram_id="linear_algebra_transform",
        svg_caption="Azione lineare di una matrice A sulla base canonica, variazione d'area |det(A)| e direzioni invarianti.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(318, 1389, 1386, 974),
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=4,
        slug="probabilita_prima_del_ml",
        title="Probabilità: colmare il vuoto prima del Machine Learning",
        subtitle="Spazi di probabilità, indipendenza, teorema di Bayes e aggiornamento razionale dell'incertezza",
        node_ids=("P3.2",),
        concept_queries=("probabilità condizionata", "teorema di bayes", "variabile aleatoria"),
        drill_keys=("drill_p3_bayes", "drill_combinatorics_binomial"),
        svg_diagram_id="probability_tree_bayes",
        svg_caption="Partizione dello spazio campionario tramite albero condizionato e aggiornamento bayesiano a posteriori.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(1361, 988, 5),
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=5,
        slug="statistica_inferenziale_e_dati",
        title="Statistica inferenziale e analisi dei dati senza illusioni",
        subtitle="Metodo dei minimi quadrati, regressione lineare, intervalli di confidenza e uso critico del p-value",
        node_ids=("P3.3",),
        concept_queries=("minimi quadrati", "intervallo di confidenza", "regressione lineare"),
        drill_keys=("drill_p3_least_squares",),
        svg_diagram_id="statistical_regression_ci",
        svg_caption="Adattamento lineare ai minimi quadrati, residui verticali e fascia di incertezza campionaria.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(1361, 988, 1386),
        preferred_book_uids=(OA_UID_OPENINTRO_STATS,),
        target_length_words=1250,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=6,
        slug="crittografia_aritmetica_modulare_e_rsa",
        title="Crittografia applicata: aritmetica modulare, RSA e protocolli",
        subtitle="Congruenze, funzione totiente di Eulero, asimmetria delle chiavi e distinzione tra hash e cifratura",
        node_ids=("P4.1",),
        concept_queries=("aritmetica modulare", "funzione di hash", "crittografia rsa"),
        drill_keys=("drill_p4_rsa_modular",),
        svg_diagram_id="modular_clock_rsa",
        svg_caption="Aritmetica ciclica dell'orologio modulare Z/nZ ed esponenti pubblici e privati legati da Eulero.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(1334, 4, 1373),
        preferred_book_uids=(OA_UID_BONEH_SHOUP,),
        proof_rubric_id="hash_vs_encryption",
        target_length_words=1300,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=7,
        slug="macchina_memoria_binario_e_reti",
        title="Macchina, memoria, rappresentazione binaria e reti",
        subtitle="Complemento a due, aritmetica finita dei registri, stack, heap e anatomia dei protocolli di rete",
        node_ids=("P4.2",),
        concept_queries=("complemento a due", "architettura dei calcolatori memoria", "protocolli di rete"),
        drill_keys=("drill_p4_twos_complement",),
        svg_diagram_id="memory_stack_twos_comp",
        svg_caption="Codifica in complemento a due su 8 bit e disposizione della memoria virtuale tra stack, heap e segmento dati.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(183, 1376, 982, 3),
        target_length_words=1250,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=8,
        slug="complessita_invarianti_e_scrittura_tecnica",
        title="Complessità, invarianti di ciclo e scrittura tecnica dalle fonti",
        subtitle="Correttezza formale degli algoritmi, ordini di crescita, riga di comando e rigore argomentativo",
        node_ids=("P5.1", "P1.1", "P6.2"),
        concept_queries=("complessita algoritmi", "invariante di ciclo", "semantica programmi"),
        drill_keys=("drill_p5_complexity_invariants", "drill_p1_cli_permissions"),
        svg_diagram_id="algorithm_invariant_testing",
        svg_caption="Ciclo dimostrativo dell'invariante (inizializzazione, mantenimento, terminazione) e verifica sistematica.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(518, 1381, 982, 1336),
        target_length_words=1250,
    ),
    ChapterSpec(
        volume_id="vol2_secai",
        chapter_number=9,
        slug="git_testing_sicurezza_web_e_ai",
        title="Versionamento, testing sistematico, sicurezza web e modelli generativi",
        subtitle="Storia riproducibile del codice, verifica dei casi limite, vulnerabilità web e perturbazioni avversarie nei modelli AI",
        node_ids=("P1.2", "P5.2", "P5.3"),
        concept_queries=("sicurezza applicazioni web", "testing software", "controllo di versione"),
        drill_keys=("drill_p1_git_concepts", "drill_p5_testing_edge_cases", "drill_p5_http_sqli"),
        svg_diagram_id="series_conjunction_circuit",
        svg_caption="Difesa in profondità e controllo congiunto delle condizioni di sicurezza e correttezza del software.",
        book_title_display=VOL2_TITLE_DISPLAY,
        preferred_book_pks=(4, 982, 1336),
        preferred_book_uids=(
            OA_UID_PRO_GIT,
            OA_UID_OWASP_WSTG,
            OA_UID_SWE_GOOGLE,
            OA_UID_ARXIV_VASWANI,
            OA_UID_ARXIV_GOODFELLOW,
            OA_UID_ARXIV_BIGGIO,
        ),
        target_length_words=1350,
    ),
)


def get_volume_specs(volume_id: str) -> Tuple[ChapterSpec, ...]:
    vid = str(volume_id or "").strip().lower()
    if vid == "vol1_ofa":
        return VOL1_CHAPTER_SPECS
    if vid == "vol2_secai":
        return VOL2_CHAPTER_SPECS
    raise ValueError(f"Volume sconosciuto: {volume_id!r} (attesi 'vol1_ofa' o 'vol2_secai').")


def _extract_clean_excerpt_for_question(
    raw_snippet: str,
    haystack_norm: str,
) -> Optional[str]:
    """Restituisce un estratto leggibile (6-45 parole) la cui forma normalizzata è verbatim in `norm_content`."""
    cleaned = " ".join(str(raw_snippet or "").split()).strip()
    if len(cleaned) < 25:
        return None
    if re.search(r"in\s+(?:ﬁ|fi)gura", cleaned, flags=re.IGNORECASE):
        return None
    if "`" in cleaned:
        cleaned = re.sub(r"\s+\S*`\S*.*$", "", cleaned).strip()
    words = cleaned.split()
    for end in range(min(40, len(words)), 5, -1):
        cand = " ".join(words[:end]).strip()
        if normalizza_testo(cand) in haystack_norm:
            return cand
    return None


def export_ofa_30_real_questions(
    db_path: Path | str = DEFAULT_DB_PATH,
    out_path: Optional[Path | str] = None,
    *,
    target_count: int = 30,
) -> List[Dict[str, Any]]:
    """Estrae deterministicamente 30 quesiti reali d'ingresso/OFA ancorati verbatim al corpus."""
    conn = connect_corpus_db(db_path, read_only=True)
    conn.row_factory = sqlite3.Row
    questions: List[Dict[str, Any]] = []
    seen_norm: set[str] = set()

    try:
        # 1. Quesiti matematici CISIA / Conferenza Presidi (`Testmatbasesol`, book_pk=941)
        rows_mat = conn.execute(
            """
            SELECT b.block_pk, b.block_uid, b.page_start, b.printed_page, b.content, b.norm_content,
                   bk.title AS book_title
            FROM blocks b
            JOIN books bk ON bk.book_pk = b.book_pk
            WHERE b.book_pk = 941 AND b.is_active = 1
            ORDER BY b.page_start ASC, b.block_pk ASC
            """
        ).fetchall()
        for row in rows_mat:
            hay = str(row["norm_content"] or normalizza_testo(row["content"]))
            for m in re.finditer(r"(?:^|\n)(\d{1,2})\.\s*\n([^\n]+(?:\n[^\n]+)?)", str(row["content"] or "")):
                if len(questions) >= target_count:
                    break
                qnum = m.group(1)
                body_raw = re.split(r"\n(?:[A-D]|Argomento:)\b", m.group(2))[0]
                excerpt = _extract_clean_excerpt_for_question(body_raw, hay)
                if excerpt is None:
                    continue
                k = normalizza_testo(excerpt)[:60]
                if k in seen_norm:
                    continue
                seen_norm.add(k)
                questions.append(
                    {
                        "id": f"OFA-REAL-{len(questions) + 1:02d}",
                        "source_kind": "test_matematica_di_base",
                        "book_title": str(row["book_title"]),
                        "block_pk": int(row["block_pk"]),
                        "block_uid": str(row["block_uid"]),
                        "page": int(row["printed_page"] or row["page_start"] or 1),
                        "original_number": qnum,
                        "question_excerpt": excerpt,
                    }
                )

        # 2. Quesiti d'ingresso di Informatica (`Test-di-informatica-2015-2017`, book_pk=935)
        rows_inf = conn.execute(
            """
            SELECT b.block_pk, b.block_uid, b.page_start, b.printed_page, b.content, b.norm_content,
                   bk.title AS book_title
            FROM blocks b
            JOIN books bk ON bk.book_pk = b.book_pk
            WHERE b.book_pk = 935 AND b.is_active = 1
            ORDER BY b.page_start ASC, b.block_pk ASC
            """
        ).fetchall()
        for row in rows_inf:
            if len(questions) >= target_count:
                break
            hay = str(row["norm_content"] or normalizza_testo(row["content"]))
            for m in re.finditer(r"(?:^|\n)\s*(\d{1,2})\)\s+([^\n]+)", str(row["content"] or "")):
                if len(questions) >= target_count:
                    break
                qnum = m.group(1)
                excerpt = _extract_clean_excerpt_for_question(m.group(2), hay)
                if excerpt is None:
                    continue
                k = normalizza_testo(excerpt)[:60]
                if k in seen_norm:
                    continue
                seen_norm.add(k)
                questions.append(
                    {
                        "id": f"OFA-REAL-{len(questions) + 1:02d}",
                        "source_kind": "test_ingresso_informatica",
                        "book_title": str(row["book_title"]),
                        "block_pk": int(row["block_pk"]),
                        "block_uid": str(row["block_uid"]),
                        "page": int(row["printed_page"] or row["page_start"] or 1),
                        "original_number": qnum,
                        "question_excerpt": excerpt,
                    }
                )

        # 3. Completa a 30 con quesiti logico-matematici dalle prove d'ammissione 2008-2017 (book_pk 1282..1286)
        if len(questions) < target_count:
            rows_adm = conn.execute(
                """
                SELECT b.block_pk, b.block_uid, b.page_start, b.printed_page, b.content, b.norm_content,
                       bk.title AS book_title
                FROM blocks b
                JOIN books bk ON bk.book_pk = b.book_pk
                WHERE b.book_pk IN (1286, 1285, 1284, 1283, 1282)
                  AND b.is_active = 1
                  AND b.page_start BETWEEN 5 AND 6
                ORDER BY b.book_pk DESC, b.page_start ASC
                """
            ).fetchall()
            for row in rows_adm:
                if len(questions) >= target_count:
                    break
                hay = str(row["norm_content"] or normalizza_testo(row["content"]))
                for raw_line in str(row["content"] or "").splitlines():
                    if len(questions) >= target_count:
                        break
                    left_col = re.split(r" {5,}", raw_line.strip())[0].strip()
                    m = re.match(r"^(4[0-9]|5[0-5])\.\s+(.+)$", left_col)
                    if not m:
                        continue
                    qnum, txt = m.group(1), m.group(2)
                    excerpt = _extract_clean_excerpt_for_question(txt, hay)
                    if excerpt is None:
                        continue
                    k = normalizza_testo(excerpt)[:60]
                    if k in seen_norm:
                        continue
                    seen_norm.add(k)
                    questions.append(
                        {
                            "id": f"OFA-REAL-{len(questions) + 1:02d}",
                            "source_kind": "test_ammissione_logica_matematica",
                            "book_title": str(row["book_title"]),
                            "block_pk": int(row["block_pk"]),
                            "block_uid": str(row["block_uid"]),
                            "page": int(row["printed_page"] or row["page_start"] or 5),
                            "original_number": qnum,
                            "question_excerpt": excerpt,
                        }
                    )
    finally:
        conn.close()

    dest = Path(out_path) if out_path else (DEFAULT_BOOKS_DIR / "vol1_ofa" / "ofa_30_quesiti_reali.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "ofa-30-quesiti-reali.v1",
        "count": len(questions),
        "questions": questions,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return questions


__all__ = [
    "ALL_OA_BOOK_UIDS",
    "OA_UID_ARXIV_BIGGIO",
    "OA_UID_ARXIV_GOODFELLOW",
    "OA_UID_ARXIV_VASWANI",
    "OA_UID_BONEH_SHOUP",
    "OA_UID_OPENINTRO_STATS",
    "OA_UID_OWASP_WSTG",
    "OA_UID_PRO_GIT",
    "OA_UID_SWE_GOOGLE",
    "VOL1_CHAPTER_SPECS",
    "VOL1_TITLE_DISPLAY",
    "VOL2_CHAPTER_SPECS",
    "VOL2_TITLE_DISPLAY",
    "export_ofa_30_real_questions",
    "get_volume_specs",
]
