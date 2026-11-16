#!/usr/bin/env python3
"""CLI Batch Idempotente per l'estrazione `BlockExtraction v2.1` a ondate (Wave 1..4).

Principi non negoziabili (ADR-0002, TASK-EPIST-03, TASK-EPIST-04):
- Provider primario `vertex`: usa i crediti Google Cloud attivi (`macro-authority-492722-u7`)
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
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
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
    BlockExtractionV21,
    SchemaValidationError,
    persist_block_extraction,
    validate_batch_anti_template,
    validate_block_extraction,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pack_corpus.db"
DEFAULT_STATUS_PATH = Path(__file__).resolve().parents[2] / "data" / "wave1_status.json"
DEFAULT_GCP_PROJECT = "macro-authority-492722-u7"
DEFAULT_VERTEX_MODEL = "gemini-2.5-flash"

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
        "4. FIRMA STRUTTURALE `sig` OPZIONALE: se il brano è già un enunciato matematico/informatico "
        "astratto puro (es. manuale di analisi o algoritmi), DEVI impostare `\"sig\": null`.\n"
        "5. DOMAIN STRIPPING CONCISO (quando `sig` non è null): `sig.mech` deve essere UNA sola frase densa "
        f"di 80–240 caratteri; è VIETATO usare sostantivi aneddotici di superficie (es. {forbidden_csv}) o "
        "iniettare formule con modulo assenti dal testo; descrivi solo l'azione geometrico-operativa astratta "
        "e scegli 1..3 `op_tags` SOLO tra:\n"
        f"[{tags_csv}]\n\n"
        f"METADATI CONTESTO: titolo={book_title!r} | dominio={surface_domain!r} | "
        f"sezione={section_title!r} | pag={page_start}\n"
        "BRANO:\n"
        f"{content}\n"
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
) -> List[sqlite3.Row]:
    """Seleziona i blocchi sostantivi attivi non ancora loggati in `block_extraction_log`."""
    conn.row_factory = sqlite3.Row
    params: List[Any] = []
    filter_clause = ""

    if wave is not None:
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
    if has_log_table:
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
            bk.surface_domain
        FROM blocks bl
        JOIN books bk ON bk.book_pk = bl.book_pk
        {done_join}
        WHERE bl.is_active = 1
          AND bk.is_active = 1
          AND bl.block_role != 'paratext'
          {done_filter}
          {filter_clause}
        ORDER BY bl.book_pk ASC, bl.block_pk ASC
    """
    raw_rows = conn.execute(sql, tuple(params)).fetchall()

    # Interleaving Round-Robin per book_pk (così anche --limit 40 tocca ~40 libri diversi)
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
        if q:
            interleaved.append(q.popleft())
            if q:
                active_books.append(bpk)

    if limit is not None and limit > 0:
        return list(islice(interleaved, int(limit)))
    return interleaved


