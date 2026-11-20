#!/usr/bin/env python3
"""CLI Batch Idempotente per l'estrazione `BlockExtraction v2.1` a ondate (Wave 1..4).

Principi non negoziabili (ADR-0002, TASK-EPIST-03, TASK-EPIST-04):
- Provider primario `vertex`: usa i crediti Google Cloud attivi (`$GCP_PROJECT`)
  tramite `gcloud auth print-access-token` in memoria (zero segreti su disco, attribuzione
  `CLOUDSDK_METRICS_ENVIRONMENT` conforme a `enforcing-resource-attribution`).
- Provider secondari `gemini` / `deepseek`: leggono API key esclusivamente da `os.environ`.
- Zero Mock Guarantee: se le credenziali mancano e non si è in `--dry-run` o `--seed-empirical`,
  termina esplicitamente con `MissingCredentialsError` senza scrivere righe finte nel DB.
- Idempotenza totale: traccia ogni blocco processato (anche `low_or_paratext`) dentro
  `block_extraction_log`, esegue a micro-batch concorrenti con commit incrementali WAL,
  1 auto-riparazione su `SchemaValidationError`, telemetria live su `data/wave1_status.json`
  e discovery opzionale dei ponti "Libro Sbagliato" su `curiosity_bridges`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .bridge import (
    DEFAULT_NODE_ARCHETYPES,
    discover_and_validate_bridges,
    seed_verified_empirical_bridges,
)
from .op_tags import ALL_OP_TAGS, DEFAULT_FORBIDDEN_SURFACE_NOUNS
from .schema_v21 import (
    ALL_MACRO_DISCIPLINES,
    BlockExtractionV21,
    BlockYield,
    SchemaValidationError,
    persist_block_extraction,
    persist_v22_metadata_only,
    validate_batch_anti_template,
    validate_block_extraction,
    validate_v22_metadata_only,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pack_corpus.db"
DEFAULT_STATUS_PATH = Path(__file__).resolve().parents[2] / "data" / "wave1_status.json"
DEFAULT_GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
DEFAULT_VERTEX_MODEL = "gemini-2.5-flash"
DEFAULT_BATCH_LOCATION = "us-central1"

WAVE_DOMAINS: Mapping[int, tuple[str, ...]] = {
    # Wave 1: Nucleo Aureo (selettore dedicato ~50-62 libri; fallback dominio storia_della_scienza)
    1: ("storia_della_scienza",),
    # Wave 2: Miniera dei Libri Sbagliati (Filosofia, Medicina/Biologia, Musica, Arte, Botanica)
    2: (
        "filosofia_scienze_umane",
        "medicina_biologia",
        "musica_acustica",
        "arte_letteratura_antichita",
        "botanica_scienze_naturali",
    ),
    # Wave 3: Trattati STEM completi (Matematica, Informatica, Fisica/Ingegneria)
    3: ("matematica", "informatica", "fisica_ingegneria"),
    # Wave 4: Miscellanea tecnica e coda lunga (100% corpus)
    4: ("miscellanea_tecnica",),
}

_NUCLEO_AUREO_KEYWORDS: tuple[str, ...] = (
    "galvani",
    "cartesio",
    "descartes",
    "frajese",
    "boole",
    "prodi",
    "bellissima",
    "torricelli",
    "newton",
    "cavalieri",
    "kelvin",
    "abbagnano",
    "winskel",
    "bertossi",
    "blockchain",
    "etica per le ict",
    "ohm",
    "utet",
)

_META_MECH_BOILERPLATE_RE = re.compile(
    r"^\s*(?:il\s+(?:testo|brano|meccanismo|sistema|passo|capitolo|paragrafo)"
    r"|questo\s+(?:testo|brano|meccanismo)|l'autore|la\s+sezione)\s+"
    r"(?:descrive|presenta|illustra|mostra|analizza|introduce|traccia|opera|consiste)\b",
    flags=re.IGNORECASE,
)


class MissingCredentialsError(RuntimeError):
    """Sollevato quando si richiede estrazione cloud reale senza credenziali valide."""


class _VertexTokenCache:
    """Cache thread-safe in memoria per token OAuth `gcloud` (rinnovo ogni 25 minuti)."""

    def __init__(self, ttl_seconds: int = 1500) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._token: str = ""
        self._fetched_at: float = 0.0

    def get_token(self, *, force_refresh: bool = False) -> str:
        with self._lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._token
                and (now - self._fetched_at) < self._ttl
            ):
                return self._token
            token = _fetch_gcloud_access_token()
            self._token = token
            self._fetched_at = now
            return token

    def invalidate(self) -> None:
        with self._lock:
            self._token = ""
            self._fetched_at = 0.0


_VERTEX_TOKEN_CACHE = _VertexTokenCache()


def _gcloud_env() -> Dict[str, str]:
    env = os.environ.copy()
    existing = env.get("CLOUDSDK_METRICS_ENVIRONMENT", "").strip()
    if "datacloud.antigravity" not in existing.split():
        env["CLOUDSDK_METRICS_ENVIRONMENT"] = f"{existing} datacloud.antigravity".strip()
    return env


def _fetch_gcloud_access_token() -> str:
    try:
        proc = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            env=_gcloud_env(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise MissingCredentialsError(
            f"Impossibile eseguire `gcloud auth print-access-token` per Vertex AI: {exc}"
        ) from exc

    tok = (proc.stdout or "").strip()
    if proc.returncode != 0 or not tok:
        stderr_msg = (proc.stderr or "").strip()[:220]
        raise MissingCredentialsError(
            f"Token OAuth gcloud assente o non valido per Vertex AI (code={proc.returncode}): {stderr_msg}. "
            "Esegui `gcloud auth login` oppure usa `--dry-run`."
        )
    return tok


def build_block_extraction_prompt(
    *,
    book_title: str,
    surface_domain: str,
    section_title: str,
    page_start: Optional[int],
    content: str,
) -> str:
    """Costruisce il prompt deterministico `BlockExtraction v2.1` (zero leakage, diritto al silenzio)."""
    tags_csv = ", ".join(sorted(ALL_OP_TAGS))
    forbidden_csv = ", ".join(sorted(DEFAULT_FORBIDDEN_SURFACE_NOUNS)[:16])
    return (
        "Sei l'estrattore epistemico di `resuscipack` (schema `block-extraction.v2.1`).\n"
        "Rispondi SOLO con un singolo oggetto JSON valido, senza testo o markdown intorno.\n"
        "FORMATO OBBLIGATORIO: "
        '{"yield":"high|medium|low_or_paratext","units":[{"kind":"def|thm|proof_idea|proc|exp|dispute|claim|counterex",'
        '"mode":"defines|proves|applies|critiques|extends|presupposes|narrates","stmt":"...","quote":"...",'
        '"who":["..."],"vs":null,"concepts":["..."]}],"sig":{"op_tags":["..."],"role":"genesis_problem|'
        'embodied_intuition|fertile_error|hidden_assumption|feasibility_bound","mech":"..."}}\n'
        "REGOLE FERREE:\n"
        "1. DIRITTO AL SILENZIO: se il brano è indice, sommario, bibliografia, frontespizio, colophon, "
        "prefazione editoriale che elenca soltanto curatori/capitoli, nota tipografica, pagina vuota o "
        'privo di asserzioni concettuali, restituisci {"yield":"low_or_paratext","units":[],"sig":null}.\n'
        "2. CONCISIONE, ZERO META-DESCRIZIONI E ZERO DEISSI: estrai solo 1–4 unità ad alta densità (`units`, "
        "massimo 6). Ogni `units[i].stmt` deve avere 40–200 caratteri, soggetto esplicito (vietati 'egli', "
        "'ella', 'esso', 'il nostro', 'ivi', 'ibidem', 'op. cit.') e NON deve iniziare con formule meta "
        "come 'Il testo descrive...' o 'Il brano presenta...': esprimi direttamente la proposizione.\n"
        "3. CITAZIONE VERBATIM BREVE: `units[i].quote` deve essere una sottostringa ESATTA di 6–22 parole "
        "copiata letteralmente dal BRANO (stesse parole nello stesso ordine). "
        "Se `kind='dispute'`, valorizza obbligatoriamente `vs` (Con chi in disaccordo).\n"
        "4. FIRMA STRUTTURALE `sig` STRETTAMENTE SELETTIVA: imposta `\"sig\": null` sui manuali astratti "
        "(matematica/informatica) E ANCHE su biografie pure, libretti d'opera, riassunti storici generici "
        "o saggi musicologici privi di un meccanismo fisico, acustico, geometrico, sperimentale o procedurale concreto.\n"
        "5. DOMAIN STRIPPING CONCISO (solo quando `sig` è concreto e non null): `sig.mech` deve essere UNA "
        "sola frase densa di 80–240 caratteri; è VIETATO iniziare con formule meta come 'Il meccanismo descrive...', "
        "'Il testo descrive...', 'Il sistema...', 'Il brano...' (inizia direttamente dal sostantivo d'azione o "
        f"relazione, es. 'Concentrazione direzionale di onde...', 'Suddivisione di una corda vibrante...'); è VIETATO "
        f"usare sostantivi aneddotici di superficie (es. {forbidden_csv}) o iniettare formule con modulo assenti "
        "dal testo; scegli 1..3 `op_tags` SOLO tra:\n"
        f"[{tags_csv}]\n\n"
        f"METADATI CONTESTO: titolo={book_title!r} | dominio={surface_domain!r} | "
        f"sezione={section_title!r} | pag={page_start}\n"
        "BRANO:\n"
        f"{content}\n"
    )


V22_COMPACT_ITEM_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["b", "y", "d", "t", "p", "yr", "u"],
    "properties": {
        "b": {"type": "INTEGER"},
        "y": {"type": "STRING", "enum": ["high", "medium", "low_or_paratext"]},
        "d": {"type": "ARRAY", "maxItems": 3, "items": {"type": "STRING", "enum": sorted(ALL_MACRO_DISCIPLINES)}},
        "t": {"type": "ARRAY", "maxItems": 3, "items": {"type": "STRING"}},
        "p": {"type": "ARRAY", "maxItems": 20, "items": {"type": "STRING"}},
        "yr": {"type": "ARRAY", "maxItems": 12, "items": {"type": "STRING"}},
        "u": {
            "type": "ARRAY",
            "maxItems": 2,
            "items": {
                "type": "OBJECT",
                "required": ["k", "m", "st", "q", "w", "c"],
                "properties": {
                    "k": {"type": "STRING", "enum": ["def", "thm", "proof_idea", "proc", "exp", "dispute", "claim", "counterex"]},
                    "m": {"type": "STRING", "enum": ["defines", "proves", "applies", "critiques", "extends", "presupposes", "narrates"]},
                    "st": {"type": "STRING"},
                    "q": {"type": "STRING"},
                    "w": {"type": "ARRAY", "maxItems": 4, "items": {"type": "STRING"}},
                    "v": {"type": "STRING", "nullable": True},
                    "c": {"type": "ARRAY", "maxItems": 3, "items": {"type": "STRING"}},
                },
            },
        },
        "s": {
            "type": "OBJECT",
            "nullable": True,
            "required": ["op", "r", "mc"],
            "properties": {
                "op": {"type": "ARRAY", "maxItems": 2, "items": {"type": "STRING", "enum": sorted(ALL_OP_TAGS)}},
                "r": {"type": "STRING", "enum": ["genesis_problem", "embodied_intuition", "fertile_error", "hidden_assumption", "feasibility_bound"]},
                "mc": {"type": "STRING"},
            },
        },
    },
}

V22_COMPACT_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["items"],
    "properties": {"items": {"type": "ARRAY", "items": V22_COMPACT_ITEM_SCHEMA}},
}

V22_SINGLE_COMPACT_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["y", "d", "t", "p", "yr", "u"],
    "properties": {k: v for k, v in V22_COMPACT_ITEM_SCHEMA["properties"].items() if k != "b"},
}

V22_METADATA_ONLY_ITEM_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["b", "y", "d", "t", "p", "yr"],
    "properties": {
        k: V22_COMPACT_ITEM_SCHEMA["properties"][k] for k in ("b", "y", "d", "t", "p", "yr")
    },
}

V22_METADATA_ONLY_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["items"],
    "properties": {"items": {"type": "ARRAY", "items": V22_METADATA_ONLY_ITEM_SCHEMA}},
}

V22_SINGLE_METADATA_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["y", "d", "t", "p", "yr"],
    "properties": {k: V22_COMPACT_ITEM_SCHEMA["properties"][k] for k in ("y", "d", "t", "p", "yr")},
}


def build_multiblock_extraction_prompt(
    *,
    book_title: str,
    surface_domain: str,
    rows: Sequence[Mapping[str, Any]],
    single_v22_only: bool = False,
    metadata_only: bool = False,
) -> str:
    """Costruisce il prompt compatto `BlockExtraction v2.2` (`responseSchema` JSON su 1..8 blocchi)."""
    blocks_section = []
    for r in rows:
        bpk = int(r["block_pk"])
        pg = r["page_start"]
        sec = str(r["section_title"] or "").strip()
        txt = str(r["content"] or "").strip()
        blocks_section.append(
            f"[B:block_pk={bpk}|p:{pg}|sec={sec!r}]\n{txt}\n[/B:{bpk}]"
        )
    joined_blocks = "\n\n".join(blocks_section)

    order_rule = (
        ""
        if single_v22_only
        else "- Restituisci in `items[]` ESATTAMENTE 1 oggetto per ogni `[B:block_pk=id|...]` nell'identico ordine (`b`=id integer).\n"
    )
    if metadata_only:
        return (
            "Classifica lo spettro reale v2.2 dei seguenti brani in JSON compatto (`d`=macro-discipline, `t`=temi, `p`=luoghi, `yr`=anni).\n"
            f"{order_rule}"
            "- Se un blocco è solo indice, sommario, frontespizio, vuoto OPPURE sequenza illeggibile di simboli/numeri/codici font corrotti priva di frasi di senso compiuto: `y`='low_or_paratext', `d`=[],`t`=[],`p`=[],`yr`=[].\n"
            "- Altrimenti: `d`=1..3 macro-discipline effettive del testo (es. Marconi navale/costiero include `geografia_cartografia_territorio`); `t`=1..3 temi specifici in italiano; `p`=toponimi geografici reali citati nel brano; `yr`=anni o date esplicite.\n"
            f"LIBRO: {book_title!r} ({surface_domain})\n\n{joined_blocks}\n"
        )

    return (
        "Estrai in JSON compatto `BlockExtraction v2.2` secondo lo schema allegato.\n"
        f"{order_rule}"
        "- Se indice/frontespizio/bibliografia/vuoto OPPURE sequenza illeggibile di simboli/numeri/codici font corrotti priva di frasi di senso compiuto: `y`='low_or_paratext', `d`=[],`t`=[],`p`=[],`yr`=[],`u`=[],`s`=null.\n"
        "- Altrimenti: `d`=1..3 macro-discipline reali del brano; `t`=1..3 temi specifici in italiano; `p`=toponimi geografici reali nel brano; `yr`=anni/date esplicite.\n"
        "- `u`: 1 sola asserzione centrale per brani ordinari, 2 solo se la pagina enuncia due definizioni/teoremi/esperimenti distinti (`st` 45..110 char con soggetto esplicito, vietati egli/esso/costui/ivi; "
        "`q` citazione CONTIGUA ESATTA di 5..14 parole copiata carattere-per-carattere dal brano: NON correggere refusi OCR come 'ro'->'10', NON tradurre LaTeX greco in Unicode, VIETATO inserire '[...]' o ellissi; "
        "`v` obbligatorio se `k`='dispute'; `c`=1..3 concetti; mai mettere 'narrates' dentro `k`).\n"
        "- `s`: null su esposizioni astratte/biografiche pure; valorizza solo per un meccanismo fisico, sperimentale o procedurale concreto "
        "(`mc` 80..165 char astratto dal dominio, senza meta-frasi 'Il testo descrive...' e senza sostantivi aneddotici di superficie).\n"
        f"LIBRO: {book_title!r} ({surface_domain})\n\n{joined_blocks}\n"
    )


def _norm_title_dedup_key(title: str) -> str:
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]|libgen\.lc|libgen", " ", title.lower())
    cleaned = re.sub(r"[^a-z0-9à-ÿ]+", " ", cleaned)
    return " ".join(cleaned.split()[:6])


def select_nucleo_aureo_book_pks(
    conn: sqlite3.Connection,
    *,
    max_books: int = 62,
    max_blocks: int = 5200,
) -> List[int]:
    """Seleziona in modo deterministico il ~60-book Nucleo Aureo per Wave 1 (~4.000-5.200 blocchi)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            bk.book_pk,
            bk.title,
            bk.surface_domain,
            COUNT(bl.block_pk) AS n_blocks
        FROM books bk
        JOIN blocks bl ON bl.book_pk = bk.book_pk
        WHERE bk.is_active = 1
          AND bl.is_active = 1
          AND bl.block_role != 'paratext'
        GROUP BY bk.book_pk
        ORDER BY bk.book_pk ASC
        """
    ).fetchall()

    candidates: List[Tuple[int, int, int, str]] = []
    for r in rows:
        bpk = int(r["book_pk"])
        title = str(r["title"] or "")
        title_l = title.lower()
        dom = str(r["surface_domain"] or "")
        n_blks = int(r["n_blocks"])

        tier: Optional[int] = None
        if dom == "storia_della_scienza":
            tier = 0
        elif any(k in title_l for k in ("galvani", "cartesio", "descartes")) and n_blks <= 600:
            tier = 1
        elif any(k in title_l for k in ("frajese", "boole", "prodi", "bellissima")) and n_blks <= 450:
            tier = 2
        elif dom == "musica_acustica":
            tier = 3
        elif any(k in title_l for k in _NUCLEO_AUREO_KEYWORDS):
            tier = 4

        if tier is not None:
            candidates.append((tier, n_blks, bpk, _norm_title_dedup_key(title)))

    # Ordina deterministicamente dando priorità alla varietà tra Storia, Galvani/Cartesio, Fondamenti e Musica
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))

    selected: List[int] = []
    seen_titles: set[str] = set()
    total_blocks = 0
    for tier, n_blks, bpk, dedup_key in candidates:
        if len(selected) >= max_books:
            break
        if dedup_key and dedup_key in seen_titles:
            continue
        if selected and (total_blocks + n_blks) > max_blocks:
            continue
        selected.append(bpk)
        if dedup_key:
            seen_titles.add(dedup_key)
        total_blocks += n_blks

    return selected


def select_pending_blocks(
    conn: sqlite3.Connection,
    *,
    wave: Optional[int] = None,
    limit: Optional[int] = None,
    pack_size: int = 1,
    include_v21_backfill: bool = False,
    book_pk: Optional[int] = None,
    block_pks: Optional[Sequence[int]] = None,
) -> List[sqlite3.Row]:
    """Seleziona i blocchi sostantivi attivi pendenti (raggruppati in finestre `pack_size` per libro e
    intercalati Round-Robin tra i libri)."""
    conn.row_factory = sqlite3.Row
    params: List[Any] = []
    filter_clause = ""

    if block_pks:
        clean_pks = sorted({int(pk) for pk in block_pks})
        if clean_pks:
            placeholders = ",".join("?" for _ in clean_pks)
            filter_clause += f" AND bl.block_pk IN ({placeholders})"
            params.extend(clean_pks)
    if book_pk is not None:
        filter_clause += " AND bk.book_pk = ?"
        params.append(int(book_pk))
    elif wave is not None and not block_pks:
        if wave not in WAVE_DOMAINS:
            raise ValueError(f"Wave non valida: {wave} (ammesse: 1, 2, 3, 4)")
        if wave == 1:
            book_pks = select_nucleo_aureo_book_pks(conn)
            if book_pks:
                placeholders = ",".join("?" for _ in book_pks)
                filter_clause = f"AND bk.book_pk IN ({placeholders})"
                params.extend(book_pks)
            else:
                doms = WAVE_DOMAINS[1]
                placeholders = ",".join("?" for _ in doms)
                filter_clause = f"AND bk.surface_domain IN ({placeholders})"
                params.extend(doms)
        else:
            doms = WAVE_DOMAINS[wave]
            placeholders = ",".join("?" for _ in doms)
            filter_clause = f"AND bk.surface_domain IN ({placeholders})"
            params.extend(doms)

    has_log_table = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='block_extraction_log'"
        ).fetchone()
        is not None
    )
    has_v22_table = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='block_metadata_v22'"
        ).fetchone()
        is not None
    )

    if include_v21_backfill and has_v22_table and has_log_table:
        done_join = (
            "LEFT JOIN block_extraction_log bel ON bel.block_pk = bl.block_pk "
            "LEFT JOIN block_metadata_v22 m22 ON m22.block_pk = bl.block_pk"
        )
        done_filter = "AND m22.block_pk IS NULL AND (bel.yield IS NULL OR bel.yield != 'low_or_paratext')"
    elif has_log_table:
        done_join = "LEFT JOIN block_extraction_log bel ON bel.block_pk = bl.block_pk"
        done_filter = "AND bel.block_pk IS NULL"
    else:
        done_join = "LEFT JOIN (SELECT DISTINCT block_pk FROM epistemic_units) done ON done.block_pk = bl.block_pk"
        done_filter = "AND done.block_pk IS NULL"

    sql = f"""
        SELECT
            bl.block_pk,
            bl.block_uid,
            bl.book_pk,
            bl.book_title,
            bl.section_title,
            bl.page_start,
            bl.content,
            bl.est_tokens,
            bk.surface_domain,
            (SELECT COUNT(*) FROM epistemic_units eu WHERE eu.block_pk = bl.block_pk) AS existing_units_cnt
        FROM blocks bl
        JOIN books bk ON bk.book_pk = bl.book_pk
        {done_join}
        WHERE bl.is_active = 1
          AND bk.is_active = 1
          AND bl.block_role != 'paratext'
          {done_filter}
          {filter_clause}
        ORDER BY bl.book_pk ASC, bl.page_start ASC, bl.block_pk ASC
    """
    raw_rows = conn.execute(sql, tuple(params)).fetchall()

    # Interleaving Round-Robin per finestre contigue di `pack_size` blocchi dello stesso book_pk
    win_sz = max(1, int(pack_size))
    by_book: Dict[int, deque[sqlite3.Row]] = defaultdict(deque)
    book_order: List[int] = []
    for r in raw_rows:
        bpk = int(r["book_pk"])
        if bpk not in by_book:
            book_order.append(bpk)
        by_book[bpk].append(r)

    interleaved: List[sqlite3.Row] = []
    active_books = deque(book_order)
    while active_books:
        bpk = active_books.popleft()
        q = by_book[bpk]
        taken = 0
        while q and taken < win_sz:
            interleaved.append(q.popleft())
            taken += 1
        if q:
            active_books.append(bpk)

    if limit is not None and limit > 0:
        return list(islice(interleaved, int(limit)))
    return interleaved


def group_rows_into_book_windows(rows: Sequence[sqlite3.Row], pack_size: int = 5) -> List[List[sqlite3.Row]]:
    """Raggruppa righe consecutive appartenenti allo stesso `book_pk` in finestre di lunghezza `<= pack_size`."""
    win_sz = max(1, int(pack_size))
    if win_sz == 1:
        return [[r] for r in rows]

    windows: List[List[sqlite3.Row]] = []
    current: List[sqlite3.Row] = []
    current_book: Optional[int] = None
    for r in rows:
        bpk = int(r["book_pk"])
        if current and (bpk != current_book or len(current) >= win_sz):
            windows.append(current)
            current = []
        current_book = bpk
        current.append(r)
    if current:
        windows.append(current)
    return windows


def estimate_wave_budget(rows: Sequence[sqlite3.Row], *, pack_size: int = 8) -> Dict[str, Any]:
    """Calcola token di input/output e costi stimati USD sui blocchi pendenti (`responseSchema` compatto)."""
    n_blocks = len(rows)
    n_books = len({int(r["book_pk"]) for r in rows}) if rows and "book_pk" in rows[0].keys() else 0
    text_tokens = sum(int(r["est_tokens"] or max(1, len(r["content"]) // 4)) for r in rows)
    prompt_overhead = n_blocks * 280
    in_tokens = text_tokens + prompt_overhead
    out_tokens = n_blocks * 335

    cost_flash_lite = (in_tokens / 1e6) * 0.05 + (out_tokens / 1e6) * 0.20
    cost_deepseek = (in_tokens / 1e6) * 0.14 + (out_tokens / 1e6) * 0.28
    cost_gemini_flash_batch = (in_tokens / 1e6) * 0.15 + (out_tokens / 1e6) * 1.25
    cost_vertex_flash_sync = (in_tokens / 1e6) * 0.30 + (out_tokens / 1e6) * 2.50

    windows = group_rows_into_book_windows(rows, pack_size=pack_size)
    n_win = len(windows)
    n_meta_only = sum(
        1 for r in rows if "existing_units_cnt" in r.keys() and int(r["existing_units_cnt"] or 0) > 0
    )
    n_full = n_blocks - n_meta_only
    # Profilo empirico responseSchema a chiavi compatte: ~310 tok header/finestra, ~290 out full, ~70 out backfill
    packed_in_tokens = text_tokens + n_win * 310
    packed_out_tokens = n_full * 290 + n_meta_only * 70
    packed_sync_usd = (packed_in_tokens / 1e6) * 0.30 + (packed_out_tokens / 1e6) * 2.50
    packed_batch_usd = (packed_in_tokens / 1e6) * 0.15 + (packed_out_tokens / 1e6) * 1.25
    eur_per_100_batch = (
        round(((packed_batch_usd * 0.92) / n_blocks) * 100.0, 4) if n_blocks else 0.0
    )

    return {
        "pending_books": n_books,
        "pending_blocks": n_blocks,
        "pending_metadata_only_blocks": n_meta_only,
        "estimated_input_tokens": in_tokens,
        "estimated_output_tokens": out_tokens,
        "estimated_cost_usd": {
            "vertex_gemini_2_5_flash_credits": round(cost_vertex_flash_sync, 3),
            "gemini_2_5_flash_batch": round(cost_gemini_flash_batch, 3),
            "gemini_2_5_flash_lite_batch": round(cost_flash_lite, 3),
            "deepseek_v3_batch": round(cost_deepseek, 3),
        },
        "packed_v22_estimate": {
            "pack_size": max(1, int(pack_size)),
            "window_count": n_win,
            "estimated_input_tokens_packed": packed_in_tokens,
            "estimated_output_tokens_packed": packed_out_tokens,
            "vertex_sync_usd": round(packed_sync_usd, 3),
            "vertex_batch_usd": round(packed_batch_usd, 3),
            "vertex_batch_eur": round(packed_batch_usd * 0.92, 3),
            "vertex_batch_eur_per_100_blocks": eur_per_100_batch,
        },
    }


def _resolve_api_key(provider: str) -> str:
    env_var = "GEMINI_API_KEY" if provider == "gemini" else "DEEPSEEK_API_KEY"
    val = os.environ.get(env_var, "").strip()
    if not val:
        raise MissingCredentialsError(
            f"Variabile d'ambiente {env_var} assente. Rifiuto di generare fallback/mock finti: "
            f"esporta {env_var} nell'ambiente oppure usa `--provider vertex` / `--dry-run` / `--seed-empirical`."
        )
    return val


def _strip_json_fences(raw_text: str) -> str:
    txt = raw_text.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


def _repair_json_latex_escapes(raw_json: str) -> str:
    return re.sub(r'\\(?![\\/"bfnrtu])', r'\\\\', raw_json)


def _decode_json_tolerant(raw_text: str) -> Mapping[str, Any]:
    cleaned = _strip_json_fences(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return json.loads(_repair_json_latex_escapes(cleaned))


_ONLINE_LOCATIONS: Tuple[str, ...] = ("us-central1", "global", "europe-west1", "us-east4")


def _vertex_generate_json(
    prompt: str,
    *,
    project_id: Optional[str] = None,
    model: Optional[str] = None,
    thinking_budget: int = 0,
    max_output_tokens: int = 2048,
    response_schema: Optional[Mapping[str, Any]] = None,
) -> Tuple[Mapping[str, Any], int, int]:
    """Chiama Vertex AI `gemini-2.5-flash` sui crediti Google Cloud con refresh token e failover multi-regione 429/503."""
    proj = project_id or os.environ.get("GCP_PROJECT_ID", DEFAULT_GCP_PROJECT)
    mdl = model or os.environ.get("VERTEX_GEMINI_MODEL", DEFAULT_VERTEX_MODEL)
    gen_cfg: Dict[str, Any] = {
        "temperature": 0.1,
        "maxOutputTokens": int(max_output_tokens),
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": int(thinking_budget)},
    }
    if response_schema is not None:
        gen_cfg["responseSchema"] = response_schema
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }
    ).encode("utf-8")

    backoffs = (4.0, 12.0, 28.0, 55.0)
    last_err: Optional[Exception] = None
    for attempt in range(len(backoffs) + 1):
        loc = _ONLINE_LOCATIONS[attempt % len(_ONLINE_LOCATIONS)]
        host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
        url = (
            f"https://{host}/v1/projects/{proj}"
            f"/locations/{loc}/publishers/google/models/{mdl}:generateContent"
        )
        token = _VERTEX_TOKEN_CACHE.get_token(force_refresh=(attempt > 0 and isinstance(last_err, urllib.error.HTTPError) and last_err.code == 401))
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": proj,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            txt = raw["candidates"][0]["content"]["parts"][0]["text"]
            parsed = _decode_json_tolerant(txt)
            usage = raw.get("usageMetadata") or {}
            in_tok = int(usage.get("promptTokenCount") or 0)
            out_tok = int(usage.get("candidatesTokenCount") or 0)
            return parsed, in_tok, out_tok
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code == 401 and attempt == 0:
                _VERTEX_TOKEN_CACHE.invalidate()
                continue
            if exc.code in {429, 500, 503} and attempt < len(backoffs):
                time.sleep(backoffs[attempt] + random.uniform(0.0, 2.5))
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:260]
            except Exception:
                pass
            raise RuntimeError(f"Vertex AI HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            if attempt < len(backoffs):
                time.sleep(backoffs[attempt] + random.uniform(0.0, 2.5))
                continue
            raise RuntimeError(f"Errore di rete Vertex AI: {exc}") from exc

    raise RuntimeError(f"Vertex AI fallito dopo retry: {last_err}")


def _default_cloud_call(
    provider: str,
    api_key: str,
    prompt: str,
    *,
    project_id: Optional[str] = None,
    model: Optional[str] = None,
    thinking_budget: int = 0,
    max_output_tokens: int = 2048,
    response_schema: Optional[Mapping[str, Any]] = None,
) -> Tuple[Mapping[str, Any], int, int]:
    if provider == "vertex":
        return _vertex_generate_json(
            prompt,
            project_id=project_id,
            model=model,
            thinking_budget=thinking_budget,
            max_output_tokens=max_output_tokens,
            response_schema=response_schema,
        )

    if provider == "gemini":
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": int(max_output_tokens),
                "responseMimeType": "application/json",
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        txt = raw["candidates"][0]["content"]["parts"][0]["text"]
        usage = raw.get("usageMetadata") or {}
        return (
            json.loads(_strip_json_fences(txt)),
            int(usage.get("promptTokenCount") or 0),
            int(usage.get("candidatesTokenCount") or 0),
        )

    if provider == "deepseek":
        url = "https://api.deepseek.com/chat/completions"
        body = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        txt = raw["choices"][0]["message"]["content"]
        usage = raw.get("usage") or {}
        return (
            json.loads(_strip_json_fences(txt)),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

    raise ValueError(f"Provider sconosciuto: {provider!r}")


def _write_status_file(status_file: Optional[Path], payload: Mapping[str, Any]) -> None:
    if status_file is None:
        return
    status_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = status_file.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, status_file)


def _log_block_extraction(
    conn: sqlite3.Connection,
    *,
    block_pk: int,
    block_uid: str,
    extraction: BlockExtractionV21,
    provider_model: str,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO block_extraction_log (
            block_pk, block_uid, yield, provider_model, units_count, has_sig, processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(block_pk) DO UPDATE SET
            yield = excluded.yield,
            provider_model = excluded.provider_model,
            units_count = excluded.units_count,
            has_sig = excluded.has_sig,
            processed_at = excluded.processed_at
        """,
        (
            block_pk,
            block_uid,
            extraction.block_yield.value,
            provider_model,
            len(extraction.units),
            1 if extraction.sig is not None else 0,
            now_iso,
        ),
    )


