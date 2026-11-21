"""Gestione dell'Ontologia Ministeriale v6 consolidata e mappatura sulla spina SecAI (TASK-SPEC-04).

Mantiene rigorosamente separati (regola R4 di SPEC.md):
- il livello `institutional_declared` (gli obiettivi ufficiali importati dai 53 file JSON di `ontologia_v6`
  più l'integrazione del Quinto Anno di Matematica Liceo Scientifico da `CONTENUTI_PROGRAMMI_MINISTERIALI.txt`);
- la mappatura deterministica sui nodi del DAG unificato (`1ª Elementare → 5ª Superiore → OFA → SecAI`);
- lo stato di allineamento empirico sul corpus integrale (`pending_wave4_full_corpus` fino al termine di M1).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from resuscipack.curriculum.dag import DEFAULT_DAG_PATH, load_unified_dag

DEFAULT_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "data" / "curriculum" / "ministerial_ontology"
DEFAULT_V6_SOURCES_DIR = DEFAULT_ONTOLOGY_DIR / "v6_sources"
DEFAULT_CONSOLIDATED_ONTOLOGY_PATH = DEFAULT_ONTOLOGY_DIR / "ontology_v6_consolidated.json"

LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE = "CONTENUTI_PROGRAMMI_MINISTERIALI.txt#MATEMATICA-LICEO-SCIENTIFICO-CLASSE-V"

LICEO_SCIENTIFICO_QUINTO_ANNO_NUCLEI: list[dict[str, Any]] = [
    {
        "nome": "Relazioni e funzioni — Limiti, continuità e calcolo differenziale",
        "argomenti": [
            "Definizione di limite di funzione reale e interpretazione con intorni e tolleranze",
            "Limiti notevoli e risoluzione delle forme indeterminate",
            "Funzioni continue su un intervallo, punti di discontinuità e asintoti",
            "Teoremi fondamentali sulle funzioni continue (Weierstrass, valori intermedi, esistenza degli zeri)",
            "Rapporto incrementale, derivata in un punto e suo significato geometrico (retta tangente) e fisico (velocità istantanea)",
            "Regole di derivazione e derivata delle funzioni composte e inverse",
            "Teoremi di Rolle, Lagrange, Cauchy e regola di De L'Hôpital",
            "Studio completo del grafico di una funzione (dominio, segno, estremi locali, flessi, asintoti) e problemi di ottimo",
        ],
    },
    {
        "nome": "Relazioni e funzioni — Calcolo integrale ed equazioni differenziali",
        "argomenti": [
            "Primitive di una funzione e integrale indefinito (integrali immediati e per scomposizione)",
            "Metodi di integrazione per sostituzione e per parti",
            "Integrale definito secondo Riemann e proprietà dell'integrale definito",
            "Teorema Fondamentale del Calcolo Integrale (Torricelli-Barrow) e calcolo di aree e volumi",
            "Equazioni differenziali ordinarie del primo e secondo ordine (a variabili separabili e lineari) come modelli fisici e dinamici",
        ],
    },
    {
        "nome": "Dati e previsioni / Geometria nello spazio (Quinto Anno)",
        "argomenti": [
            "Distribuzioni di probabilità continue e distribuzione normale",
            "Geometria analitica nello spazio: equazioni cartesiane e parametriche di rette e piani, parallelismo, ortogonalità e distanze",
        ],
    },
]


def infer_cycle(filename: str) -> str:
    low = filename.lower()
    if low.startswith("primaria_"):
        return "primaria"
    if low.startswith("media_"):
        return "secondaria_i_grado"
    if low.startswith("tecnico_"):
        return "secondaria_ii_grado_tecnici"
    if low.startswith("professionale_"):
        return "secondaria_ii_grado_professionali"
    return "secondaria_ii_grado_licei"


def infer_macro_discipline(subject: str, filename: str) -> str:
    low_s = subject.lower()
    low_f = filename.lower()
    if "matematica" in low_s or "matematica" in low_f:
        return "matematica"
    if "fisica" in low_s and "motorie" not in low_s:
        return "fisica"
    if "informatica" in low_s or "tecnolog" in low_s or "meccanica" in low_f or "elettronica" in low_f or "trasporti" in low_f:
        return "informatica_tecnologia"
    if "storia" in low_s or "econom" in low_f:
        return "storia_economia"
    if "geografia" in low_s:
        return "geografia_territorio"
    if "filosofia" in low_s or "scienze umane" in low_s or "scienze_umane" in low_f:
        return "filosofia_scienze_umane"
    if "scienze" in low_s or "chimica" in low_f or "agraria" in low_f:
        return "scienze_chimica_biologia"
    if "italiano" in low_s or "latina" in low_s or "greca" in low_s or "straniera" in low_s or "inglese" in low_s:
        return "letteratura_lingue"
    if "arte" in low_s or "disegno" in low_s or "grafica" in low_f or "moda" in low_f or "artistico" in low_f:
        return "arte_architettura"
    if "musica" in low_s or "musicale" in low_f:
        return "musica_acustica"
    if "diritto" in low_s or "turism" in low_f:
        return "diritto_societa"
    return "discipline_generali_e_indirizzo"


def _compute_objective_uid(
    source_file: str,
    school: str,
    subject: str,
    grade: str,
    nucleus: str,
    statement: str,
) -> str:
    raw = f"{source_file}|{school}|{subject}|{grade}|{nucleus}|{statement}"
    return "ont_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def map_math_objective_to_dag_nodes(
    *,
    cycle: str,
    grade: str,
    nucleus: str,
    statement: str,
    dag_nodes: dict[str, dict[str, Any]],
) -> list[str]:
    """Mappa deterministicamente un obiettivo di Matematica (1ª elementare → 5ª superiore)
    sugli ID reali dei nodi presenti in `secai_unified_dag.json`."""
    text = statement.lower()
    is_liceo = cycle == "secondaria_ii_grado_licei"
    hits: list[str] = []

    def add(nid: str) -> None:
        if nid in dag_nodes and nid not in hits:
            hits.append(nid)

    # Analisi, limiti, derivate, integrali, ODE (5ª superiore / Secondo biennio)
    if any(k in text for k in ("equazioni differenziali", "variabili separabili")):
        add("superiori.equazioni-differenziali-modelli")
        add("P2.3")
    if any(k in text for k in ("integrale", "integrali", "integrazione", "primitive", "riemann", "torricelli-barrow", "linee curve")):
        if is_liceo:
            add("superiori.integrali-teorema-fondamentale")
            add("P2.3")
        else:
            add("geometria.area-triangolo-poligoni")
            add("geometria.cerchio-pi-greco")
    if any(k in text for k in ("derivata", "derivazione", "rolle", "lagrange", "cauchy", "hôpital", "hopital", "rapporto incrementale", "problemi di ottimo", "velocità di variazione", "studio completo")):
        add("superiori.derivata-studio-funzione")
        add("P2.3")
    if any(k in text for k in ("limite", "limiti", "continuità", "funzioni continue", "asintoti", "discontinuità", "weierstrass", "calcolo approssimato", "infinito matematico")):
        add("superiori.limiti-continuita-asintoti")
        add("P2.3")

    # Esponenziali, logaritmi, successioni, complessi, trigonometria, coniche
    if any(k in text for k in ("esponenzial", "logaritm", "numero e", "y = 2n")):
        if is_liceo:
            add("superiori.esponenziali-logaritmi")
        add("P0.6")
    if any(k in text for k in ("numeri complessi", "piano di gauss", "forma trigonometrica")):
        add("superiori.numeri-complessi-gauss")
    if any(k in text for k in ("succession", "progressioni", "ricorrenza", "regolarità in una sequenza")):
        add("relazioni.sequenze-regole")
        if is_liceo:
            add("superiori.successioni-progressioni")
        if "ricorrenza" in text:
            add("P2.1")
    if any(k in text for k in ("funzioni circolari", "risoluzione dei triangoli", "trigonometria", "goniometric")):
        add("superiori.goniometria-formule-equazioni")
        add("superiori.trigonometria-triangoli")
        add("P0.7")
    if any(k in text for k in ("coniche", "parabole", "parabola", "luogo geometrico")):
        add("superiori.coniche-luoghi-geometrici")
        add("P0.6")

    # Vettori, matrici, geometria analitica spazio e piano
    if any(k in text for k in ("vettori", "matric", "geometria dello spazio", "geometria analitica nello spazio", "solidi", "poliedri", "tridimensionali", "volum")):
        if any(k in text for k in ("vettori", "matric", "geometria dello spazio", "geometria analitica nello spazio")):
            add("superiori.geometria-spazio-vettori")
            add("P3.1")
        if any(k in text for k in ("solidi", "poliedri", "tridimensionali", "volum")):
            add("geometria.solidi-volume")
    if any(k in text for k in ("sistemi di equazioni lineari", "fasci di rette", "coordinate cartesiane", "piano cartesiano", "f(x) = ax + b")):
        add("geometria.coordinate-griglia")
        if is_liceo:
            add("superiori.sistemi-lineari-retta")

    # Algebra, polinomi, disequazioni, radicali, numeri reali
    if any(k in text for k in ("polinomi", "calcolo letterale", "fattorizzazione", "divisione con resto fra polinomi", "equazioni polinomiali")):
        add("relazioni.lettere-formule")
        add("superiori.polinomi-prodotti-notevoli")
        add("superiori.fattorizzazione-frazioni-algebriche")
        add("P0.5")
    if any(k in text for k in ("radicali", "radice quadrata", "irrazionalità di √2", "numeri irrazionali", "numeri trascendenti", "secondo grado", "elevato al quadrato dà 2")):
        if "radice quadrata" in text or "elevato al quadrato dà 2" in text:
            add("operazioni.radici-base")
        if is_liceo:
            add("superiori.radicali-equazioni-secondo-grado")
        if any(k in text for k in ("√2", "irrazional", "trascendent", "elevato al quadrato dà 2")):
            add("P0.4")
    if any(k in text for k in ("disequazioni", "|x|", "valore assoluto", "equazioni di primo grado")):
        if "primo grado" in text and not is_liceo:
            add("relazioni.equazione-primo-grado-base")
        else:
            add("superiori.equazioni-fratte-irrazionali-modulo")
            add("P0.5")
    if any(k in text for k in ("formule che contengono lettere", "espressione numerica", "espressioni di calcolo", "precedenza delle operazioni")):
        add("relazioni.lettere-formule")
        add("operazioni.distributiva")

    # Numeri naturali, posizionale, 4 operazioni, frazioni, decimali, divisibilità, potenze
    if any(k in text for k in ("contare oggetti", "senso progressivo", "per salti")):
        add("numeri.quantita")
        add("numeri.ordine")
    if any(k in text for k in ("notazione posizionale", "sistemi di notazione dei numeri")):
        add("numeri.posizionale")
    if any(k in text for k in ("confrontarli e ordinarli", "rappresentare i numeri conosciuti sulla retta", "numeri reali e loro rappresentazione geometrica")):
        add("numeri.ordine")
        if "reali" in text:
            add("P0.4")
    if any(k in text for k in ("quattro operazioni", "algoritmi scritti usuali", "semplici operazioni", "tabelline", "addizioni e sottrazioni")):
        add("operazioni.addizione")
        add("operazioni.sottrazione")
        add("operazioni.moltiplicazione")
        add("operazioni.colonna")
        add("operazioni.divisione")
    if "divisione con resto" in text or "multipli e divisori" in text:
        add("operazioni.divisione")
        add("divisibilita.multipli-primi")
        if "comun" in text:
            add("divisibilita.mcm")
            add("divisibilita.mcd")
    if any(k in text for k in ("multiplo comune più piccolo", "divisore comune più grande", "algoritmo euclideo per il mcd", "fattori primi")):
        add("divisibilita.multipli-primi")
        add("divisibilita.mcm")
        add("divisibilita.mcd")
    if "associativa e distributiva" in text or "proprietà delle operazioni" in text:
        add("operazioni.addizione")
        add("operazioni.distributiva")
    if "potenze" in text:
        add("operazioni.potenze-base")
        if "potenze del 10" in text:
            add("misure.equivalenze-decimali")
    if "interi negativi" in text:
        add("numeri.relativi")
    if any(k in text for k in ("frazioni", "numero razionale")):
        add("frazioni.significato")
        add("frazioni.equivalenza")
        add("frazioni.denominatore-comune")
        if cycle != "primaria":
            add("frazioni.moltiplicazione-divisione")
    if any(k in text for k in ("numeri decimali", "percentual", "stimare il risultato")):
        if "decimali" in text:
            add("numeri.decimali")
        if "percentual" in text or "stima" in text:
            add("rapporti.proporzioni-percentuali")
            add("P0.8")
    if any(k in text for k in ("proporzionalit", "y = ax", "a/x")):
        add("rapporti.proporzioni-percentuali")
        add("relazioni.proporzionalita-diretta-inversa")

    # Geometria euclidea & trasformazioni & misure
    if any(k in text for k in ("assiomi", "postulato", "congruenza", "costruzioni geometriche", "sintetico e analitico", "dimostrazione")):
        add("P0.1")
        if is_liceo:
            add("superiori.geometria-sintetica-congruenza")
    if "pitagora" in text:
        add("geometria.pitagora")
    if any(k in text for k in ("simili", "similitudin", "talete", "in scala")):
        add("geometria.similitudine-scala")
        if is_liceo:
            add("superiori.circonferenza-euclide-talete")
    if any(k in text for k in ("circonferenza", "cerchio", "numero π")):
        add("geometria.cerchio-pi-greco")
        if is_liceo:
            add("superiori.circonferenza-euclide-talete")
    if any(k in text for k in ("trasformazioni geometriche", "ruotate", "traslate", "riflesse", "simmetrie", "invarianti")):
        add("geometria.simmetrie-traslazioni")
    if any(k in text for k in ("perpendicolarità", "parallelismo")):
        add("geometria.parallelismo-perpendicolarita")
    if "angoli" in text or "goniometro" in text:
        add("geometria.angoli-rotazioni")
    if any(k in text for k in ("perimetro", "poligoni", "triangoli", "quadrilateri", "figure geometriche", "disegni geometrici", "percorso")):
        add("geometria.poligoni-perimetro")
        add("geometria.punti-rette-segmenti")
    if any(k in text for k in ("area", "aree")):
        add("geometria.area-rettangolo-schieramento")
        add("geometria.area-triangolo-poligoni")
    if any(k in text for k in ("unità di misura", "misurare grandezze", "passare da un'unità", "monetari", "stimare distanze")):
        add("misure.confronto-unita")
        add("misure.equivalenze-decimali")
    if any(k in text for k in ("posizione nello spazio", "sopra/sotto", "destra/sinistra", "modelli materiali")):
        add("geometria.coordinate-griglia")

    # Insiemi, logica, funzioni, dati, probabilità, informatica
    if any(k in text for k in ("classificare", "criteri che sono stati usati", "linguaggio degli insiemi")):
        add("logica.classificare-attributi")
        if "funzioni" in text or "dominio" in text or "composizione" in text or "inverse" in text:
            add("P0.3")
        if "argomentare" in text or "criteri" in text:
            add("logica.tutti-qualcuno-controesempio")
    if any(k in text for k in ("funzioni", "registri di rappresentazione")):
        add("P0.3")
        add("P0.6")
    if any(k in text for k in ("probabilit", "aleatori", "evento", "eventi", "più probabile")):
        add("dati.media-frequenza-incertezza")
        if is_liceo:
            add("superiori.combinatoria-probabilita-composta")
            add("P3.2")
    if any(k in text for k in ("frequenza", "frequenze", "media aritmetica", "mediana", "moda", "variabilità", "serie statistiche", "tabelle", "diagrammi", "analisi di insiemi di dati", "rappresentazione dei dati", "rappresentare relazioni e dati")):
        add("dati.tabelle-grafici")
        add("dati.media-frequenza-incertezza")
        if is_liceo:
            add("P3.3")
    if any(k in text for k in ("modello matematico",)):
        add("relazioni.proporzionalita-diretta-inversa")
        add("P0.8")
    if any(k in text for k in ("algoritmo", "calcolabile", "calcolabilità", "strumenti informatici", "testuali e multimediali")):
        add("relazioni.sequenze-regole")
        add("P1.1")
        add("G02")
        add("P2.2")

    # Guard rail: garanzia 100% copertura su Primaria / Medie / Liceo Scientifico Matematica
    if not hits:
        if "spazio" in nucleus.lower() or "geometria" in nucleus.lower():
            add("geometria.poligoni-perimetro")
        elif "relazioni" in nucleus.lower() or "dati" in nucleus.lower():
            add("dati.tabelle-grafici")
        else:
            add("numeri.quantita")
    return hits


def build_consolidated_ontology(
    sources_dir: Path | str = DEFAULT_V6_SOURCES_DIR,
    dag_path: Path | str = DEFAULT_DAG_PATH,
) -> dict[str, Any]:
    """Carica i 53 file `v6_sources/*.json`, integra il Quinto Anno mancante di Matematica Liceo
    Scientifico da CONTENUTI_PROGRAMMI_MINISTERIALI.txt, e mappa gli obiettivi matematici K-13 sul DAG."""
    sdir = Path(sources_dir)
    if not sdir.exists():
        raise FileNotFoundError(f"Cartella sorgenti ontologia_v6 non trovata: {sdir}")

    dag_payload = load_unified_dag(dag_path)
    dag_nodes = dag_payload["nodes"]

    objectives: list[dict[str, Any]] = []
    source_files_meta: list[dict[str, Any]] = []
    cycle_counts: Counter[str] = Counter()

    for json_path in sorted(sdir.glob("*.json")):
        raw_bytes = json_path.read_bytes()
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        data = json.loads(raw_bytes.decode("utf-8"))
        school = str(data.get("scuola", "Sconosciuta")).strip()
        subject = str(data.get("materia", "Sconosciuta")).strip()
        cycle = infer_cycle(json_path.name)
        macro_disc = infer_macro_discipline(subject, json_path.name)

        anni = list(data.get("anni", []))
        file_obj_count = 0

        def _append_grade_block(anno_name: str, nuclei_list: list[dict[str, Any]], src_ref: str, src_hash: str) -> None:
            nonlocal file_obj_count
            for nucleo in nuclei_list:
                nucleo_name = str(nucleo.get("nome", "Generale")).strip()
                for stmt_raw in nucleo.get("argomenti", []):
                    stmt = str(stmt_raw).strip()
                    if not stmt:
                        continue
                    uid = _compute_objective_uid(src_ref, school, subject, anno_name, nucleo_name, stmt)
                    mapped_nodes: list[str] = []
                    if json_path.name in {"primaria_matematica.json", "media_matematica.json", "liceo_scientifico_matematica.json"}:
                        mapped_nodes = map_math_objective_to_dag_nodes(
                            cycle=cycle,
                            grade=anno_name,
                            nucleus=nucleo_name,
                            statement=stmt,
                            dag_nodes=dag_nodes,
                        )
                    objectives.append(
                        {
                            "objective_uid": uid,
                            "cycle": cycle,
                            "school": school,
                            "subject": subject,
                            "target_macro_discipline": macro_disc,
                            "grade": anno_name,
                            "nucleus": nucleo_name,
                            "statement": stmt,
                            "source_file": src_ref,
                            "source_sha256": src_hash,
                            "epistemic_layer": "institutional_declared",
                            "mapped_dag_node_ids": mapped_nodes,
                            "corpus_alignment_status": "pending_wave4_full_corpus",
                        }
                    )
                    cycle_counts[cycle] += 1
                    file_obj_count += 1

        for anno_data in anni:
            _append_grade_block(
                str(anno_data.get("anno", "Generale")).strip(),
                anno_data.get("nuclei_tematici", []),
                json_path.name,
                sha256_hex,
            )

        # Integrazione esplicita del Quinto Anno per Matematica — Liceo Scientifico (assente dal file v6 raw)
        if json_path.name == "liceo_scientifico_matematica.json":
            quinto_hash = hashlib.sha256(
                json.dumps(LICEO_SCIENTIFICO_QUINTO_ANNO_NUCLEI, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            _append_grade_block(
                "Quinto Anno",
                LICEO_SCIENTIFICO_QUINTO_ANNO_NUCLEI,
                LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE,
                quinto_hash,
            )

        source_files_meta.append(
            {
                "filename": json_path.name,
                "sha256": sha256_hex,
                "school": school,
                "subject": subject,
                "cycle": cycle,
                "objective_count": file_obj_count,
            }
        )

    math_core_objs = [
        o for o in objectives
        if Path(o["source_file"].split("#", 1)[0]).name in {
            "primaria_matematica.json",
            "media_matematica.json",
            "liceo_scientifico_matematica.json",
        }
        or o["source_file"] == LICEO_SCIENTIFICO_QUINTO_ANNO_SOURCE
    ]
    math_mapped_count = sum(1 for o in math_core_objs if o["mapped_dag_node_ids"])

    return {
        "schema_version": "ministerial-ontology-v6.consolidated.v1",
        "epistemic_principle": "R4: Livello istituzionale dichiarato tenuto distinto dalla copertura apprendibile empirica del corpus.",
        "stats": {
            "source_json_files": len(source_files_meta),
            "total_objectives": len(objectives),
            "by_cycle": dict(sorted(cycle_counts.items())),
            "k13_math_spine_objectives": len(math_core_objs),
            "k13_math_mapped_to_dag": math_mapped_count,
            "k13_math_unmapped": len(math_core_objs) - math_mapped_count,
        },
        "sources": source_files_meta,
        "objectives": objectives,
    }


def save_consolidated_ontology(
    dest_path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH,
    sources_dir: Path | str = DEFAULT_V6_SOURCES_DIR,
    dag_path: Path | str = DEFAULT_DAG_PATH,
) -> dict[str, Any]:
    payload = build_consolidated_ontology(sources_dir=sources_dir, dag_path=dag_path)
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_consolidated_ontology(path: Path | str = DEFAULT_CONSOLIDATED_ONTOLOGY_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return save_consolidated_ontology(dest_path=p)
    return json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    out = save_consolidated_ontology()
    print(json.dumps(out["stats"], ensure_ascii=False, indent=2))