def estimate_wave_budget(rows: Sequence[sqlite3.Row]) -> Dict[str, Any]:
    """Calcola token di input/output e costi stimati USD sui blocchi pendenti (onesto, zero sconti finti)."""
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

    return {
        "pending_books": n_books,
        "pending_blocks": n_blocks,
        "estimated_input_tokens": in_tokens,
        "estimated_output_tokens": out_tokens,
        "estimated_cost_usd": {
            "vertex_gemini_2_5_flash_credits": round(cost_vertex_flash_sync, 3),
            "gemini_2_5_flash_batch": round(cost_gemini_flash_batch, 3),
            "gemini_2_5_flash_lite_batch": round(cost_flash_lite, 3),
            "deepseek_v3_batch": round(cost_deepseek, 3),
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


def _vertex_generate_json(
    prompt: str,
    *,
    project_id: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[Mapping[str, Any], int, int]:
    """Chiama Vertex AI `gemini-2.5-flash` sui crediti Google Cloud con refresh token e retry 429/503."""
    proj = project_id or os.environ.get("GCP_PROJECT_ID", DEFAULT_GCP_PROJECT)
    mdl = model or os.environ.get("VERTEX_GEMINI_MODEL", DEFAULT_VERTEX_MODEL)
    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{proj}"
        f"/locations/global/publishers/google/models/{mdl}:generateContent"
    )
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode("utf-8")

    backoffs = (2.0, 5.0)
    last_err: Optional[Exception] = None
    for attempt in range(len(backoffs) + 1):
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
            parsed = json.loads(_strip_json_fences(txt))
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
                time.sleep(backoffs[attempt])
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
                time.sleep(backoffs[attempt])
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
) -> Tuple[Mapping[str, Any], int, int]:
    if provider == "vertex":
        return _vertex_generate_json(prompt, project_id=project_id, model=model)

    if provider == "gemini":
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
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


def _extract_single_row(
    row: sqlite3.Row,
    *,
    provider: str,
    api_key: str,
    project_id: Optional[str],
    model: Optional[str],
    llm_fn: Optional[Callable[[str, sqlite3.Row], Mapping[str, Any]]],
) -> Tuple[sqlite3.Row, Optional[BlockExtractionV21], int, int, Optional[str]]:
    base_prompt = build_block_extraction_prompt(
        book_title=str(row["book_title"] or ""),
        surface_domain=str(row["surface_domain"] or ""),
        section_title=str(row["section_title"] or ""),
        page_start=row["page_start"],
        content=str(row["content"]),
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
                )
            total_in += in_tok
            total_out += out_tok
            ext = validate_block_extraction(
                raw_payload,
                block_content=str(row["content"]),
            )
            return row, ext, total_in, total_out, None
        except (SchemaValidationError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if attempt == 0:
                prompt = (
                    f"{base_prompt}\n"
                    f"ATTENZIONE CORREZIONE OBBLIGATORIA: il tuo tentativo precedente ha violato questa regola: {exc}. "
                    "Correggi rigorosamente copiando la citazione esattamente come scritta nel BRANO."
                )
                continue
            return row, None, total_in, total_out, str(exc)
        except Exception as exc:
            return row, None, total_in, total_out, str(exc)

    return row, None, total_in, total_out, "errore sconosciuto"


def run_batch_extraction(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    wave: Optional[int] = None,
    limit: Optional[int] = 50,
    provider: str = "vertex",
    dry_run: bool = False,
    workers: int = 8,
    batch_size: int = 25,
    discover_bridges: bool = False,
    status_file: Optional[Path] = None,
    project_id: Optional[str] = None,
    model: Optional[str] = None,
    llm_fn: Optional[Callable[[str, sqlite3.Row], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Esegue un ciclo idempotente di estrazione `BlockExtraction v2.1` con micro-batch concorrenti."""
    from resuscipack.corpus.schema import init_corpus_db

    conn = init_corpus_db(db_path)

    try:
        pending = select_pending_blocks(conn, wave=wave, limit=limit)
        budget = estimate_wave_budget(pending)
        if dry_run:
            return {"mode": "dry_run", "wave": wave, **budget}

        api_key = ""
        if llm_fn is None:
            if provider == "vertex":
                # Fail-honest prima di avviare thread pool
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
                    "books_in_wave": books_in_wave,
                    "blocks_total_in_wave": blocks_total_in_wave,
                    "blocks_completed": blocks_completed,
                    "blocks_rejected": blocks_rejected,
                    "paratext_logged": paratext_logged,
                    "epistemic_units_total": tot_units_db,
                    "signatures_total": tot_sigs_db,
                    "bridges_total": tot_bridges_db,
                    "input_tokens_used": in_tokens_used,
                    "output_tokens_used": out_tokens_used,
                    "estimated_eur_from_credits": _estimate_eur(in_tokens_used, out_tokens_used),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        def _bridge_llm_adapter(prompt: str) -> Mapping[str, Any]:
            if llm_fn is not None:
                return llm_fn(prompt, pending[0])  # type: ignore[arg-type]
            parsed, b_in, b_out = _default_cloud_call(
                provider, api_key, prompt, project_id=project_id, model=model
            )
            nonlocal in_tokens_used, out_tokens_used
            in_tokens_used += b_in
            out_tokens_used += b_out
            return parsed

        _emit_status("running")

        n_workers = max(1, min(int(workers), 16))
        chunk_sz = max(1, int(batch_size))
        blocks_since_bridge = 0

        for start in range(0, len(pending), chunk_sz):
            chunk = pending[start : start + chunk_sz]
            if n_workers > 1 and len(chunk) > 1:
                with ThreadPoolExecutor(max_workers=n_workers) as pool:
                    results = list(
                        pool.map(
                            lambda r: _extract_single_row(
                                r,
                                provider=provider,
                                api_key=api_key,
                                project_id=project_id,
                                model=model,
                                llm_fn=llm_fn,
                            ),
                            chunk,
                        )
                    )
            else:
                results = [
                    _extract_single_row(
                        r,
                        provider=provider,
                        api_key=api_key,
                        project_id=project_id,
                        model=model,
                        llm_fn=llm_fn,
                    )
                    for r in chunk
                ]

            valid_exts: List[BlockExtractionV21] = []
            valid_pairs: List[Tuple[sqlite3.Row, BlockExtractionV21]] = []
            for row, ext, tok_in, tok_out, err in results:
                in_tokens_used += tok_in
                out_tokens_used += tok_out
                if ext is None:
                    blocks_rejected += 1
                    rejected.append({"block_pk": int(row["block_pk"]), "error": err or "errore"})
                else:
                    valid_exts.append(ext)
                    valid_pairs.append((row, ext))

            if valid_exts:
                validate_batch_anti_template(valid_exts)

            for row, ext in valid_pairs:
                bpk = int(row["block_pk"])
                buid = str(row["block_uid"])
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

        return {
            "mode": "executed",
            "wave": wave,
            "provider": provider_label,
            "books_in_wave": books_in_wave,
            "blocks_processed": blocks_completed,
            "blocks_rejected": blocks_rejected,
            "paratext_logged": paratext_logged,
            "rejected_details": rejected,
            "units_written": units_written,
            "signatures_written": sigs_written,
            "bridges_validated": bridges_validated_total,
            "input_tokens_used": in_tokens_used,
            "output_tokens_used": out_tokens_used,
            "estimated_eur_from_credits": _estimate_eur(in_tokens_used, out_tokens_used),
        }
    finally:
        conn.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="CLI Batch Idempotente BlockExtraction v2.1 per Wave 1..4 di resuscipack."
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

    try:
        res = run_batch_extraction(
            args.db,
            wave=args.wave,
            limit=args.limit if args.limit > 0 else None,
            provider=args.provider,
            dry_run=args.dry_run,
            workers=args.workers,
            batch_size=args.batch_size,
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
