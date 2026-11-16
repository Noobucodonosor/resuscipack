#!/usr/bin/env python3
"""CLI Batch Idempotente per l'estrazione `BlockExtraction v2.1` a ondate (Wave 1..4).

Principi non negoziabili (ADR-0002, TASK-EPIST-03):
- Legge `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` esclusivamente da `os.environ` (zero chiavi hardcoded).
- Zero Mock Guarantee: se la chiave API manca e non si è in `--dry-run` o `--seed-empirical`,
  termina esplicitamente con errore senza scrivere alcuna riga finta/deterministica nel DB.
- Idempotenza: salta tutti i `block_pk` già presenti in `epistemic_units`, riprendendo
  esattamente dal punto d'interruzione e verificando ogni blocco con `validate_block_extraction`
  e ogni lotto con `validate_batch_anti_template`.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .bridge import seed_verified_empirical_bridges
from .op_tags import ALL_OP_TAGS, DEFAULT_FORBIDDEN_SURFACE_NOUNS
from .schema_v21 import (
    BlockExtractionV21,
    SchemaValidationError,
    persist_block_extraction,
    validate_batch_anti_template,
    validate_block_extraction,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pack_corpus.db"

WAVE_DOMAINS: Mapping[int, tuple[str, ...]] = {
    # Wave 1: Nucleo Aureo (Storia della scienza, Classici UTET + Fondamenti Matematica/Fisica)
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


class MissingCredentialsError(RuntimeError):
    """Sollevato quando si richiede estrazione cloud reale senza chiave API in `os.environ`."""


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
        "Rispondi SOLO con un singolo oggetto JSON valido, senza markdown.\n"
        "REGOLE FERREE:\n"
        "1. DIRITTO AL SILENZIO: se il brano è indice, bibliografia, copyright o privo di asserzioni "
        'concettuali, restituisci {"yield":"low_or_paratext","units":[],"sig":null}.\n'
        "2. ZERO DEISSI: ogni `units[i].stmt` deve essere una proposizione autonoma con soggetto esplicito "
        "(vietati 'egli', 'il Nostro', 'ivi', 'ibidem', 'op. cit.').\n"
        "3. CITAZIONE VERBATIM: `units[i].quote` deve essere una sottostringa ESATTA di 4–25 parole "
        "copiata dal BRANO. Se `kind='dispute'`, valorizza obbligatoriamente `vs` (Con chi in disaccordo).\n"
        "4. FIRMA STRUTTURALE `sig` OPZIONALE: se il brano è già un enunciato matematico/informatico "
        "astratto puro (es. manuale di analisi o algoritmi), DEVI impostare `\"sig\": null`.\n"
        "5. DOMAIN STRIPPING (quando `sig` non è null): in `sig.mech` è VIETATO usare sostantivi "
        f"aneddotici di superficie (es. {forbidden_csv}) o iniettare formule assenti dal testo; "
        "descrivi l'azione con termini geometrico-operativi e scegli 1..3 `op_tags` SOLO tra:\n"
        f"[{tags_csv}]\n\n"
        f"METADATI CONTESTO: titolo={book_title!r} | dominio={surface_domain!r} | "
        f"sezione={section_title!r} | pag={page_start}\n"
        "BRANO:\n"
        f"{content}\n"
    )


def select_pending_blocks(
    conn: sqlite3.Connection,
    *,
    wave: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[sqlite3.Row]:
    """Seleziona i blocchi sostantivi attivi non ancora estratti in `epistemic_units`."""
    conn.row_factory = sqlite3.Row
    params: List[Any] = []
    domain_clause = ""
    if wave is not None:
        if wave not in WAVE_DOMAINS:
            raise ValueError(f"Wave non valida: {wave} (ammesse: 1, 2, 3, 4)")
        doms = WAVE_DOMAINS[wave]
        placeholders = ",".join("?" for _ in doms)
        domain_clause = f"AND bk.surface_domain IN ({placeholders})"
        params.extend(doms)

    limit_clause = ""
    if limit is not None and limit > 0:
        limit_clause = "LIMIT ?"
        params.append(int(limit))

    sql = f"""
        SELECT
            bl.block_pk,
            bl.block_uid,
            bl.book_title,
            bl.section_title,
            bl.page_start,
            bl.content,
            bl.est_tokens,
            bk.surface_domain
        FROM blocks bl
        JOIN books bk ON bk.book_pk = bl.book_pk
        LEFT JOIN (
            SELECT DISTINCT block_pk FROM epistemic_units
        ) done ON done.block_pk = bl.block_pk
        WHERE bl.is_active = 1
          AND bk.is_active = 1
          AND bl.block_role != 'paratext'
          AND done.block_pk IS NULL
          {domain_clause}
        ORDER BY bl.block_pk ASC
        {limit_clause}
    """
    return conn.execute(sql, tuple(params)).fetchall()


def estimate_wave_budget(rows: Sequence[sqlite3.Row]) -> Dict[str, Any]:
    """Calcola token di input/output e costi stimati USD sui blocchi pendenti (onesto, zero sconti finti)."""
    n_blocks = len(rows)
    text_tokens = sum(int(r["est_tokens"] or max(1, len(r["content"]) // 4)) for r in rows)
    prompt_overhead = n_blocks * 240
    in_tokens = text_tokens + prompt_overhead
    out_tokens = n_blocks * 335  # media ponderata misurata su schema v2.1 (65% sig=null, 35% sig!=null)

    # Tariffe Batch asincrone (USD per 1M token):
    cost_flash_lite = (in_tokens / 1e6) * 0.05 + (out_tokens / 1e6) * 0.20
    cost_deepseek = (in_tokens / 1e6) * 0.14 + (out_tokens / 1e6) * 0.28
    cost_gemini_flash = (in_tokens / 1e6) * 0.15 + (out_tokens / 1e6) * 1.25

    return {
        "pending_blocks": n_blocks,
        "estimated_input_tokens": in_tokens,
        "estimated_output_tokens": out_tokens,
        "estimated_cost_usd": {
            "gemini_2_5_flash_lite_batch": round(cost_flash_lite, 3),
            "deepseek_v3_batch": round(cost_deepseek, 3),
            "gemini_2_5_flash_batch": round(cost_gemini_flash, 3),
        },
    }


def _resolve_api_key(provider: str) -> str:
    env_var = "GEMINI_API_KEY" if provider == "gemini" else "DEEPSEEK_API_KEY"
    val = os.environ.get(env_var, "").strip()
    if not val:
        raise MissingCredentialsError(
            f"Variabile d'ambiente {env_var} assente. Rifiuto di generare fallback/mock finti: "
            f"esporta {env_var} nell'ambiente oppure usa --dry-run / --seed-empirical."
        )
    return val


def _default_cloud_call(provider: str, api_key: str, prompt: str) -> Mapping[str, Any]:
    if provider == "gemini":
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
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
        return json.loads(txt)

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
        return json.loads(txt)

    raise ValueError(f"Provider sconosciuto: {provider!r}")


def run_batch_extraction(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    wave: Optional[int] = None,
    limit: Optional[int] = 50,
    provider: str = "gemini",
    dry_run: bool = False,
    llm_fn: Optional[Callable[[str, sqlite3.Row], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Esegue un ciclo idempotente di estrazione `BlockExtraction v2.1`."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        pending = select_pending_blocks(conn, wave=wave, limit=limit)
        budget = estimate_wave_budget(pending)
        if dry_run:
            return {"mode": "dry_run", "wave": wave, **budget}

        api_key = ""
        if llm_fn is None:
            api_key = _resolve_api_key(provider)

        validated_batch: List[ tuple[sqlite3.Row, BlockExtractionV21] ] = []
        rejected: List[Dict[str, Any]] = []

        for row in pending:
            prompt = build_block_extraction_prompt(
                book_title=str(row["book_title"] or ""),
                surface_domain=str(row["surface_domain"] or ""),
                section_title=str(row["section_title"] or ""),
                page_start=row["page_start"],
                content=str(row["content"]),
            )
            try:
                raw_payload = (
                    llm_fn(prompt, row)
                    if llm_fn is not None
                    else _default_cloud_call(provider, api_key, prompt)
                )
                ext = validate_block_extraction(
                    raw_payload,
                    block_content=str(row["content"]),
                )
                validated_batch.append((row, ext))
            except (SchemaValidationError, KeyError, ValueError, json.JSONDecodeError) as exc:
                rejected.append({"block_pk": int(row["block_pk"]), "error": str(exc)})

        # Gate anti-template sull'intero lotto prima del commit transazionale
        validate_batch_anti_template([ext for _, ext in validated_batch])

        units_written = 0
        sigs_written = 0
        for row, ext in validated_batch:
            units_written += persist_block_extraction(
                conn,
                block_pk=int(row["block_pk"]),
                block_uid=str(row["block_uid"]),
                extraction=ext,
            )
            if ext.sig is not None:
                sigs_written += 1

        conn.commit()
        return {
            "mode": "executed",
            "wave": wave,
            "blocks_processed": len(validated_batch),
            "blocks_rejected": len(rejected),
            "rejected_details": rejected,
            "units_written": units_written,
            "signatures_written": sigs_written,
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
    parser.add_argument("--provider", choices=["gemini", "deepseek"], default="gemini")
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