def _expand_compact_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Espande le chiavi wire compatte (`y,d,t,p,yr,u,s`) nello schema canonico `BlockExtraction v2.2`."""
    if "yield" in item:
        return dict(item)
    expanded: Dict[str, Any] = {
        "yield": item.get("y"),
        "macro_disciplines": item.get("d") or [],
        "topics": item.get("t") or [],
        "places": item.get("p") or [],
        "years": item.get("yr") or [],
    }
    if "u" in item:
        raw_units = item.get("u") or []
        expanded_units = []
        for u in raw_units:
            if not isinstance(u, Mapping):
                continue
            if "kind" in u:
                expanded_units.append(dict(u))
            else:
                expanded_units.append(
                    {
                        "kind": u.get("k"),
                        "mode": u.get("m"),
                        "stmt": u.get("st"),
                        "quote": u.get("q"),
                        "who": u.get("w") or [],
                        "vs": u.get("v"),
                        "concepts": u.get("c") or [],
                    }
                )
        expanded["units"] = expanded_units
        raw_sig = item.get("s")
        if isinstance(raw_sig, Mapping):
            if "mech" in raw_sig:
                expanded["sig"] = dict(raw_sig)
            else:
                expanded["sig"] = {
                    "op_tags": raw_sig.get("op") or [],
                    "role": raw_sig.get("r"),
                    "mech": raw_sig.get("mc"),
                }
        else:
            expanded["sig"] = None
    return expanded


def _extract_single_row(
    row: sqlite3.Row,
    *,
    provider: str,
    api_key: str,
    project_id: Optional[str],
    model: Optional[str],
    llm_fn: Optional[Callable[[str, sqlite3.Row], Mapping[str, Any]]],
    require_v22_metadata: bool = False,
    metadata_only: bool = False,
) -> Tuple[sqlite3.Row, Optional[BlockExtractionV21], int, int, Optional[str]]:
    if require_v22_metadata or metadata_only:
        base_prompt = build_multiblock_extraction_prompt(
            book_title=str(row["book_title"] or ""),
            surface_domain=str(row["surface_domain"] or ""),
            rows=[row],
            single_v22_only=True,
            metadata_only=metadata_only,
        )
    else:
        base_prompt = build_block_extraction_prompt(
            book_title=str(row["book_title"] or ""),
            surface_domain=str(row["surface_domain"] or ""),
            section_title=str(row["section_title"] or ""),
            page_start=row["page_start"],
            content=str(row["content"]),
        )
    schema = (
        V22_SINGLE_METADATA_RESPONSE_SCHEMA
        if metadata_only
        else (V22_SINGLE_COMPACT_RESPONSE_SCHEMA if require_v22_metadata else None)
    )
    total_in = 0
    total_out = 0
    prompt = base_prompt

    for attempt in range(2):
        try:
            if llm_fn is not None:
                raw_payload = llm_fn(prompt, row)
                in_tok = max(1, len(prompt) // 4)
                out_tok = max(1, len(json.dumps(raw_payload, ensure_ascii=False)) // 4)
            else:
                raw_payload, in_tok, out_tok = _default_cloud_call(
                    provider,
                    api_key,
                    prompt,
                    project_id=project_id,
                    model=model,
                    thinking_budget=0,
                    max_output_tokens=1024 if metadata_only else (3072 if require_v22_metadata else 2048),
                    response_schema=schema if provider == "vertex" else None,
                )
            total_in += in_tok
            total_out += out_tok
            candidate = _expand_compact_item(raw_payload)
            if metadata_only:
                ext = validate_v22_metadata_only(candidate)
            else:
                ext = validate_block_extraction(
                    candidate,
                    block_content=str(row["content"]),
                    require_v22_metadata=require_v22_metadata,
                )
                if ext.sig is not None and _META_MECH_BOILERPLATE_RE.search(ext.sig.mech):
                    raise SchemaValidationError(
                        "sig.mech non deve iniziare con formule meta come 'Il meccanismo descrive...' o 'Il testo descrive...'"
                    )
            return row, ext, total_in, total_out, None
        except (SchemaValidationError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if attempt == 0:
                prompt = (
                    f"{base_prompt}\n"
                    f"ATTENZIONE CORREZIONE OBBLIGATORIA: il tentativo precedente ha violato questa regola: {exc}. "
                    "Copia la citazione verbatim carattere-per-carattere senza modificare refusi OCR o comandi LaTeX."
                )
                continue
            return row, None, total_in, total_out, str(exc)
        except Exception as exc:
            return row, None, total_in, total_out, str(exc)

    return row, None, total_in, total_out, "errore sconosciuto"


def _parse_window_extractions_payload(raw_payload: Mapping[str, Any]) -> Dict[int, Mapping[str, Any]]:
    by_pk: Dict[int, Mapping[str, Any]] = {}
    if not isinstance(raw_payload, Mapping):
        return by_pk
    items = raw_payload.get("items") if "items" in raw_payload else raw_payload.get("extractions")
    if not isinstance(items, list):
        return by_pk
    for item in items:
        if not isinstance(item, Mapping):
            continue
        raw_bpk = item.get("b") if "b" in item else item.get("block_pk")
        if raw_bpk is None:
            continue
        try:
            bpk = int(raw_bpk)
        except (TypeError, ValueError):
            continue
        cleaned = {k: v for k, v in item.items() if k not in ("b", "block_pk")}
        by_pk[bpk] = _expand_compact_item(cleaned)
    return by_pk


def _extract_window(
    window_rows: Sequence[sqlite3.Row],
    *,
    provider: str,
    api_key: str,
    project_id: Optional[str],
    model: Optional[str],
    llm_fn: Optional[Callable[[str, Any], Mapping[str, Any]]],
    require_v22_metadata: bool = True,
) -> List[Tuple[sqlite3.Row, Optional[BlockExtractionV21], int, int, Optional[str]]]:
    """Estrae una finestra di `1..8` blocchi dello stesso libro ammortizzando il prompt + `responseSchema`."""
    is_metadata_only = (
        llm_fn is None
        and require_v22_metadata
        and all(
            "existing_units_cnt" in r.keys() and int(r["existing_units_cnt"] or 0) > 0
            for r in window_rows
        )
    )
    if len(window_rows) == 1:
        res = _extract_single_row(
            window_rows[0],
            provider=provider,
            api_key=api_key,
            project_id=project_id,
            model=model,
            llm_fn=llm_fn,
            require_v22_metadata=require_v22_metadata,
            metadata_only=is_metadata_only,
        )
        return [res]

    lead = window_rows[0]
    prompt = build_multiblock_extraction_prompt(
        book_title=str(lead["book_title"] or ""),
        surface_domain=str(lead["surface_domain"] or ""),
        rows=window_rows,
        single_v22_only=False,
        metadata_only=is_metadata_only,
    )
    schema = (
        V22_METADATA_ONLY_RESPONSE_SCHEMA
        if is_metadata_only
        else (V22_COMPACT_RESPONSE_SCHEMA if require_v22_metadata else None)
    )
    win_in = 0
    win_out = 0
    by_pk: Dict[int, Mapping[str, Any]] = {}
    window_call_err: Optional[str] = None

    try:
        if llm_fn is not None:
            raw_payload = llm_fn(prompt, list(window_rows))
            win_in = max(1, len(prompt) // 4)
            win_out = max(1, len(json.dumps(raw_payload, ensure_ascii=False)) // 4)
        else:
            raw_payload, win_in, win_out = _default_cloud_call(
                provider,
                api_key,
                prompt,
                project_id=project_id,
                model=model,
                thinking_budget=0,
                max_output_tokens=4096 if is_metadata_only else 8192,
                response_schema=schema if provider == "vertex" else None,
            )
        by_pk = _parse_window_extractions_payload(raw_payload)
    except Exception as exc:
        window_call_err = str(exc)

    n = len(window_rows)
    base_in_share = win_in // n
    base_out_share = win_out // n
    rem_in = win_in % n
    rem_out = win_out % n

    outputs: List[Tuple[sqlite3.Row, Optional[BlockExtractionV21], int, int, Optional[str]]] = []
    for idx, row in enumerate(window_rows):
        r_in = base_in_share + (1 if idx < rem_in else 0)
        r_out = base_out_share + (1 if idx < rem_out else 0)
        bpk = int(row["block_pk"])
        candidate = by_pk.get(bpk)
        err_msg: Optional[str] = window_call_err
        if candidate is not None:
            try:
                if is_metadata_only:
                    ext = validate_v22_metadata_only(candidate)
                else:
                    ext = _validate_with_unit_salvage(
                        candidate,
                        block_content=str(row["content"]),
                        require_v22_metadata=require_v22_metadata,
                    )
                outputs.append((row, ext, r_in, r_out, None))
                continue
            except (SchemaValidationError, KeyError, TypeError, ValueError) as exc:
                err_msg = str(exc)
        else:
            err_msg = err_msg or f"block_pk={bpk} assente da items[]"

        # Riparazione mirata a blocco singolo solo se questo specifico blocco ha fallito
        rep_row, rep_ext, rep_in, rep_out, rep_err = _extract_single_row(
            row,
            provider=provider,
            api_key=api_key,
            project_id=project_id,
            model=model,
            llm_fn=llm_fn if llm_fn is None else None,
            require_v22_metadata=require_v22_metadata,
            metadata_only=is_metadata_only,
        ) if llm_fn is None else (row, None, 0, 0, err_msg)
        outputs.append((rep_row, rep_ext, r_in + rep_in, r_out + rep_out, rep_err))

    return outputs


def _apply_anti_template_filter(
    valid_pairs: List[Tuple[sqlite3.Row, BlockExtractionV21]],
    rejected: List[Dict[str, Any]],
) -> Tuple[List[Tuple[sqlite3.Row, BlockExtractionV21]], int]:
    """Applica il gate anti-template scartando solo le righe col prefisso ripetuto."""
    if not valid_pairs:
        return valid_pairs, 0
    valid_exts = [ext for _, ext in valid_pairs]
    try:
        validate_batch_anti_template(valid_exts)
        return valid_pairs, 0
    except SchemaValidationError as batch_err:
        prefixes = [
            " ".join(ext.sig.mech.casefold().split()[:4])
            for _, ext in valid_pairs
            if ext.sig is not None
        ]
        bad_prefix = Counter(prefixes).most_common(1)[0][0] if prefixes else ""
        filtered_pairs: List[Tuple[sqlite3.Row, BlockExtractionV21]] = []
        dropped = 0
        for row, ext in valid_pairs:
            if (
                ext.sig is not None
                and bad_prefix
                and " ".join(ext.sig.mech.casefold().split()[:4]) == bad_prefix
            ):
                dropped += 1
                rejected.append({"block_pk": int(row["block_pk"]), "error": str(batch_err)})
            else:
                filtered_pairs.append((row, ext))
        return filtered_pairs, dropped


def run_batch_extraction(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    wave: Optional[int] = None,
    limit: Optional[int] = 50,
    provider: str = "vertex",
    dry_run: bool = False,
    workers: int = 8,
    batch_size: int = 25,
    pack_size: Optional[int] = None,
    require_v22_metadata: Optional[bool] = None,
    include_v21_backfill: bool = False,
    book_pk: Optional[int] = None,
    block_pks: Optional[Sequence[int]] = None,
    discover_bridges: bool = False,
    status_file: Optional[Path] = None,
    project_id: Optional[str] = None,
    model: Optional[str] = None,
    llm_fn: Optional[Callable[[str, Any], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Esegue un ciclo idempotente di estrazione `BlockExtraction v2.1 / v2.2` con finestre multi-blocco."""
    from resuscipack.corpus.schema import init_corpus_db

    eff_pack = int(pack_size) if pack_size is not None else (1 if llm_fn is not None else 8)
    eff_v22 = bool(require_v22_metadata) if require_v22_metadata is not None else (llm_fn is None)

    conn = init_corpus_db(db_path)

    try:
        pending = select_pending_blocks(
            conn,
            wave=wave,
            limit=limit,
            pack_size=eff_pack,
            include_v21_backfill=include_v21_backfill,
            book_pk=book_pk,
            block_pks=block_pks,
        )
        budget = estimate_wave_budget(pending, pack_size=eff_pack)
        if dry_run:
            return {"mode": "dry_run", "wave": wave, **budget}

        api_key = ""
        if llm_fn is None:
            if provider == "vertex":
                _VERTEX_TOKEN_CACHE.get_token()
            else:
                api_key = _resolve_api_key(provider)

        effective_model = model or (
            DEFAULT_VERTEX_MODEL
            if provider == "vertex"
            else ("gemini-2.5-flash" if provider == "gemini" else "deepseek-chat")
        )
        provider_label = f"{provider}:{effective_model}"

        books_in_wave = len({int(r["book_pk"]) for r in pending}) if pending else 0
        blocks_total_in_wave = len(pending)
        blocks_completed = 0
        blocks_rejected = 0
        units_written = 0
        sigs_written = 0
        v22_metadata_written = 0
        paratext_logged = 0
        in_tokens_used = 0
        out_tokens_used = 0
        rejected: List[Dict[str, Any]] = []
        bridges_validated_total = 0

        def _estimate_eur(tok_in: int, tok_out: int) -> float:
            usd = (tok_in / 1e6) * 0.30 + (tok_out / 1e6) * 2.50
            return round(usd * 0.92, 4)

        def _emit_status(state_name: str) -> None:
            if status_file is None:
                return
            tot_units_db = int(conn.execute("SELECT COUNT(*) FROM epistemic_units").fetchone()[0])
            tot_sigs_db = int(conn.execute("SELECT COUNT(*) FROM structural_signatures").fetchone()[0])
            tot_bridges_db = int(
                conn.execute("SELECT COUNT(*) FROM curiosity_bridges WHERE status = 'validated'").fetchone()[0]
            )
            _write_status_file(
                status_file,
                {
                    "state": state_name,
                    "wave": wave,
                    "provider": provider_label,
                    "pack_size": eff_pack,
                    "books_in_wave": books_in_wave,
                    "blocks_total_in_wave": blocks_total_in_wave,
                    "blocks_completed": blocks_completed,
                    "blocks_rejected": blocks_rejected,
                    "paratext_logged": paratext_logged,
                    "epistemic_units_total": tot_units_db,
                    "signatures_total": tot_sigs_db,
                    "v22_metadata_written": v22_metadata_written,
                    "bridges_total": tot_bridges_db,
                    "input_tokens_used": in_tokens_used,
                    "output_tokens_used": out_tokens_used,
                    "estimated_eur_from_credits": _estimate_eur(in_tokens_used, out_tokens_used),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        token_lock = threading.Lock()

        def _bridge_llm_adapter(prompt: str) -> Mapping[str, Any]:
            if llm_fn is not None:
                return llm_fn(prompt, pending[0])  # type: ignore[arg-type]
            parsed, b_in, b_out = _default_cloud_call(
                provider,
                api_key,
                prompt,
                project_id=project_id,
                model=model,
                thinking_budget=512,
            )
            nonlocal in_tokens_used, out_tokens_used
            with token_lock:
                in_tokens_used += b_in
                out_tokens_used += b_out
            return parsed

        _emit_status("running")

        n_workers = max(1, min(int(workers), 16))
        windows = group_rows_into_book_windows(pending, pack_size=eff_pack)
        win_per_commit = max(1, (int(batch_size) + eff_pack - 1) // eff_pack)
        blocks_since_bridge = 0

        try:
            for start in range(0, len(windows), win_per_commit):
                win_chunk = windows[start : start + win_per_commit]
                if n_workers > 1 and len(win_chunk) > 1:
                    with ThreadPoolExecutor(max_workers=n_workers) as pool:
                        nested_results = list(
                            pool.map(
                                lambda wrows: _extract_window(
                                    wrows,
                                    provider=provider,
                                    api_key=api_key,
                                    project_id=project_id,
                                    model=model,
                                    llm_fn=llm_fn,
                                    require_v22_metadata=eff_v22,
                                ),
                                win_chunk,
                            )
                        )
                else:
                    nested_results = [
                        _extract_window(
                            wrows,
                            provider=provider,
                            api_key=api_key,
                            project_id=project_id,
                            model=model,
                            llm_fn=llm_fn,
                            require_v22_metadata=eff_v22,
                        )
                        for wrows in win_chunk
                    ]

                results = [item for sub in nested_results for item in sub]
                valid_pairs: List[Tuple[sqlite3.Row, BlockExtractionV21]] = []
                for row, ext, tok_in, tok_out, err in results:
                    in_tokens_used += tok_in
                    out_tokens_used += tok_out
                    if ext is None:
                        blocks_rejected += 1
                        rejected.append({"block_pk": int(row["block_pk"]), "error": err or "errore"})
                    else:
                        valid_pairs.append((row, ext))

                valid_pairs, dropped_cnt = _apply_anti_template_filter(valid_pairs, rejected)
                blocks_rejected += dropped_cnt

                for row, ext in valid_pairs:
                    bpk = int(row["block_pk"])
                    buid = str(row["block_uid"])
                    has_existing_units = (
                        "existing_units_cnt" in row.keys()
                        and int(row["existing_units_cnt"] or 0) > 0
                    )
                    if has_existing_units and ext.units == ():
                        wrote_v22 = persist_v22_metadata_only(conn, block_pk=bpk, payload=ext)
                        if wrote_v22:
                            v22_metadata_written += 1
                        elif ext.block_yield is BlockYield.LOW_OR_PARATEXT:
                            paratext_logged += 1
                        blocks_completed += 1
                        continue

                    n_u = persist_block_extraction(
                        conn,
                        block_pk=bpk,
                        block_uid=buid,
                        extraction=ext,
                    )
                    _log_block_extraction(
                        conn,
                        block_pk=bpk,
                        block_uid=buid,
                        extraction=ext,
                        provider_model=provider_label,
                    )
                    units_written += n_u
                    if ext.macro_disciplines:
                        v22_metadata_written += 1
                    if ext.units == ():
                        paratext_logged += 1
                    if ext.sig is not None:
                        sigs_written += 1
                    blocks_completed += 1
                    blocks_since_bridge += 1

                conn.commit()

                if discover_bridges and blocks_since_bridge >= 200:
                    b_res = discover_and_validate_bridges(
                        conn,
                        _bridge_llm_adapter,
                        top_k_per_node=5,
                        archetypes=DEFAULT_NODE_ARCHETYPES,
                        max_workers=min(4, n_workers),
                    )
                    bridges_validated_total += int(b_res.get("bridges_validated") or 0)
                    blocks_since_bridge = 0

                _emit_status("running")

            if discover_bridges and (blocks_since_bridge > 0 or len(pending) == 0):
                b_res = discover_and_validate_bridges(
                    conn,
                    _bridge_llm_adapter,
                    top_k_per_node=5,
                    archetypes=DEFAULT_NODE_ARCHETYPES,
                    max_workers=min(4, n_workers),
                )
                bridges_validated_total += int(b_res.get("bridges_validated") or 0)

            _emit_status("completed")
        except Exception:
            _emit_status("failed")
            raise

        eur_sync = _estimate_eur(in_tokens_used, out_tokens_used)
        return {
            "mode": "executed",
            "wave": wave,
            "provider": provider_label,
            "pack_size": eff_pack,
            "windows_sent": len(windows),
            "books_in_wave": books_in_wave,
            "blocks_processed": blocks_completed,
            "blocks_rejected": blocks_rejected,
            "paratext_logged": paratext_logged,
            "rejected_details": rejected,
            "units_written": units_written,
            "signatures_written": sigs_written,
            "v22_metadata_written": v22_metadata_written,
            "bridges_validated": bridges_validated_total,
            "input_tokens_used": in_tokens_used,
            "output_tokens_used": out_tokens_used,
            "estimated_eur_from_credits": eur_sync,
            "equivalent_vertex_batch_eur": round(eur_sync * 0.5, 4),
            "eur_per_100_blocks_sync": round((eur_sync / blocks_total_in_wave) * 100.0, 4) if blocks_total_in_wave else 0.0,
            "eur_per_100_blocks_batch": round(((eur_sync * 0.5) / blocks_total_in_wave) * 100.0, 4) if blocks_total_in_wave else 0.0,
        }
    finally:
        conn.close()


def export_multiblock_batch_jsonl(
    conn: sqlite3.Connection,
    out_jsonl_path: Path | str,
    *,
    wave: Optional[int] = None,
    limit: Optional[int] = None,
    pack_size: int = 8,
    include_v21_backfill: bool = False,
    book_pk: Optional[int] = None,
    block_pks: Optional[Sequence[int]] = None,
    shard_size: Optional[int] = None,
    retry_notes: Optional[Mapping[int, str]] = None,
    thinking_budget: int = 0,
) -> Dict[str, Any]:
    """Esporta le finestre multi-blocco nel formato nativo Vertex AI `batchPredictionJobs` (-50%,
    solo chiave radice `request` senza `custom_id`), opzionalmente suddiviso in shard JSONL."""
    pending = select_pending_blocks(
        conn,
        wave=wave,
        limit=limit,
        pack_size=pack_size,
        include_v21_backfill=include_v21_backfill,
        book_pk=book_pk,
        block_pks=block_pks,
    )
    windows = group_rows_into_book_windows(pending, pack_size=pack_size)
    out_path = Path(out_jsonl_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_map: Dict[str, List[int]] = {}

    eff_shard = int(shard_size) if (shard_size and int(shard_size) > 0) else 0
    jsonl_paths: List[str] = []

    def _build_record(widx: int, wrows: Sequence[sqlite3.Row]) -> str:
        lead = wrows[0]
        bpk_book = int(lead["book_pk"])
        cid = f"win_{widx:06d}_bk{bpk_book}"
        manifest_map[cid] = [int(r["block_pk"]) for r in wrows]
        is_meta = all(
            "existing_units_cnt" in r.keys() and int(r["existing_units_cnt"] or 0) > 0
            for r in wrows
        )
        prompt_core = build_multiblock_extraction_prompt(
            book_title=str(lead["book_title"] or ""),
            surface_domain=str(lead["surface_domain"] or ""),
            rows=wrows,
            single_v22_only=False,
            metadata_only=is_meta,
        )
        has_retry = False
        if retry_notes:
            notes = [
                str(retry_notes[int(r["block_pk"])])
                for r in wrows
                if int(r["block_pk"]) in retry_notes
            ]
            if notes:
                has_retry = True
                prompt_core += (
                    "\nATTENZIONE CORREZIONE OBBLIGATORIA DAL TENTATIVO PRECEDENTE:\n"
                    + "\n".join(notes)
                    + "\nREGOLE DI RIPARAZIONE: (1) NON sintetizzare o parafrasare a memoria: "
                    "`q` DEVE essere copiata parola-per-parola esattamente come appare stampata nel brano sopra "
                    "(5..14 parole contigue, inclusi eventuali refusi/spaziature OCR); "
                    "(2) Se il brano contiene solo formule/codice senza frasi compiute, intestazioni/slide "
                    "frammentarie, tabelle numeriche o codifica font corrotta/illeggibile (`*0!6...`, caratteri di "
                    "controllo, testo capovolto), DEVI restituire `y`='low_or_paratext', `d`=[], `t`=[], `p`=[], "
                    "`yr`=[], `u`=[], `s`=null.\n"
                )
        record = {
            "request": {
                "contents": [{"role": "user", "parts": [{"text": f"[WIN_ID={cid}]\n{prompt_core}"}]}],
                "generationConfig": {
                    "temperature": 0.25 if has_retry else 0.1,
                    "maxOutputTokens": 4096 if is_meta else 8192,
                    "responseMimeType": "application/json",
                    "responseSchema": V22_METADATA_ONLY_RESPONSE_SCHEMA if is_meta else V22_COMPACT_RESPONSE_SCHEMA,
                    "thinkingConfig": {"thinkingBudget": max(0, int(thinking_budget))},
                },
            }
        }
        return json.dumps(record, ensure_ascii=False)

    if eff_shard == 0 or len(windows) <= eff_shard:
        with out_path.open("w", encoding="utf-8") as fh:
            for widx, wrows in enumerate(windows, start=1):
                fh.write(_build_record(widx, wrows) + "\n")
        jsonl_paths.append(str(out_path))
    else:
        for s_idx, start in enumerate(range(0, len(windows), eff_shard), start=1):
            chunk = windows[start : start + eff_shard]
            spath = out_path.with_name(f"{out_path.stem}_part{s_idx:02d}{out_path.suffix}")
            with spath.open("w", encoding="utf-8") as fh:
                for offset, wrows in enumerate(chunk, start=start + 1):
                    fh.write(_build_record(offset, wrows) + "\n")
            jsonl_paths.append(str(spath))

    manifest_path = out_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest_map, indent=2), encoding="utf-8")
    return {
        "jsonl_path": jsonl_paths[0],
        "jsonl_paths": jsonl_paths,
        "manifest_path": str(manifest_path),
        "windows_exported": len(windows),
        "blocks_exported": len(pending),
    }


def upload_file_to_gcs(local_path: Path, gcs_uri: str) -> None:
    subprocess.run(
        ["gcloud", "storage", "cp", str(local_path), gcs_uri],
        env=_gcloud_env(),
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )


def download_gcs_prefix(gcs_prefix: str, local_dir: Path) -> List[Path]:
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gcloud", "storage", "cp", "-r", f"{gcs_prefix.rstrip('/')}/*", str(local_dir)],
        env=_gcloud_env(),
        capture_output=True,
        text=True,
        timeout=600,
        check=True,
    )
    return sorted(local_dir.rglob("*.jsonl"))


def _vertex_batch_json(
    url: str,
    *,
    project_id: str,
    data: Optional[bytes] = None,
    method: str = "GET",
    timeout: int = 30,
    err_prefix: str = "Vertex Batch",
) -> Dict[str, Any]:
    """Esegue una richiesta REST Vertex Batch con refresh automatico del token su 401."""
    for attempt in range(2):
        token = _VERTEX_TOKEN_CACHE.get_token(force_refresh=(attempt > 0))
        headers = {
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": project_id,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 0:
                _VERTEX_TOKEN_CACHE.invalidate()
                continue
            detail = exc.read().decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"{err_prefix} HTTP {exc.code}: {detail}") from exc
    raise RuntimeError(f"{err_prefix}: tentativi esauriti")


def submit_vertex_batch_job(
    gcs_input_uris: Sequence[str],
    gcs_output_prefix: str,
    display_name: str,
    *,
    project_id: str = DEFAULT_GCP_PROJECT,
    location: str = DEFAULT_BATCH_LOCATION,
    model: str = DEFAULT_VERTEX_MODEL,
    labels: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Invia un `batchPredictionJob` nativo a Vertex AI (`-50%` sui token Batch)."""
    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/batchPredictionJobs"
    job_labels = {"env": "datacloud_antigravity", **(dict(labels) if labels else {})}
    payload = {
        "displayName": display_name,
        "model": f"publishers/google/models/{model}",
        "inputConfig": {
            "instancesFormat": "jsonl",
            "gcsSource": {"uris": list(gcs_input_uris)},
        },
        "outputConfig": {
            "predictionsFormat": "jsonl",
            "gcsDestination": {"outputUriPrefix": gcs_output_prefix.rstrip("/") + "/"},
        },
        "labels": job_labels,
    }
    return _vertex_batch_json(
        url,
        project_id=project_id,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        timeout=60,
        err_prefix="Vertex Batch submit",
    )


def get_vertex_batch_job(job_name: str, *, project_id: str = DEFAULT_GCP_PROJECT) -> Dict[str, Any]:
    """Legge lo stato live (`JOB_STATE_*`, errori, outputInfo) di un `batchPredictionJob`."""
    m = re.search(r"locations/([^/]+)/", job_name)
    location = m.group(1) if m else DEFAULT_BATCH_LOCATION
    url = f"https://{location}-aiplatform.googleapis.com/v1/{job_name}"
    return _vertex_batch_json(
        url,
        project_id=project_id,
        method="GET",
        timeout=30,
        err_prefix="Vertex Batch get",
    )


def _validate_with_unit_salvage(
    ext_dict: Mapping[str, Any],
    *,
    block_content: str,
    require_v22_metadata: bool,
) -> BlockExtractionV21:
    """Valida `BlockExtraction` provando prima il payload completo, poi azzerando `sig` se spurio
    e infine salvando il sottoinsieme di `units` che superano tutti i gate deterministici."""

    def _check_full(d: Mapping[str, Any]) -> BlockExtractionV21:
        ext = validate_block_extraction(
            d,
            block_content=block_content,
            require_v22_metadata=require_v22_metadata,
        )
        if ext.sig is not None and _META_MECH_BOILERPLATE_RE.search(ext.sig.mech):
            raise SchemaValidationError(
                "sig.mech non deve iniziare con formule meta come 'Il meccanismo descrive...'"
            )
        return ext

    try:
        return _check_full(ext_dict)
    except SchemaValidationError as primary_exc:
        if ext_dict.get("sig") is not None:
            try:
                return _check_full({**ext_dict, "sig": None})
            except SchemaValidationError:
                pass
        raw_units = ext_dict.get("units")
        if isinstance(raw_units, list) and len(raw_units) > 1:
            good_units = []
            for u in raw_units:
                try:
                    _check_full({**ext_dict, "units": [u], "sig": None})
                    good_units.append(u)
                except SchemaValidationError:
                    continue
            if good_units:
                try:
                    return _check_full({**ext_dict, "units": good_units})
                except SchemaValidationError:
                    return _check_full({**ext_dict, "units": good_units, "sig": None})
        raise primary_exc


def import_multiblock_batch_jsonl(
    conn: sqlite3.Connection,
    predictions_jsonl_path: Path | str | Sequence[Path | str],
    *,
    provider_model: str = "vertex-batch:gemini-2.5-flash",
    require_v22_metadata: bool = True,
) -> Dict[str, Any]:
    """Valida e persiste idempotentemente i risultati restituiti da uno o più file/cartelle
    Vertex AI Batch Prediction JSONL."""
    if isinstance(predictions_jsonl_path, (Path, str)):
        p = Path(predictions_jsonl_path)
        if not p.exists():
            raise FileNotFoundError(f"File/cartella JSONL predizioni non trovato: {p}")
        pred_files = sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    else:
        pred_files = [Path(x) for x in predictions_jsonl_path]
        for pf in pred_files:
            if not pf.exists():
                raise FileNotFoundError(f"File JSONL predizioni non trovato: {pf}")

    rows_by_pk: Dict[int, sqlite3.Row] = {}
    conn.row_factory = sqlite3.Row
    for r in conn.execute("SELECT block_pk, block_uid, content FROM blocks WHERE is_active = 1"):
        rows_by_pk[int(r["block_pk"])] = r
    existing_unit_pks = {
        int(r[0]) for r in conn.execute("SELECT DISTINCT block_pk FROM epistemic_units")
    }
    already_done_pks = {
        int(r[0])
        for r in conn.execute(
            """
            SELECT l.block_pk FROM block_extraction_log l
            WHERE l.yield = 'low_or_paratext'
               OR EXISTS (SELECT 1 FROM block_metadata_v22 m WHERE m.block_pk = l.block_pk)
            """
        )
    }

    windows_read = 0
    windows_parse_failed = 0
    blocks_committed = 0
    blocks_rejected = 0
    units_written = 0
    v22_written = 0
    in_tok = 0
    out_tok = 0
    rejected: List[Dict[str, Any]] = []
    valid_pairs: List[Tuple[sqlite3.Row, BlockExtractionV21]] = []

    for pred_path in pred_files:
        with pred_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                windows_read += 1
                try:
                    obj = json.loads(s)
                    resp = obj.get("response") if isinstance(obj, Mapping) else obj
                    if isinstance(resp, Mapping) and "candidates" in resp:
                        usage = resp.get("usageMetadata") or {}
                        in_tok += int(usage.get("promptTokenCount") or 0)
                        out_tok += int(usage.get("candidatesTokenCount") or 0)
                        txt = resp["candidates"][0]["content"]["parts"][0]["text"]
                        payload = _decode_json_tolerant(txt)
                    else:
                        payload = obj
                except Exception as exc:
                    windows_parse_failed += 1
                    rejected.append({"block_pk": -1, "error": f"window_parse_error: {exc}"})
                    continue

                by_pk = _parse_window_extractions_payload(payload)
                req_obj = obj.get("request") if isinstance(obj, Mapping) else None
                if isinstance(req_obj, Mapping) and len(by_pk) == 1:
                    req_txt = "".join(
                        str(pt.get("text") or "")
                        for ct in (req_obj.get("contents") or [])
                        if isinstance(ct, Mapping)
                        for pt in (ct.get("parts") or [])
                        if isinstance(pt, Mapping)
                    )
                    prompt_pks = [int(x) for x in re.findall(r"\[B:block_pk=(\d+)\|", req_txt)]
                    if len(prompt_pks) == 1 and next(iter(by_pk)) not in rows_by_pk:
                        only_val = next(iter(by_pk.values()))
                        by_pk = {prompt_pks[0]: only_val}
                for bpk, ext_dict in by_pk.items():
                    if bpk in already_done_pks:
                        continue
                    blk_row = rows_by_pk.get(bpk)
                    if blk_row is None:
                        blocks_rejected += 1
                        rejected.append({"block_pk": bpk, "error": "block_pk assente o inattivo"})
                        continue
                    try:
                        if bpk in existing_unit_pks and not ext_dict.get("units"):
                            ext = validate_v22_metadata_only(ext_dict)
                        else:
                            ext = _validate_with_unit_salvage(
                                ext_dict,
                                block_content=str(blk_row["content"]),
                                require_v22_metadata=require_v22_metadata,
                            )
                        valid_pairs.append((blk_row, ext))
                    except (SchemaValidationError, KeyError, TypeError, ValueError) as exc:
                        blocks_rejected += 1
                        rejected.append({"block_pk": bpk, "error": str(exc)})

    valid_pairs, dropped_cnt = _apply_anti_template_filter(valid_pairs, rejected)
    blocks_rejected += dropped_cnt

    for blk_row, ext in valid_pairs:
        bpk = int(blk_row["block_pk"])
        buid = str(blk_row["block_uid"])
        if ext.units == () and bpk in existing_unit_pks:
            if persist_v22_metadata_only(conn, block_pk=bpk, payload=ext):
                v22_written += 1
            if ext.block_yield is BlockYield.LOW_OR_PARATEXT:
                _log_block_extraction(
                    conn,
                    block_pk=bpk,
                    block_uid=buid,
                    extraction=ext,
                    provider_model=provider_model,
                )
            blocks_committed += 1
            continue
        n_u = persist_block_extraction(conn, block_pk=bpk, block_uid=buid, extraction=ext)
        _log_block_extraction(
            conn,
            block_pk=bpk,
            block_uid=buid,
            extraction=ext,
            provider_model=provider_model,
        )
        units_written += n_u
        if ext.macro_disciplines:
            v22_written += 1
        blocks_committed += 1

    conn.commit()
    return {
        "files_read": len(pred_files),
        "windows_read": windows_read,
        "windows_parse_failed": windows_parse_failed,
        "blocks_committed": blocks_committed,
        "blocks_rejected": blocks_rejected,
        "units_written": units_written,
        "v22_written": v22_written,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "rejected_details": rejected,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="CLI Batch Idempotente BlockExtraction v2.1 / v2.2 per Wave 1..4 di resuscipack."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso di pack_corpus.db")
    parser.add_argument("--wave", type=int, choices=[1, 2, 3, 4], default=None, help="Filtra per Wave 1..4")
    parser.add_argument("--limit", type=int, default=50, help="Massimo numero di blocchi per run (0 = tutti)")
    parser.add_argument(
        "--provider",
        choices=["vertex", "gemini", "deepseek"],
        default="vertex",
        help="Backend LLM: default `vertex` sui crediti Google Cloud attivi",
    )
    parser.add_argument("--workers", type=int, default=8, help="Worker concorrenti HTTP per micro-batch")
    parser.add_argument("--batch-size", type=int, default=25, help="Blocchi per commit transazionale")
    parser.add_argument("--pack-size", type=int, default=8, help="Blocchi contigui per finestra (1..8)")
    parser.add_argument("--book-pk", type=int, default=None, help="Filtra un singolo book_pk")
    parser.add_argument(
        "--block-pks",
        type=str,
        default=None,
        help="Lista CSV di block_pk specifici da elaborare (es. 28052,28053,28054)",
    )
    parser.add_argument("--backfill-v22", action="store_true", help="Include blocchi v2.1 privi di metadati v2.2")
    parser.add_argument("--export-batch-jsonl", type=Path, default=None, help="Esporta JSONL per Vertex AI Batch (-50%%)")
    parser.add_argument("--import-batch-jsonl", type=Path, default=None, help="Importa JSONL predetto da Vertex AI Batch")
    parser.add_argument(
        "--discover-bridges",
        action="store_true",
        help="Scopre e valida nuovi ponti Libro Sbagliato su curiosity_bridges",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_PATH,
        help="File JSON di telemetria live per il Tavolo di Studio",
    )
    parser.add_argument("--dry-run", action="store_true", help="Calcola volumi e costi reali senza chiamate API")
    parser.add_argument(
        "--seed-empirical",
        action="store_true",
        help="Inserisce i 3 ponti empirici verificati (Marconi, Galvani, Cartesio) in pack_corpus.db",
    )
    args = parser.parse_args(argv)

    if args.seed_empirical:
        res = seed_verified_empirical_bridges(args.db)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.export_batch_jsonl is not None:
        from resuscipack.corpus.schema import init_corpus_db

        conn = init_corpus_db(args.db)
        try:
            res = export_multiblock_batch_jsonl(
                conn,
                args.export_batch_jsonl,
                wave=args.wave,
                limit=args.limit if args.limit > 0 else None,
                pack_size=args.pack_size,
                include_v21_backfill=args.backfill_v22,
                book_pk=args.book_pk,
            )
        finally:
            conn.close()
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.import_batch_jsonl is not None:
        from resuscipack.corpus.schema import init_corpus_db

        conn = init_corpus_db(args.db)
        try:
            res = import_multiblock_batch_jsonl(conn, args.import_batch_jsonl)
        finally:
            conn.close()
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    parsed_block_pks: Optional[List[int]] = None
    if args.block_pks:
        parsed_block_pks = [int(tok.strip()) for tok in args.block_pks.split(",") if tok.strip()]

    try:
        res = run_batch_extraction(
            args.db,
            wave=args.wave,
            limit=args.limit if args.limit > 0 else None,
            provider=args.provider,
            dry_run=args.dry_run,
            workers=args.workers,
            batch_size=args.batch_size,
            pack_size=args.pack_size,
            include_v21_backfill=args.backfill_v22,
            book_pk=args.book_pk,
            block_pks=parsed_block_pks,
            discover_bridges=args.discover_bridges,
            status_file=None if args.dry_run else args.status_file,
        )
    except MissingCredentialsError as exc:
        print(f"ERRORE CREDENZIALI: {exc}", file=sys.stderr)
        return 2
    except SchemaValidationError as exc:
        print(f"ERRORE QUALITÀ LOTTO: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
