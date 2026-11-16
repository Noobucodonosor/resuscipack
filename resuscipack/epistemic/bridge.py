"""Motore di Inversione Disciplinare ("Il Libro Sbagliato") e gestione `curiosity_bridges`.

Implementa il Ponte Simmetrico a 3 Stadi (ADR-0002, TASK-EPIST-03):
1. Query di inversione vincolata su `structural_signatures` (`surface_domain NOT IN canonical_domains`
   + intersezione sugli `OpTag` + ranking lessicale/strutturale sul meccanismo de-lessicalizzato);
2. Validazione rigorosa a 3 passi inferenziali + mappatura 1-a-1 delle grandezze prima di scrivere
   in `curiosity_bridges` (zero analogie decorative);
3. Seed deterministico e idempotente dei 3 casi empirici reali verificati sul corpus:
   - Marconi a Santa Margherita Ligure (navigazione cieca tra due boe a 50 m + riflettore parabolico);
   - Galvani, la stanza chiusa e la catena umana con Rialpo (congiunzione in serie + confounder);
   - Cartesio, Regola X (tessitori/ricamatrici su griglia discreta + decifrazione scrittura velata).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .op_tags import OpTag, canonical_exclusions_for, validate_op_tags
from .schema_v21 import (
    normalizza_testo,
    persist_block_extraction,
    validate_block_extraction,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pack_corpus.db"


@dataclass(frozen=True)
class GeneratorArchetype:
    """Archetipo pre-formale dichiarato lato nodo curricolare per pescare Libri Sbagliati."""

    node_id: str
    canonical_domains: Tuple[str, ...]
    target_op_tags: Tuple[OpTag, ...]
    generator_query: str


@dataclass(frozen=True)
class WrongBookCandidate:
    block_pk: int
    block_uid: str
    book_title: str
    author: Optional[str]
    year: Optional[int]
    surface_domain: str
    page_start: Optional[int]
    printed_page: Optional[str]
    mech: str
    op_tags: Tuple[str, ...]
    anti_sudoku_role: str
    score: float
    content: str


def _tokenize_structural(text: str) -> set[str]:
    stop = {
        "della", "delle", "degli", "dallo", "dalla", "nella", "nello", "nelle",
        "con", "per", "tra", "fra", "una", "uno", "gli", "che", "non", "più",
        "come", "solo", "modo", "ogni", "suo", "sua", "loro", "verso", "sulla",
    }
    return {
        w
        for w in re.findall(r"[a-zà-öø-ÿ0-9]{4,}", normalizza_testo(text))
        if w not in stop
    }


def find_wrong_book_candidates(
    conn: sqlite3.Connection,
    archetype: GeneratorArchetype,
    *,
    limit: int = 30,
) -> List[WrongBookCandidate]:
    """Esegue la query di Inversione Disciplinare Vincolata su `pack_corpus.db`."""
    if limit < 1:
        return []
    conn.row_factory = sqlite3.Row
    target_tags = {t.value for t in validate_op_tags(archetype.target_op_tags)}
    excluded: set[str] = set()
    for dom in archetype.canonical_domains:
        excluded.add(dom.strip().casefold())
        excluded.update(canonical_exclusions_for(dom))

    placeholders = ",".join("?" for _ in sorted(excluded)) if excluded else "''"
    sql = f"""
        SELECT
            bl.block_pk,
            bl.block_uid,
            bl.book_title,
            bk.author,
            bk.year,
            bk.surface_domain,
            bl.page_start,
            bl.printed_page,
            bl.content,
            ss.mech,
            ss.op_tags_json,
            ss.anti_sudoku_role
        FROM structural_signatures ss
        JOIN blocks bl ON bl.block_pk = ss.block_pk
        JOIN books bk ON bk.book_pk = bl.book_pk
        WHERE bl.is_active = 1
          AND bk.is_active = 1
          AND lower(bk.surface_domain) NOT IN ({placeholders})
    """
    params = tuple(sorted(excluded)) if excluded else ()
    rows = conn.execute(sql, params).fetchall()

    q_tokens = _tokenize_structural(archetype.generator_query)
    candidates: List[WrongBookCandidate] = []
    for row in rows:
        row_tags = tuple(json.loads(row["op_tags_json"] or "[]"))
        overlap_tags = target_tags.intersection(row_tags)
        if not overlap_tags:
            continue

        tag_score = len(overlap_tags) / max(len(target_tags), 1)
        m_tokens = _tokenize_structural(row["mech"])
        lex_overlap = (
            len(q_tokens & m_tokens) / max(len(q_tokens), 1) if q_tokens else 0.0
        )
        # Punteggio composito in [0, 1] ancorato a coincidenza strutturale sugli OpTag + meccanismo
        composite_score = round(min(1.0, 0.65 * tag_score + 0.35 * min(1.0, lex_overlap * 2.5)), 4)

        candidates.append(
            WrongBookCandidate(
                block_pk=int(row["block_pk"]),
                block_uid=str(row["block_uid"]),
                book_title=str(row["book_title"] or ""),
                author=row["author"],
                year=row["year"],
                surface_domain=str(row["surface_domain"]),
                page_start=row["page_start"],
                printed_page=row["printed_page"],
                mech=str(row["mech"]),
                op_tags=row_tags,
                anti_sudoku_role=str(row["anti_sudoku_role"]),
                score=composite_score,
                content=str(row["content"]),
            )
        )

    candidates.sort(key=lambda c: (-c.score, c.block_pk))
    return candidates[:limit]


def validate_and_upsert_bridge(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    block_pk: int,
    target_op_tags: Sequence[str | OpTag],
    mapping: Mapping[str, str],
    chain_steps: Sequence[str],
    score: float,
    status: str = "validated",
) -> int:
    """Valida l'invariante non-decorativo (mappatura >= 2 grandezze, catena >= 3 passi)
    e inserisce/aggiorna il record in `curiosity_bridges`."""
    node_clean = str(node_id or "").strip()
    if not node_clean:
        raise ValueError("node_id non può essere vuoto")

    resolved_tags = [t.value for t in validate_op_tags(target_op_tags)]

    if not isinstance(mapping, Mapping):
        raise ValueError("mapping deve essere un dizionario {grandezza_fisica: grandezza_formale}")
    cleaned_map = {
        " ".join(str(k).split()).strip(): " ".join(str(v).split()).strip()
        for k, v in mapping.items()
        if str(k).strip() and str(v).strip()
    }
    if len(cleaned_map) < 2:
        raise ValueError(
            "Ponte rifiutato (anti-analogia decorativa): servono almeno 2 corrispondenze 1-a-1 in mapping"
        )

    cleaned_steps = [" ".join(str(s).split()).strip() for s in chain_steps if len(str(s).strip()) >= 12]
    if len(cleaned_steps) < 3:
        raise ValueError(
            f"Ponte rifiutato (invariante ofa_epistemic): servono almeno 3 passaggi inferenziali (trovati {len(cleaned_steps)})"
        )

    if not (0.0 <= float(score) <= 1.0):
        raise ValueError(f"score deve essere compreso tra 0.0 e 1.0 (ricevuto {score})")
    if status not in {"validated", "candidate", "rejected_decorative"}:
        raise ValueError(f"status ponte non valido: {status!r}")

    row = conn.execute(
        "SELECT block_pk, is_active FROM blocks WHERE block_pk = ?", (block_pk,)
    ).fetchone()
    if row is None or int(row[1]) != 1:
        raise ValueError(f"block_pk={block_pk} inesistente o non attivo in blocks")

    conn.execute(
        """
        INSERT INTO curiosity_bridges (
            node_id, block_pk, target_op_tags_json, mapping_json,
            chain_steps_json, score, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id, block_pk) DO UPDATE SET
            target_op_tags_json = excluded.target_op_tags_json,
            mapping_json = excluded.mapping_json,
            chain_steps_json = excluded.chain_steps_json,
            score = excluded.score,
            status = excluded.status
        """,
        (
            node_clean,
            int(block_pk),
            json.dumps(resolved_tags, ensure_ascii=False),
            json.dumps(cleaned_map, ensure_ascii=False),
            json.dumps(cleaned_steps, ensure_ascii=False),
            round(float(score), 4),
            status,
        ),
    )
    bridge_row = conn.execute(
        "SELECT bridge_pk FROM curiosity_bridges WHERE node_id = ? AND block_pk = ?",
        (node_clean, int(block_pk)),
    ).fetchone()
    return int(bridge_row[0])


def get_bridges_for_node(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    only_validated: bool = True,
    prefix_fallback: bool = True,
) -> List[Dict[str, Any]]:
    """Restituisce i ponti 'Libro Sbagliato' arricchiti coi metadati del blocco e del volume."""
    conn.row_factory = sqlite3.Row
    status_clause = "AND cb.status = 'validated'" if only_validated else ""
    base_sql = f"""
        SELECT
            cb.bridge_pk,
            cb.node_id,
            cb.block_pk,
            bl.block_uid,
            bl.book_title,
            bk.author,
            bk.year,
            bk.surface_domain,
            bl.page_start,
            bl.page_end,
            bl.printed_page,
            bl.content,
            ss.mech,
            ss.anti_sudoku_role,
            cb.target_op_tags_json,
            cb.mapping_json,
            cb.chain_steps_json,
            cb.score,
            cb.status
        FROM curiosity_bridges cb
        JOIN blocks bl ON bl.block_pk = cb.block_pk
        JOIN books bk ON bk.book_pk = bl.book_pk
        LEFT JOIN structural_signatures ss ON ss.block_pk = bl.block_pk
        WHERE bl.is_active = 1
          {status_clause}
    """
    rows = conn.execute(
        base_sql + " AND cb.node_id = ? ORDER BY cb.score DESC, cb.bridge_pk ASC",
        (node_id,),
    ).fetchall()

    if not rows and prefix_fallback and "." in node_id:
        prefix = node_id.rsplit(".", 1)[0]
        rows = conn.execute(
            base_sql + " AND (cb.node_id = ? OR cb.node_id LIKE ?) ORDER BY cb.score DESC",
            (prefix, f"{prefix}.%"),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "bridge_pk": int(r["bridge_pk"]),
                "node_id": r["node_id"],
                "block_pk": int(r["block_pk"]),
                "block_uid": r["block_uid"],
                "book_title": r["book_title"],
                "author": r["author"],
                "year": r["year"],
                "surface_domain": r["surface_domain"],
                "page_start": r["page_start"],
                "page_end": r["page_end"],
                "printed_page": r["printed_page"],
                "content": r["content"],
                "mech": r["mech"],
                "anti_sudoku_role": r["anti_sudoku_role"],
                "target_op_tags": json.loads(r["target_op_tags_json"] or "[]"),
                "mapping": json.loads(r["mapping_json"] or "{}"),
                "chain_steps": json.loads(r["chain_steps_json"] or "[]"),
                "score": float(r["score"]),
                "status": r["status"],
            }
        )
    return out


def _find_active_block_by_anchor(
    conn: sqlite3.Connection,
    title_substr: str,
    verbatim_anchor: str,
) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    norm_anchor = normalizza_testo(verbatim_anchor)
    rows = conn.execute(
        """
        SELECT block_pk, block_uid, book_title, content, norm_content
        FROM blocks
        WHERE is_active = 1
          AND lower(book_title) LIKE ?
          AND instr(norm_content, ?) > 0
        ORDER BY block_pk ASC
        LIMIT 1
        """,
        (f"%{title_substr.lower()}%", norm_anchor),
    ).fetchall()
    return rows[0] if rows else None


def seed_verified_empirical_bridges(db_or_conn: Path | str | sqlite3.Connection = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """ Popola in modo idempotente e verificato (zero leakage, 100% verbatim) i 3 casi empirici
    cardine (Marconi a Santa Margherita, Galvani & Rialpo, Cartesio Regola X) dentro `pack_corpus.db`.
    """
    owns_conn = not isinstance(db_or_conn, sqlite3.Connection)
    conn = sqlite3.connect(str(db_or_conn)) if owns_conn else db_or_conn
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    specs: List[Dict[str, Any]] = [
        {
            "key": "marconi_santa_margherita",
            "title_hint": "marconi",
            "anchor": "due boe di traguardo, poste a cinquanta metri l'una dall'altra",
            "extraction": {
                "yield": "high",
                "units": [
                    {
                        "kind": "exp",
                        "mode": "narrates",
                        "stmt": (
                            "Il 30 giugno 1934 nel mare di Santa Margherita Ligure Guglielmo Marconi e "
                            "Gaston-Antoine Mathieu guidano il panfilo Elettra con gli oblò accecati attraverso "
                            "due boe poste a 50 metri usando solo la lancetta di un ricevitore per radio-faro."
                        ),
                        "quote": "L'esperimento ebbe luogo il 30 giugno 1934 nel mare di Santa Margherita Ligure.",
                        "who": ["Guglielmo Marconi", "Gaston-Antoine Mathieu", "Arthur Compton"],
                        "vs": "Navigazione marittima dipendente dalla visibilità ottica diretta",
                        "concepts": ["radionavigazione cieca", "radio-faro", "Santa Margherita Ligure"],
                    },
                    {
                        "kind": "exp",
                        "mode": "applies",
                        "stmt": (
                            "Dopo giri e cambiamenti di rotta, il panfilo Elettra passa tre volte tra le due "
                            "boe dimostrando di poter riacquisire i segnali del radio-faro da qualunque posizione."
                        ),
                        "quote": "da qualunque posizione fosse possibile « riacquisire » i segnali del radio-faro",
                        "who": ["Guglielmo Marconi"],
                        "vs": None,
                        "concepts": ["riacquisizione del segnale", "correzione di rotta"],
                    },
                ],
                "sig": {
                    "op_tags": [
                        "BOUNDED_TOLERANCE",
                        "SIGNED_DEVIATION_FEEDBACK",
                        "LATENT_STATE_SENSING",
                    ],
                    "role": "embodied_intuition",
                    "mech": (
                        "Guida cieca di un punto mobile attraverso un varco di larghezza fissa (50 m) "
                        "azzerando lo scostamento indicato da uno strumento scalare e recuperando l'asse "
                        "di riferimento da posizioni iniziali arbitrarie."
                    ),
                },
            },
            "bridges": [
                {
                    "node_id": "P0.5",
                    "target_op_tags": ["BOUNDED_TOLERANCE", "SIGNED_DEVIATION_FEEDBACK"],
                    "mapping": {
                        "Rotta centrale del radio-faro": "Centro di riferimento x0",
                        "Semidistanza tra le due boe (25 m su 50 m totali)": "Raggio di tolleranza delta > 0",
                        "Scostamento laterale della lancetta": "Errore con segno (x - x0)",
                        "Passaggio nel varco tra le boe": "Disequazione con valore assoluto |x - x0| < 25",
                    },
                    "chain_steps": [
                        "1. Nel mare di Santa Margherita Ligure due boe distanti 50 metri fissano un varco simmetrico di ±25 metri attorno alla rotta ideale del radio-faro.",
                        "2. Con gli oblò accecati, il timoniere non osserva la posizione assoluta ma legge solo lo scostamento con segno sulla lancetta e corregge la rotta finché l'errore rientra nel margine.",
                        "3. Questa condizione fisica traduce esattamente la disequazione |x - x0| < 25, mostrando perché il valore assoluto separa l'ampiezza dell'errore dal lato (destro/sinistro) dello scarto.",
                    ],
                    "score": 0.96,
                },
                {
                    "node_id": "P0.7",
                    "target_op_tags": ["ANGULAR_GEOMETRY_PROJECTION", "BOUNDED_TOLERANCE"],
                    "mapping": {
                        "Distanza dal radio-faro in collina": "Cateto adiacente D",
                        "Semivarco di 25 metri tra le boe": "Cateto opposto r = 25 m",
                        "Cono utile di allineamento radio": "Angolo sotteso 2 * arctan(25 / D)",
                    },
                    "chain_steps": [
                        "1. Il radio-faro installato sulla collina di Santa Margherita proietta un fascio direzionale verso il varco di 50 metri in mare.",
                        "2. A distanza D dalla sorgente, metà varco (25 m) sottende un angolo theta tale che tan(theta) = 25 / D.",
                        "3. All'aumentare della distanza D l'angolo utile decresce come arctan(25/D), rendendo tangibile il legame tra rapporti trigonometrici e sensibilità angolare.",
                    ],
                    "score": 0.89,
                },
                {
                    "node_id": "numeri.relativi",
                    "target_op_tags": ["SIGNED_DEVIATION_FEEDBACK"],
                    "mapping": {
                        "Posizione centrale della lancetta": "Lo zero (0) sulla retta orientata",
                        "Deviazione a sinistra vs a destra della rotta": "Segno negativo (-) vs segno positivo (+) dello scostamento",
                    },
                    "chain_steps": [
                        "1. Sul ponte oscurato dell'Elettra non basta sapere di quanti metri si è fuori rotta: occorre sapere da quale lato per accostare nel verso opposto.",
                        "2. La lancetta dell'indicatore radio distingue due versi opposti attorno allo zero centrale di allineamento.",
                        "3. I numeri relativi nascono esattamente per codificare grandezze dotate di verso rispetto a un punto di riferimento.",
                    ],
                    "score": 0.92,
                },
            ],
        },
        {
            "key": "galvani_catena_rialpo",
            "title_hint": "galvani",
            "anchor": "si formasse come una specie di catena elettrica",
            "extraction": {
                "yield": "high",
                "units": [
                    {
                        "kind": "exp",
                        "mode": "applies",
                        "stmt": (
                            "Luigi Galvani e lo spagnolo Rialpo osservano che le contrazioni si producono "
                            "solo quando le loro mani sono congiunte a chiudere la catena tra midollo e capsula "
                            "d'argento, e cessano appena disgiungono le mani."
                        ),
                        "quote": "il quale cessava se noi disgiungevamo le mani e tornava a manifestarsi se noi le ricongiungevamo.",
                        "who": ["Luigi Galvani", "Rialpo"],
                        "vs": None,
                        "concepts": ["catena conduttrice in serie", "circuito chiuso"],
                    },
                    {
                        "kind": "exp",
                        "mode": "proves",
                        "stmt": (
                            "Interponendo tra Luigi Galvani e Rialpo una bacchetta di metallo il fenomeno "
                            "persiste, mentre interponendo una bacchetta di vetro (corpo coibente) scompare del tutto."
                        ),
                        "quote": "interponendo ora un corpo coibente, per esempio una bacchetta di vetro, ora un corpo conduttore, per esempio una bacchetta di metallo",
                        "who": ["Luigi Galvani", "Rialpo"],
                        "vs": "Ipotesi di azione puramente meccanica urtando la capsula",
                        "concepts": ["conduttore vs isolante", "controllo sperimentale"],
                    },
                ],
                "sig": {
                    "op_tags": [
                        "SERIES_CONJUNCTION_GATE",
                        "VARIABLE_ISOLATION_CONTROL",
                    ],
                    "role": "fertile_error",
                    "mech": (
                        "Attivazione binaria tutto-o-niente lungo una catena di elementi in serie verificata "
                        "ripristinando la baseline a singolo operatore e sostituendo un anello intermedio con "
                        "un mezzo trasmissivo (1) contro uno bloccante (0)."
                    ),
                },
            },
            "bridges": [
                {
                    "node_id": "P0.2",
                    "target_op_tags": ["SERIES_CONJUNCTION_GATE", "VARIABLE_ISOLATION_CONTROL"],
                    "mapping": {
                        "Contatto mano Galvani + anello intermedio + contatto Rialpo": "Variabili proposizionali in serie A, B, C",
                        "Bacchetta metallica vs bacchetta di vetro": "Valore di verità 1 (vero/chiuso) vs 0 (falso/aperto)",
                        "Contrazione osservata vs assenza di contrazione": "Uscita della congiunzione logica A AND B AND C",
                    },
                    "chain_steps": [
                        "1. Nella prova a due persone di Galvani e Rialpo il fenomeno scompare finché i due non chiudono fisicamente tutti gli anelli del cammino in serie.",
                        "2. Sostituendo un singolo anello con vetro (stato 0) l'intero effetto si annulla anche colpendo più forte la capsula, mentre col metallo (stato 1) si riattiva.",
                        "3. Il circuito in serie materializza fisicamente la tavola di verità della congiunzione logica AND (basta un solo ingresso falso per annullare l'uscita), ponte diretto verso Boole e le porte logiche di Computing Systems.",
                    ],
                    "score": 0.95,
                },
                {
                    "node_id": "P5.2",
                    "target_op_tags": ["VARIABLE_ISOLATION_CONTROL"],
                    "mapping": {
                        "Rifare subito da solo l'esperimento funzionante": "Ripristino della regression baseline nota",
                        "Sostituzione del solo giunto centrale metallo/vetro": "Fault isolation cambiando una sola variabile alla volta",
                    },
                    "chain_steps": [
                        "1. Quando la variante a due operatori con Rialpo fallisce contro ogni aspettativa, Galvani non altera più parametri insieme ma ripete subito da solo la prova base per confermare che il sistema sia ancora integro.",
                        "2. Verificata la baseline, reintroduce il secondo operatore isolando l'ipotesi di continuità tramite un test positivo (bacchetta metallica) e un test negativo (bacchetta di vetro).",
                        "3. Questa sequenza costituisce la struttura esatta del debugging scientifico e dei test di regressione/isolamento del guasto nell'ingegneria del software.",
                    ],
                    "score": 0.90,
                },
                {
                    "node_id": "logica.vero-falso-non-e-o",
                    "target_op_tags": ["SERIES_CONJUNCTION_GATE"],
                    "mapping": {
                        "Mani congiunte / bacchetta metallica": "Enunciato VERO (contatto chiuso)",
                        "Mani disgiunte / bacchetta di vetro": "Enunciato FALSO (contatto aperto)",
                        "Contrazione osservata": "Risultato del connettivo 'E' (tutti veri)",
                    },
                    "chain_steps": [
                        "1. Galvani e Rialpo formano una catena in cui ciascun giunto può essere chiuso (conduttore) oppure interrotto (aria o vetro).",
                        "2. Basta interrompere un solo giunto della catena perché il fenomeno cessi completamente.",
                        "3. È il modello fisico elementare del connettivo logico E (congiunzione): l'enunciato composto è vero solo quando tutte le condizioni in serie sono vere.",
                    ],
                    "score": 0.93,
                },
            ],
        },
        {
            "key": "cartesio_regola_x",
            "title_hint": "descartes",
            "anchor": "leggere una scrittura velata dai caratteri sconosciuti",
            "extraction": {
                "yield": "high",
                "units": [
                    {
                        "kind": "proc",
                        "mode": "applies",
                        "stmt": (
                            "Nella Regola X René Descartes invita a studiare le arti in cui regna un ordine "
                            "regolare, come l'intreccio di fili in orditi diversi e le combinazioni dell'Aritmetica."
                        ),
                        "quote": "intrecciano in infiniti modi i fili in orditi diversi; così come tutte le combinazioni di numeri",
                        "who": ["René Descartes"],
                        "vs": None,
                        "concepts": ["ordine combinatorio", "pattern regolari", "aritmetica"],
                    },
                    {
                        "kind": "proc",
                        "mode": "defines",
                        "stmt": (
                            "Per decifrare una scrittura velata da caratteri sconosciuti René Descartes "
                            "prescrive di inventare un ordine sistematico per esaminare per enumerazione tutte "
                            "le congetture possibili, evitando di tirare a indovinare a caso e senza regola."
                        ),
                        "quote": "leggere una scrittura velata dai caratteri sconosciuti, non vi scorgiamo alcun ordine, ma ne inventiamo uno",
                        "who": ["René Descartes"],
                        "vs": "Indovinare a caso senza regola e sillogistica sterile dei Dialettici",
                        "concepts": ["enumerazione ordinata", "decifrazione di caratteri ignoti", "metodo"],
                    },
                ],
                "sig": {
                    "op_tags": [
                        "CONSTRAINED_SEARCH_DECODING",
                        "COMBINATORIAL_GRID_PATTERN",
                    ],
                    "role": "genesis_problem",
                    "mech": (
                        "Generazione di pattern regolari su griglie discrete d'intreccio e decodifica di "
                        "sequenze di simboli ignoti imponendo un ordinamento ipotetico per enumerare ed "
                        "escludere con metodo le congetture anziché procedere per tentativi casuali."
                    ),
                },
            },
            "bridges": [
                {
                    "node_id": "P4.1",
                    "target_op_tags": ["CONSTRAINED_SEARCH_DECODING"],
                    "mapping": {
                        "Scrittura velata da caratteri sconosciuti": "Testo cifrato (ciphertext) su alfabeto sostituito",
                        "Indovinare a caso e senza regola": "Ricerca casuale / brute-force non strutturato nello spazio delle chiavi",
                        "Inventare un ordine per esaminare congetture su lettere e parole": "Crittanalisi guidata da vincoli strutturali ed enumerazione con pruning",
                    },
                    "chain_steps": [
                        "1. Di fronte a una sequenza di caratteri ignoti apparentemente priva di ordine, tirare a indovinare a caso collassa per l'esplosione combinatoria delle sostituzioni possibili.",
                        "2. Cartesio mostra che la soluzione consiste nell'imporre un ordine di enumerazione sulle congetture relative a singole lettere e parole per dedurre sistematicamente ciò che è compatibile.",
                        "3. Questo principio fonda sia la crittanalisi classica contro i cifrari monoalfabetici sia la distinzione informatica tra enumerazione sistematica con vincoli (backtracking) e tentativi random.",
                    ],
                    "score": 0.94,
                },
                {
                    "node_id": "P2.2",
                    "target_op_tags": ["COMBINATORIAL_GRID_PATTERN", "CONSTRAINED_SEARCH_DECODING"],
                    "mapping": {
                        "Fili intrecciati in orditi diversi": "Griglia discreta bidimensionale M[i, j] governata da regole periodiche",
                        "Enumerazione ordinata delle combinazioni": "Esplorazione combinatoria esaustiva senza ripetizioni",
                    },
                    "chain_steps": [
                        "1. L'intreccio di trama e ordito descritto nella Regola X genera un'infinità di disegni distinti applicando poche regole periodiche di scavalcamento dei fili.",
                        "2. Ogni incrocio (riga i, colonna j) assume uno stato binario (sopra/sotto), trasformando un mestiere artigianale in una struttura combinatoria discreta isomorfa alle matrici binarie.",
                        "3. È la stessa astrazione matematica del discreto che collegherà storicamente i telai a schede perforate di Jacquard al calcolo automatico.",
                    ],
                    "score": 0.91,
                },
                {
                    "node_id": "geometria.coordinate-griglia",
                    "target_op_tags": ["COMBINATORIAL_GRID_PATTERN"],
                    "mapping": {
                        "Fili verticali dell'ordito e orizzontali della trama": "Coppia di coordinate (colonna x, riga y) sulla griglia",
                        "Regola del punto di ricamo": "Legge che associa a ogni nodo (x, y) il passaggio del filo",
                    },
                    "chain_steps": [
                        "1. Nel telaio e nel ricamo citati da Cartesio, ogni punto del disegno è individuato dall'incrocio tra un filo d'ordito e uno di trama.",
                        "2. Contare i fili nelle due direzioni permette di riprodurre qualsiasi figura complessa tramite sole coppie di numeri interi.",
                        "3. La griglia artigianale anticipa concretamente l'idea di coordinate cartesiane sul piano.",
                    ],
                    "score": 0.90,
                },
            ],
        },
        {
            "key": "marconi_riflettore_parabolico",
            "optional": True,
            "title_hint": "marconi",
            "anchor": "in un simile riflettore, posto sul panfilo Elettra",
            "extraction": {
                "yield": "high",
                "units": [
                    {
                        "kind": "exp",
                        "mode": "applies",
                        "stmt": (
                            "Con un riflettore a fascio concentrato posto a cinque metri sul mare, i segnali "
                            "vengono ricevuti con regolarità a 150 Km (cinque volte la distanza ottica di 30 Km) "
                            "e debolmente fino a 258 Km da Santa Margherita Ligure."
                        ),
                        "quote": "alla distanza di 150 Km., e cioè a cinque volte la distanza ottica",
                        "who": ["Guglielmo Marconi", "Gaston Antoine Mathieu"],
                        "vs": "Limite teorico della pura portata ottica per onde ultracorte e microonde",
                        "concepts": ["riflettore parabolico", "portata oltre l'orizzonte", "microonde"],
                    }
                ],
                "sig": {
                    "op_tags": [
                        "ANGULAR_GEOMETRY_PROJECTION",
                        "ORDER_OF_MAGNITUDE_BOUND",
                    ],
                    "role": "embodied_intuition",
                    "mech": (
                        "Concentrazione direzionale di onde emesse da un fuoco geometrico in un fascio "
                        "parallelo tramite superficie riflettente curva, moltiplicando la portata utile "
                        "ben oltre la dispersione isotropa."
                    ),
                },
            },
            "bridges": [
                {
                    "node_id": "P0.6",
                    "target_op_tags": ["ANGULAR_GEOMETRY_PROJECTION"],
                    "mapping": {
                        "Sorgente radio posta nel punto focale": "Fuoco geometrico F = (0, c) della parabola",
                        "Raggi riflessi paralleli verso il ricevitore": "Proprietà focale di y = (1/4c) x^2 (angolo incidenza = riflessione)",
                    },
                    "chain_steps": [
                        "1. A potenza ridotta le microonde disperse in tutte le direzioni svaniscono rapidamente col quadrato della distanza.",
                        "2. Collocando l'antenna nel fuoco di un riflettore parabolico, ogni onda emessa viene riflessa parallelamente all'asse di simmetria verso il ricevitore distante 150 Km.",
                        "3. La curva algebrica y = a x^2 non è un grafico astratto: è l'unica forma geometrica che trasforma raggi divergenti da un punto in un fascio collimato.",
                    ],
                    "score": 0.95,
                }
            ],
        },
        {
            "key": "galvani_stanza_chiusa_confounder",
            "optional": True,
            "title_hint": "galvani",
            "anchor": "è facile ingannarsi nel fare esperimenti e credere di aver visto",
            "extraction": {
                "yield": "high",
                "units": [
                    {
                        "kind": "exp",
                        "mode": "critiques",
                        "stmt": (
                            "Luigi Galvani ammonisce sul rischio di credere di aver trovato ciò che si desidera "
                            "vedere e trasferisce l'esperimento dal giardino aperto a una stanza chiusa per "
                            "escludere il ruolo dell'elettricità atmosferica."
                        ),
                        "quote": "è facile ingannarsi nel fare esperimenti e credere di aver visto e di aver trovato ciò che desideriamo vedere e trovare.",
                        "who": ["Luigi Galvani"],
                        "vs": "Ipotesi che le contrazioni all'aperto dipendessero dall'elettricità atmosferica accumulata",
                        "concepts": ["bias di conferma", "isolamento ambientale", "controllo sperimentale"],
                    }
                ],
                "sig": {
                    "op_tags": [
                        "VARIABLE_ISOLATION_CONTROL",
                        "HIDDEN_CONFOUNDER",
                    ],
                    "role": "fertile_error",
                    "mech": (
                        "Esclusione di una variabile ambientale sospetta trasferendo il sistema in ambiente "
                        "isolato e variando sistematicamente i materiali di contatto per separare correlazione "
                        "apparente e causa."
                    ),
                },
            },
            "bridges": [
                {
                    "node_id": "P3.3",
                    "target_op_tags": ["VARIABLE_ISOLATION_CONTROL", "HIDDEN_CONFOUNDER"],
                    "mapping": {
                        "Stato del cielo (sereno vs tempestoso) in giardino": "Variabile esterna esclusa tramite stanza chiusa",
                        "Coppia di metalli diversi (uncino rame + piano ferro)": "Variabile confondente nascosta non ancora isolata",
                    },
                    "chain_steps": [
                        "1. Osservando il fenomeno solo in giardino, Galvani correla inizialmente l'effetto alle variazioni atmosferiche (confirmation bias).",
                        "2. Spostando la prova in stanza chiusa elimina la variabile meteorologica, ma resta una variabile confondente nascosta: il contatto bimetallico rame-ferro.",
                        "3. Il brano illustra dal vivo perché nell'analisi dei dati correlazione non implica causalità e come un confounder non controllato possa generare una teoria errata.",
                    ],
                    "score": 0.94,
                }
            ],
        },
    ]

    summary: Dict[str, Any] = {"seeded_blocks": {}, "bridges_upserted": 0, "missing_keys": []}

    try:
        for spec in specs:
            row = _find_active_block_by_anchor(conn, spec["title_hint"], spec["anchor"])
            if row is None:
                if not spec.get("optional", False):
                    summary["missing_keys"].append(spec["key"])
                continue

            block_pk = int(row["block_pk"])
            block_uid = str(row["block_uid"])
            validated_ext = validate_block_extraction(
                spec["extraction"],
                block_content=str(row["content"]),
            )
            n_units = persist_block_extraction(
                conn,
                block_pk=block_pk,
                block_uid=block_uid,
                extraction=validated_ext,
            )
            bridge_pks: List[int] = []
            for br in spec["bridges"]:
                bpk = validate_and_upsert_bridge(
                    conn,
                    node_id=br["node_id"],
                    block_pk=block_pk,
                    target_op_tags=br["target_op_tags"],
                    mapping=br["mapping"],
                    chain_steps=br["chain_steps"],
                    score=br["score"],
                    status="validated",
                )
                bridge_pks.append(bpk)
                summary["bridges_upserted"] += 1

            summary["seeded_blocks"][spec["key"]] = {
                "block_pk": block_pk,
                "block_uid": block_uid,
                "book_title": row["book_title"],
                "units_persisted": n_units,
                "bridge_pks": bridge_pks,
            }

        conn.commit()
    finally:
        if owns_conn:
            conn.close()

    return summary


DEFAULT_NODE_ARCHETYPES: Tuple[GeneratorArchetype, ...] = (
    GeneratorArchetype(
        node_id="numeri.quantita",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.BIJECTION_EQUINUMEROSITY, OpTag.INVARIANT_PRESERVATION),
        generator_query="accoppiamento uno a uno senza contare e invarianza della numerosita rispetto a disposizione o ordine",
    ),
    GeneratorArchetype(
        node_id="numeri.posizionale",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.MODULAR_PERIODICITY, OpTag.PROPORTIONAL_SCALING),
        generator_query="codifica posizionale mediante raggruppamento periodico e cambio di scala tra ordini di grandezza",
    ),
    GeneratorArchetype(
        node_id="numeri.relativi",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.SIGNED_DEVIATION_FEEDBACK, OpTag.INVARIANT_PRESERVATION),
        generator_query="scostamento dotato di verso positivo o negativo rispetto a uno zero di riferimento centrale",
    ),
    GeneratorArchetype(
        node_id="frazioni.denominatore-comune",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.PROPORTIONAL_SCALING, OpTag.INVARIANT_PRESERVATION),
        generator_query="riduzione di misure eterogenee a una suddivisione unitaria comune preservando la quantita",
    ),
    GeneratorArchetype(
        node_id="P0.1",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.CONTRADICTION_REDUCTIO, OpTag.INVARIANT_PRESERVATION),
        generator_query="confutazione rigorosa per assurdo o riduzione di un enunciato a premesse incompatibili",
    ),
    GeneratorArchetype(
        node_id="P0.2",
        canonical_domains=("matematica", "informatica"),
        target_op_tags=(OpTag.SERIES_CONJUNCTION_GATE, OpTag.PARALLEL_DISJUNCTION_PATH),
        generator_query="congiunzione in serie tutto o niente e disgiunzione in parallelo con rami alternativi",
    ),
    GeneratorArchetype(
        node_id="P0.3",
        canonical_domains=("matematica", "informatica"),
        target_op_tags=(OpTag.BIJECTION_EQUINUMEROSITY, OpTag.COMBINATORIAL_GRID_PATTERN),
        generator_query="corrispondenza biunivoca tra collezioni, relazioni d'ordine e associazione funzionale",
    ),
    GeneratorArchetype(
        node_id="P0.4",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.CONTRADICTION_REDUCTIO, OpTag.ACCUMULATION_INTEGRATION),
        generator_query="incommensurabilita tra grandezze discrete e continue e approssimazione per accumulo",
    ),
    GeneratorArchetype(
        node_id="P0.5",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.BOUNDED_TOLERANCE, OpTag.SIGNED_DEVIATION_FEEDBACK),
        generator_query="mantenere un punto mobile entro un varco simmetrico azzerando lo scostamento scalare",
    ),
    GeneratorArchetype(
        node_id="P0.6",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.ANGULAR_GEOMETRY_PROJECTION, OpTag.RATE_OF_CHANGE, OpTag.THRESHOLD_PHASE_TRANSITION),
        generator_query="trasformazione funzionale tra ingresso e uscita, pendenza locale, asintoti e cambio di regime",
    ),
    GeneratorArchetype(
        node_id="P0.7",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.ANGULAR_GEOMETRY_PROJECTION, OpTag.SIGNAL_TRANSDUCTION_ECHO, OpTag.MODULAR_PERIODICITY),
        generator_query="proiezioni angolari, fasci direzionali, fenomeni ondulatori periodici e misura indiretta",
    ),
    GeneratorArchetype(
        node_id="P0.8",
        canonical_domains=("matematica",),
        target_op_tags=(OpTag.ORDER_OF_MAGNITUDE_BOUND, OpTag.BOTTLENECK_CAPACITY),
        generator_query="stima di fattibilita fisica o energetica per ordini di grandezza e limiti di flusso",
    ),
    GeneratorArchetype(
        node_id="P2.2",
        canonical_domains=("matematica", "informatica"),
        target_op_tags=(OpTag.COMBINATORIAL_GRID_PATTERN, OpTag.RECURSIVE_SELF_SIMILARITY, OpTag.MODULAR_PERIODICITY),
        generator_query="strutture discrete, pattern combinatori su griglia, ricorsione autosimile e aritmetica modulare",
    ),
    GeneratorArchetype(
        node_id="P3.2",
        canonical_domains=("matematica", "informatica"),
        target_op_tags=(OpTag.PROBABILITY_BAYESIAN_UPDATE, OpTag.HIDDEN_CONFOUNDER),
        generator_query="aggiornamento di fiducia su ipotesi incerte con segnali rumorosi e variabili confondenti",
    ),
    GeneratorArchetype(
        node_id="P4.1",
        canonical_domains=("matematica", "informatica"),
        target_op_tags=(OpTag.CONSTRAINED_SEARCH_DECODING, OpTag.ADVERSARIAL_DECEPTION, OpTag.MODULAR_PERIODICITY),
        generator_query="decodifica di simboli ignoti tramite enumerazione ordinata, inganno avversario e periodicita",
    ),
    GeneratorArchetype(
        node_id="P5.2",
        canonical_domains=("informatica",),
        target_op_tags=(OpTag.VARIABLE_ISOLATION_CONTROL, OpTag.HIDDEN_CONFOUNDER),
        generator_query="ripristino della baseline funzionante e isolamento controllato di un singolo componente guasto",
    ),
)


def build_bridge_validation_prompt(
    archetype: GeneratorArchetype,
    cand: WrongBookCandidate,
) -> str:
    """Costruisce il prompt rigoroso (anti-metafora) per verificare un isomorfismo 1-a-1."""
    excerpt = cand.content[:1800]
    return (
        "Sei il validatore epistemico severo di `resuscipack` per i ponti «Il Libro Sbagliato».\n"
        "Devi decidere se questo brano estratto da un dominio NON canonico costituisce un "
        "VERO isomorfismo causale, quantitativo o procedurale per il nodo didattico.\n"
        "REGOLA ANTI-METAFORA (OBBLIGATORIA): RIFIUTA (`is_valid: false`) qualsiasi analogia poetica, "
        "letteraria, teatrale, biografica o sociologica vaga (es. 'influenza stilistica ↔ onda', "
        "'trama drammatica ↔ cifrario', 'storia di una disciplina ↔ sistema in guasto', "
        "'talento musicale ↔ isolamento variabili').\n"
        "Accetta (`is_valid: true`, `score >= 0.88`) SOLO se nel brano compaiono grandezze o operazioni "
        "concrete e misurabili (fisiche, acustiche, geometriche, meccaniche, sperimentali o algoritmiche) "
        "la cui relazione rispetta esattamente la stessa struttura formale del nodo (come le boe a 50 m di "
        "Marconi ↔ |x - x0| < 25, i conduttori in serie di Galvani ↔ AND, i rapporti di quinta (3/2)^n ↔ potenze).\n"
        "Rispondi SOLO con un oggetto JSON valido.\n"
        "Se il collegamento è metaforico, superficiale o privo di meccanismo misurabile, rispondi: "
        '{"is_valid": false, "reason": "motivo sintetico"}.\n'
        "Se invece esiste una corrispondenza rigorosa:\n"
        '{"is_valid": true, "mapping": {"grandezza concreta nel brano": "oggetto formale del nodo", ...}, '
        '"chain_steps": ["1. ...", "2. ...", "3. ..."], "score": 0.88_to_1.0}\n'
        "VINCOLI se is_valid=true: almeno 2 coppie distinte in `mapping` e almeno 3 passi "
        "inferenziali numerati in `chain_steps` (ciascuno >= 20 caratteri) ancorati ai fatti reali del brano.\n\n"
        f"NODO TARGET: {archetype.node_id}\n"
        f"ARCHETIPO FORMALE DEL NODO: {archetype.generator_query}\n"
        f"OP_TAGS TARGET: {[t.value for t in archetype.target_op_tags]}\n\n"
        f"LIBRO CANDIDATO: {cand.book_title!r} (dominio={cand.surface_domain!r}, p.{cand.page_start})\n"
        f"FIRMA ESTRATTA: {cand.mech}\n"
        f"BRANO ORIGINALE:\n{excerpt}\n"
    )


def _record_rejected_bridge(
    conn: sqlite3.Connection,
    node_id: str,
    block_pk: int,
    target_op_tags: Sequence[OpTag],
) -> None:
    """Registra in cache un candidato rifiutato come decorativo per evitare di ripagarlo nelle Wave successive."""
    resolved_tags = [t.value for t in validate_op_tags(target_op_tags)]
    conn.execute(
        """
        INSERT INTO curiosity_bridges (
            node_id, block_pk, target_op_tags_json, mapping_json,
            chain_steps_json, score, status
        ) VALUES (?, ?, ?, '{}', '[]', 0.0, 'rejected_decorative')
        ON CONFLICT(node_id, block_pk) DO UPDATE SET
            target_op_tags_json = excluded.target_op_tags_json,
            mapping_json = '{}',
            chain_steps_json = '[]',
            score = 0.0,
            status = 'rejected_decorative'
        """,
        (node_id, int(block_pk), json.dumps(resolved_tags, ensure_ascii=False)),
    )


def discover_and_validate_bridges(
    conn: sqlite3.Connection,
    call_llm_fn: Any,
    *,
    top_k_per_node: int = 5,
    archetypes: Sequence[GeneratorArchetype] = DEFAULT_NODE_ARCHETYPES,
    max_workers: int = 1,
    min_score: float = 0.88,
) -> Dict[str, Any]:
    """Scopre e valida nuovi ponti 'Libro Sbagliato' dai blocchi con `structural_signatures`."""
    from concurrent.futures import ThreadPoolExecutor

    existing_pairs = {
        (str(r[0]), int(r[1]))
        for r in conn.execute("SELECT node_id, block_pk FROM curiosity_bridges").fetchall()
    }

    pending_tasks: List[Tuple[GeneratorArchetype, WrongBookCandidate, str]] = []
    seen_in_run: set[Tuple[str, int]] = set()
    for arch in archetypes:
        cands = find_wrong_book_candidates(conn, arch, limit=top_k_per_node)
        for cand in cands:
            key = (arch.node_id, cand.block_pk)
            if key in existing_pairs or key in seen_in_run:
                continue
            seen_in_run.add(key)
            pending_tasks.append((arch, cand, build_bridge_validation_prompt(arch, cand)))

    stats: Dict[str, Any] = {
        "candidates_checked": len(pending_tasks),
        "bridges_validated": 0,
        "bridges_rejected": 0,
        "errors": [],
    }
    if not pending_tasks:
        return stats

    def _eval_one(task: Tuple[GeneratorArchetype, WrongBookCandidate, str]) -> Tuple[GeneratorArchetype, WrongBookCandidate, Any, Optional[str]]:
        arch, cand, prompt = task
        try:
            return arch, cand, call_llm_fn(prompt), None
        except Exception as exc:
            return arch, cand, None, str(exc)

    if max_workers > 1 and len(pending_tasks) > 1:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(pending_tasks))) as pool:
            outcomes = list(pool.map(_eval_one, pending_tasks))
    else:
        outcomes = [_eval_one(t) for t in pending_tasks]

    for arch, cand, raw_resp, err in outcomes:
        if err is not None:
            # Errore di rete/transitorio: non cachiamo come rejected_decorative così potrà riprovare
            stats["bridges_rejected"] += 1
            stats["errors"].append(f"{arch.node_id}/{cand.block_pk}: {err}")
            continue

        if not isinstance(raw_resp, Mapping) or not bool(raw_resp.get("is_valid", False)):
            _record_rejected_bridge(conn, arch.node_id, cand.block_pk, arch.target_op_tags)
            stats["bridges_rejected"] += 1
            continue

        try:
            mapping = raw_resp.get("mapping") or {}
            chain_steps = raw_resp.get("chain_steps") or []
            raw_score = float(raw_resp.get("score", cand.score))
            clamped_score = max(0.0, min(1.0, raw_score))
            if clamped_score < min_score:
                _record_rejected_bridge(conn, arch.node_id, cand.block_pk, arch.target_op_tags)
                stats["bridges_rejected"] += 1
                continue
            validate_and_upsert_bridge(
                conn,
                node_id=arch.node_id,
                block_pk=cand.block_pk,
                target_op_tags=arch.target_op_tags,
                mapping=mapping,
                chain_steps=chain_steps,
                score=clamped_score,
                status="validated",
            )
            stats["bridges_validated"] += 1
        except (ValueError, KeyError, TypeError) as exc:
            _record_rejected_bridge(conn, arch.node_id, cand.block_pk, arch.target_op_tags)
            stats["bridges_rejected"] += 1
            stats["errors"].append(f"{arch.node_id}/{cand.block_pk}: {exc}")

    conn.commit()
    return stats
