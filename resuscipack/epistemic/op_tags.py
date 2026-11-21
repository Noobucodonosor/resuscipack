"""Vocabolario chiuso delle 24 primitive operative universali (`OpTag`) e regole di dominio.

Le 24 `OpTag` costituiscono la lingua intermedia neutrale tra:
1. L'estrazione bottom-up dai libri (cieca ai programmi scolastici/universitari);
2. La ricerca top-down di "Libri Sbagliati" da parte dei nodi curricolari (SecAI, OFA, ecc.).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import FrozenSet, Iterable, List, Mapping, Sequence, Set


class OpTag(str, Enum):
    """Enum chiuso di 24 archetipi operativi universali (validato in JSON Schema)."""

    BOUNDED_TOLERANCE = "BOUNDED_TOLERANCE"
    SIGNED_DEVIATION_FEEDBACK = "SIGNED_DEVIATION_FEEDBACK"
    LATENT_STATE_SENSING = "LATENT_STATE_SENSING"
    ANGULAR_GEOMETRY_PROJECTION = "ANGULAR_GEOMETRY_PROJECTION"
    SERIES_CONJUNCTION_GATE = "SERIES_CONJUNCTION_GATE"
    PARALLEL_DISJUNCTION_PATH = "PARALLEL_DISJUNCTION_PATH"
    VARIABLE_ISOLATION_CONTROL = "VARIABLE_ISOLATION_CONTROL"
    HIDDEN_CONFOUNDER = "HIDDEN_CONFOUNDER"
    COMBINATORIAL_GRID_PATTERN = "COMBINATORIAL_GRID_PATTERN"
    CONSTRAINED_SEARCH_DECODING = "CONSTRAINED_SEARCH_DECODING"
    ORDER_OF_MAGNITUDE_BOUND = "ORDER_OF_MAGNITUDE_BOUND"
    PROPORTIONAL_SCALING = "PROPORTIONAL_SCALING"
    RATE_OF_CHANGE = "RATE_OF_CHANGE"
    ACCUMULATION_INTEGRATION = "ACCUMULATION_INTEGRATION"
    INVARIANT_PRESERVATION = "INVARIANT_PRESERVATION"
    BIJECTION_EQUINUMEROSITY = "BIJECTION_EQUINUMEROSITY"
    RECURSIVE_SELF_SIMILARITY = "RECURSIVE_SELF_SIMILARITY"
    CONTRADICTION_REDUCTIO = "CONTRADICTION_REDUCTIO"
    MODULAR_PERIODICITY = "MODULAR_PERIODICITY"
    PROBABILITY_BAYESIAN_UPDATE = "PROBABILITY_BAYESIAN_UPDATE"
    SIGNAL_TRANSDUCTION_ECHO = "SIGNAL_TRANSDUCTION_ECHO"
    BOTTLENECK_CAPACITY = "BOTTLENECK_CAPACITY"
    ADVERSARIAL_DECEPTION = "ADVERSARIAL_DECEPTION"
    THRESHOLD_PHASE_TRANSITION = "THRESHOLD_PHASE_TRANSITION"


OP_TAG_DESCRIPTIONS: Mapping[OpTag, str] = {
    OpTag.BOUNDED_TOLERANCE: "Passaggio o mantenimento entro un margine/varco simmetrico attorno a un riferimento.",
    OpTag.SIGNED_DEVIATION_FEEDBACK: "Correzione iterativa guidata da uno scostamento scalare dotato di segno/verso.",
    OpTag.LATENT_STATE_SENSING: "Guida o inferenza in assenza di visibilità diretta tramite misura indiretta.",
    OpTag.ANGULAR_GEOMETRY_PROJECTION: "Fasci direzionali, focalizzazione parabolica, coni angolari e proiezioni.",
    OpTag.SERIES_CONJUNCTION_GATE: "Continuità tutto-o-niente lungo una catena di elementi disposti in serie.",
    OpTag.PARALLEL_DISJUNCTION_PATH: "Percorsi alternativi ridondanti in cui basta un ramo attivo per la continuità.",
    OpTag.VARIABLE_ISOLATION_CONTROL: "Isolamento sperimentale mutando una sola condizione e fissando la baseline.",
    OpTag.HIDDEN_CONFOUNDER: "Variabile latente non controllata che simula una falsa relazione causale.",
    OpTag.COMBINATORIAL_GRID_PATTERN: "Configurazioni regolari generate da regole d'intreccio su griglie discrete 2D.",
    OpTag.CONSTRAINED_SEARCH_DECODING: "Decodifica o enumerazione ordinata di congetture con esclusione dei rami invalidi.",
    OpTag.ORDER_OF_MAGNITUDE_BOUND: "Stima quantitativa di fattibilità fisica o energetica per ordini di grandezza.",
    OpTag.PROPORTIONAL_SCALING: "Variazione in rapporto costante o inverso tra grandezze accoppiate.",
    OpTag.RATE_OF_CHANGE: "Rapidità istantanea di variazione locale di una grandezza nel tempo o nello spazio.",
    OpTag.ACCUMULATION_INTEGRATION: "Somma progressiva di contributi elementari o indivisibili fino al totale.",
    OpTag.INVARIANT_PRESERVATION: "Quantità o struttura che resta immutata attraverso trasformazioni successive.",
    OpTag.BIJECTION_EQUINUMEROSITY: "Accoppiamento uno-a-uno senza resti né collisioni tra collezioni distinte.",
    OpTag.RECURSIVE_SELF_SIMILARITY: "Riduzione di un problema a sottoproblemi omologhi più piccoli fino al caso base.",
    OpTag.CONTRADICTION_REDUCTIO: "Confutazione di un'ipotesi derivandone una conseguenza incompatibile coi vincoli.",
    OpTag.MODULAR_PERIODICITY: "Ciclicità con ritorno allo stato equivalente dopo un periodo o modulo fisso.",
    OpTag.PROBABILITY_BAYESIAN_UPDATE: "Revisione del grado di fiducia su un'ipotesi alla luce di un indizio raro/rumoroso.",
    OpTag.SIGNAL_TRANSDUCTION_ECHO: "Conversione tra domini fisici diversi o misura di distanza tramite tempo di ritorno.",
    OpTag.BOTTLENECK_CAPACITY: "Limite massimo di flusso imposto dalla sezione o risorsa più stretta.",
    OpTag.ADVERSARIAL_DECEPTION: "Manipolazione intenzionale dei segnali osservati per indurre una falsa inferenza.",
    OpTag.THRESHOLD_PHASE_TRANSITION: "Cambio brusco di regime al superamento critico di un parametro continuo.",
}

ALL_OP_TAGS: FrozenSet[str] = frozenset(tag.value for tag in OpTag)

# Sostantivi concreti aneddotici vietati in `sig.mech` (regola `domain_stripping`):
# la firma strutturale deve descrivere il meccanismo astratto senza restare intrappolata
# nel lessico pittoresco dell'episodio (es. panfilo, boe, rana, ricamatrice).
DEFAULT_FORBIDDEN_SURFACE_NOUNS: FrozenSet[str] = frozenset(
    {
        "panfilo",
        "elettra",
        "marconi",
        "santa margherita",
        "boa",
        "boe",
        "oblò",
        "oblo",
        "marinaio",
        "rana",
        "rane",
        "zampe",
        "zampa",
        "midollo",
        "galvani",
        "rialpo",
        "ringhiera",
        "ringhiere",
        "capsula",
        "ricamatrice",
        "ricamatrici",
        "tessitore",
        "tessitori",
        "tappeto",
        "tappeti",
        "telaio",
        "pecora",
        "mussolini",
        "ovra",
    }
)

# Mappa dei domini canonici da escludere quando si cerca un "Libro Sbagliato"
# per una famiglia disciplinare target.
CANONICAL_DISCIPLINE_EXCLUSIONS: Mapping[str, FrozenSet[str]] = {
    "matematica": frozenset(
        {
            "matematica",
            "analisi matematica",
            "algebra",
            "geometria",
            "logica matematica",
            "probabilità e statistica",
            "matematica, logica e geometria",
        }
    ),
    "informatica": frozenset(
        {
            "informatica",
            "sicurezza informatica",
            "algoritmi",
            "programmazione",
            "ingegneria del software",
            "reti di calcolatori",
            "intelligenza artificiale",
            "machine learning",
            "crittografia",
        }
    ),
    "fisica": frozenset(
        {
            "fisica",
            "fisica_ingegneria",
        }
    ),
}


def validate_op_tags(raw_tags: Sequence[str]) -> List[OpTag]:
    """Valida una lista di `1..3` `OpTag` distinti mantenendo l'ordine."""
    if not isinstance(raw_tags, (list, tuple)) or not (1 <= len(raw_tags) <= 3):
        raise ValueError("op_tags deve contenere tra 1 e 3 tag validi dall'Enum OpTag")
    resolved: List[OpTag] = []
    seen: Set[OpTag] = set()
    for item in raw_tags:
        try:
            tag = item if isinstance(item, OpTag) else OpTag(str(item).strip())
        except ValueError as exc:
            raise ValueError(f"op_tag non ammesso fuori dall'Enum dei 24: {item!r}") from exc
        if tag not in seen:
            seen.add(tag)
            resolved.append(tag)
    return resolved


def find_forbidden_surface_terms(
    mech_text: str,
    extra_forbidden: Iterable[str] = (),
) -> List[str]:
    """Restituisce i termini di superficie vietati presenti in `sig.mech`."""
    lowered = mech_text.casefold()
    forbidden = set(DEFAULT_FORBIDDEN_SURFACE_NOUNS)
    for term in extra_forbidden:
        cleaned = str(term or "").strip().casefold()
        if len(cleaned) >= 4:
            forbidden.add(cleaned)
    hits: List[str] = []
    for term in sorted(forbidden):
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lowered):
            hits.append(term)
    return hits


def canonical_exclusions_for(target_area: str) -> FrozenSet[str]:
    """Restituisce l'insieme dei `surface_domain` canonici da escludere per l'inversione."""
    key = target_area.strip().casefold()
    if key in {"secai", "stem_math_cs", "math_cs"}:
        return CANONICAL_DISCIPLINE_EXCLUSIONS["matematica"] | CANONICAL_DISCIPLINE_EXCLUSIONS["informatica"]
    return CANONICAL_DISCIPLINE_EXCLUSIONS.get(key, frozenset({key}))
