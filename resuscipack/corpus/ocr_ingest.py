"""Pipeline append-only per OCR Vision (PDF e `.djvu`) e importazione pagine GCS (`TASK-CORPUS-04`).

Principi non negoziabili:
- STRICT READ-ONLY su `/Users/dany/Desktop/PACK copy 4/source_pdf/`: qualsiasi file temporaneo
  (`pdftoppm`, `ddjvu`, `sips`, `gcloud storage cp`) vive esclusivamente in `TemporaryDirectory()`.
- Append-only reale su `pack_corpus.db`: i vecchi `block_pk` non vengono mai eliminati; sui volumi
  sotto-estratti i blocchi degradati vengono disattivati con `supersede_block()`.
- Attribuzione risorse Google Cloud (`enforcing-resource-attribution`): ogni invocazione `gcloud`
  propaga `CLOUDSDK_METRICS_ENVIRONMENT=datacloud.antigravity`.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .normalizer import (
    canonical_stem_key,
    classify_block_role,
    classify_surface_domain,
    clean_ocr_markdown,
    detect_language,
    estimate_bpe_tokens,
    make_block_uid,
    make_book_uid,
    normalize_for_match,
    parse_author_year,
)
from .schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db, supersede_block

DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "ocr_wave_manifest.json"
DEFAULT_GCP_PROJECT = "macro-authority-492722-u7"
DEFAULT_VISION_MODEL = "gemini-2.5-flash"
DEFAULT_GCS_OCR_PREFIX = "gs://macro-authority-492722-u7-unlimited-ocr/output"

_VISION_TOKEN_LOCK = threading.Lock()
_VISION_TOKEN_VALUE = ""
_VISION_TOKEN_TS = 0.0


def _gcloud_env() -> Dict[str, str]:
    env = os.environ.copy()
    existing = env.get("CLOUDSDK_METRICS_ENVIRONMENT", "").strip()
    if "datacloud.antigravity" not in existing.split():
        env["CLOUDSDK_METRICS_ENVIRONMENT"] = f"{existing} datacloud.antigravity".strip()
    return env


def _get_gcloud_token(*, force_refresh: bool = False) -> str:
    global _VISION_TOKEN_VALUE, _VISION_TOKEN_TS
    with _VISION_TOKEN_LOCK:
        now = time.monotonic()
        if not force_refresh and _VISION_TOKEN_VALUE and (now - _VISION_TOKEN_TS) < 1500:
            return _VISION_TOKEN_VALUE
        proc = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            env=_gcloud_env(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        tok = (proc.stdout or "").strip()
        if proc.returncode != 0 or not tok:
            raise RuntimeError(
                f"Impossibile ottenere access token gcloud per Vertex Vision (code={proc.returncode}): {proc.stderr[:220]}"
            )
        _VISION_TOKEN_VALUE = tok
        _VISION_TOKEN_TS = now
        return tok


def _resolve_tool(name: str, fallback: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    if Path(fallback).exists():
        return fallback
    raise FileNotFoundError(f"Strumento CLI richiesto non trovato: {name} (atteso anche in {fallback})")


def count_document_pages(doc_path: Path) -> int:
    """Restituisce il numero reale di pagine di un PDF (`pdfinfo`) o `.djvu` (`djvused`)."""
    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        pdfinfo = _resolve_tool("pdfinfo", "/opt/homebrew/bin/pdfinfo")
        proc = subprocess.run([pdfinfo, str(doc_path)], capture_output=True, text=True, check=True)
        m = re.search(r"^Pages:\s*(\d+)", proc.stdout, flags=re.MULTILINE)
        if not m:
            raise RuntimeError(f"Impossibile leggere il numero di pagine da pdfinfo su {doc_path}")
        return int(m.group(1))
    if suffix == ".djvu":
        djvused = _resolve_tool("djvused", "/opt/homebrew/bin/djvused")
        proc = subprocess.run([djvused, "-e", "n", str(doc_path)], capture_output=True, text=True, check=True)
        return int(proc.stdout.strip())
    raise ValueError(f"Formato documento non supportato per OCR: {doc_path.suffix}")


def parse_page_spec(spec: str, total_pages: int) -> List[int]:
    """Converte una specifica stile `'1-5,10,65-72'` in lista ordinata unica di numeri pagina 1-based."""
    pages: set[int] = set()
    for part in str(spec or "").split(","):
        p = part.strip()
        if not p:
            continue
        if "-" in p:
            a_s, b_s = p.split("-", 1)
            a, b = max(1, int(a_s)), min(total_pages, int(b_s))
            if a <= b:
                pages.update(range(a, b + 1))
        else:
            val = int(p)
            if 1 <= val <= total_pages:
                pages.add(val)
    return sorted(pages)


def render_pages_to_jpeg_bytes(
    doc_path: Path,
    page_numbers: Sequence[int],
    *,
    dpi: int = 150,
) -> List[Tuple[int, bytes]]:
    """Renderizza in modo read-only le pagine richieste (.pdf o .djvu) in JPEG in memoria usando TemporaryDirectory."""
    if not doc_path.exists():
        raise FileNotFoundError(f"Documento sorgente non trovato: {doc_path}")
    suffix = doc_path.suffix.lower()
    results: List[Tuple[int, bytes]] = []

    with tempfile.TemporaryDirectory(prefix="resuscipack_ocr_") as tmp_str:
        tmpdir = Path(tmp_str)
        if suffix == ".pdf":
            pdftoppm = _resolve_tool("pdftoppm", "/opt/homebrew/bin/pdftoppm")
            for pnum in page_numbers:
                prefix = tmpdir / f"p_{pnum:04d}"
                subprocess.run(
                    [pdftoppm, "-jpeg", "-r", str(dpi), "-f", str(pnum), "-l", str(pnum), str(doc_path), str(prefix)],
                    capture_output=True,
                    check=True,
                )
                generated = sorted(tmpdir.glob(f"p_{pnum:04d}*.jpg"))
                if not generated:
                    raise RuntimeError(f"pdftoppm non ha prodotto JPEG per pagina {pnum} di {doc_path.name}")
                results.append((int(pnum), generated[0].read_bytes()))
        elif suffix == ".djvu":
            ddjvu = _resolve_tool("ddjvu", "/opt/homebrew/bin/ddjvu")
            sips = _resolve_tool("sips", "/usr/bin/sips")
            for pnum in page_numbers:
                tiff_path = tmpdir / f"p_{pnum:04d}.tiff"
                jpg_path = tmpdir / f"p_{pnum:04d}.jpg"
                subprocess.run(
                    [ddjvu, "-format=tiff", f"-page={pnum}", str(doc_path), str(tiff_path)],
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    [sips, "-s", "format", "jpeg", "-s", "formatOptions", "80", str(tiff_path), "--out", str(jpg_path)],
                    capture_output=True,
                    check=True,
                )
                results.append((int(pnum), jpg_path.read_bytes()))
        else:
            raise ValueError(f"Formato non supportato per rendering immagini: {suffix}")

    return results


def _strip_json_fences(raw_text: str) -> str:
    txt = raw_text.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


def _repair_json_latex_escapes(raw_json: str) -> str:
    """Ripara eventuali backslash LaTeX non raddoppiati dentro stringhe JSON (es. `\\sigma` -> `\\\\sigma`)."""
    return re.sub(r'\\(?![\\/"bfnrtu])', r'\\\\', raw_json)


def transcribe_pages_via_vertex_vision(
    page_images: Sequence[Tuple[int, bytes]],
    *,
    book_title: str,
    project_id: str = DEFAULT_GCP_PROJECT,
    model: str = DEFAULT_VISION_MODEL,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Trascrive un lotto (consigliato 1..4 pagine) JPEG tramite Gemini 2.5 Flash Vision su Vertex AI (`thinkingBudget=0`)."""
    if not page_images:
        return [], 0, 0

    proj = project_id or os.environ.get("GCP_PROJECT_ID", DEFAULT_GCP_PROJECT)
    mdl = model or os.environ.get("VERTEX_GEMINI_MODEL", DEFAULT_VISION_MODEL)
    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{proj}"
        f"/locations/global/publishers/google/models/{mdl}:generateContent"
    )

    page_list_str = ", ".join(str(p) for p, _ in page_images)
    instruction = (
        f"Stai trascrivendo pagine scansionate del volume: {book_title!r}.\n"
        f"Le immagini allegate corrispondono nell'ordine esatto ai numeri pagina PDF: [{page_list_str}].\n"
        "Rispondi SOLO con JSON valido nel formato:\n"
        '{"pages":[{"pdf_page":65,"printed_page":"73","section_title":"Libro I - Definizioni",'
        '"block_role":"body|paratext|footnote","text":"..."}]}\n'
        "REGOLE TASSATIVE:\n"
        "1. Trascrivi fedelmente tutto il testo stampato nella lingua originale dell'edizione (italiano/latino/inglese), "
        "ricucendo le parole spezzate a fine riga.\n"
        "2. Rendi le formule e notazioni matematiche in LaTeX pulito ($...$ o $$...$$) quando presenti; dentro le stringhe JSON "
        "raddoppia sempre i backslash LaTeX (es. \\\\frac, \\\\sigma) affinché il JSON resti valido.\n"
        "3. Rimuovi eventuali filigrane ripetitive come 'Cultura_in_Ita5', 'Cultura_in_Ita' o URL 'scribd.com'.\n"
        "4. Imposta block_role='paratext' su indici, sommari, bibliografie, frontespizi o pagine bianche; "
        "'body' sul testo sostantivo (definizioni, teoremi, dimostrazioni, commenti).\n"
        "5. Se una pagina ha figure geometriche, aggiungi una riga breve `[Figura geometrica: descrivi lettere/etichette visibili]`.\n"
    )

    parts: List[Dict[str, Any]] = [{"text": instruction}]
    for pnum, img_bytes in page_images:
        parts.append({"text": f"[INIZIO IMMAGINE PAGINA PDF {pnum}]"})
        parts.append(
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64.b64encode(img_bytes).decode("ascii"),
                }
            }
        )

    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode("utf-8")

    backoffs = (2.0, 5.0)
    last_err: Optional[Exception] = None
    for attempt in range(len(backoffs) + 1):
        token = _get_gcloud_token(force_refresh=(attempt > 0))
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
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            txt = raw["candidates"][0]["content"]["parts"][0]["text"]
            cleaned_txt = _strip_json_fences(txt)
            usage = raw.get("usageMetadata") or {}
            in_tok = int(usage.get("promptTokenCount") or 0)
            out_tok = int(usage.get("candidatesTokenCount") or 0)
            try:
                parsed = json.loads(cleaned_txt)
            except json.JSONDecodeError:
                try:
                    parsed = json.loads(_repair_json_latex_escapes(cleaned_txt))
                except json.JSONDecodeError:
                    if len(page_images) > 1:
                        mid = len(page_images) // 2
                        p_left, li, lo = transcribe_pages_via_vertex_vision(
                            page_images[:mid],
                            book_title=book_title,
                            project_id=project_id,
                            model=model,
                        )
                        p_right, ri, ro = transcribe_pages_via_vertex_vision(
                            page_images[mid:],
                            book_title=book_title,
                            project_id=project_id,
                            model=model,
                        )
                        return p_left + p_right, in_tok + li + ri, out_tok + lo + ro
                    raise
            pages_out = parsed.get("pages") if isinstance(parsed, dict) else []
            norm_pages: List[Dict[str, Any]] = []
            for idx, p_obj in enumerate(pages_out or []):
                if isinstance(p_obj, Mapping):
                    d = dict(p_obj)
                    if len(pages_out) == len(page_images):
                        d["pdf_page"] = int(page_images[idx][0])
                    norm_pages.append(d)
            return norm_pages, in_tok, out_tok
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in {401, 429, 500, 503} and attempt < len(backoffs):
                time.sleep(backoffs[attempt])
                continue
            detail = exc.read().decode("utf-8", errors="ignore")[:260]
            raise RuntimeError(f"Vertex Vision HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            last_err = exc
            if attempt < len(backoffs):
                time.sleep(backoffs[attempt])
                continue
            raise RuntimeError(f"Errore Vertex Vision OCR: {exc}") from exc

    raise RuntimeError(f"Vertex Vision OCR fallito: {last_err}")


def _find_or_create_book(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_path: str,
    surface_domain: str,
    source_kind: str,
    total_pages: int,
    sample_text: str,
) -> Tuple[int, str]:
    ckey = canonical_stem_key(title)
    existing_rows = conn.execute(
        "SELECT book_pk, book_uid, title FROM books WHERE is_active = 1"
    ).fetchall()
    for row in existing_rows:
        if canonical_stem_key(str(row["title"])) == ckey:
            return int(row["book_pk"]), str(row["book_uid"])

    book_uid = make_book_uid(ckey or title, source_kind)
    row_by_uid = conn.execute(
        "SELECT book_pk, book_uid FROM books WHERE book_uid = ?",
        (book_uid,),
    ).fetchone()
    if row_by_uid is not None:
        return int(row_by_uid["book_pk"]), str(row_by_uid["book_uid"])

    author, year = parse_author_year(title)
    lang = detect_language(sample_text)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO books (
            book_uid, title, author, year, surface_domain, language,
            source_kind, source_path, page_count, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            book_uid,
            title,
            author,
            year,
            surface_domain,
            lang,
            source_kind,
            source_path,
            int(total_pages),
            now_iso,
        ),
    )
    return int(cur.lastrowid), book_uid


def ingest_ocr_pages_append_only(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_path: str,
    surface_domain: Optional[str] = None,
    source_kind: str = "vertex_vision_ocr",
    total_pages: int = 0,
    transcribed_pages: Sequence[Mapping[str, Any]],
    supersede_under_extracted: bool = False,
) -> Dict[str, Any]:
    """Inserisce in modalità append-only pagine trascritte in `blocks` (+ `books`), senza alterare
    alcuno dei `block_pk` preesistenti e disattivando eventuali vecchi blocchi degradati se richiesto."""
    cleaned_pages: List[Dict[str, Any]] = []
    for p in transcribed_pages:
        pdf_page = int(p.get("pdf_page") or p.get("page") or 0)
        raw_txt = str(p.get("text") or p.get("content") or "")
        cleaned = clean_ocr_markdown(raw_txt)
        if not cleaned or len(cleaned) < 20:
            continue
        sec_title = " ".join(str(p.get("section_title") or "").split()).strip()
        raw_role = str(p.get("block_role") or "").strip().lower()
        role = raw_role if raw_role in {"body", "footnote", "paratext"} else classify_block_role(cleaned, sec_title)
        printed_page = str(p.get("printed_page") or (str(pdf_page) if pdf_page > 0 else "")).strip()
        cleaned_pages.append(
            {
                "pdf_page": pdf_page,
                "printed_page": printed_page,
                "section_title": sec_title,
                "block_role": role,
                "content": cleaned,
            }
        )

    if not cleaned_pages:
        return {"book_pk": None, "blocks_inserted": 0, "blocks_skipped": 0, "blocks_superseded": 0}

    sample_txt = "\n\n".join(p["content"] for p in cleaned_pages[:4])
    eff_domain = surface_domain or classify_surface_domain(title, sample_txt)
    book_pk, book_uid = _find_or_create_book(
        conn,
        title=title,
        source_path=source_path,
        surface_domain=eff_domain,
        source_kind=source_kind,
        total_pages=total_pages or max(p["pdf_page"] for p in cleaned_pages),
        sample_text=sample_txt,
    )

    old_active_pks: List[int] = []
    if supersede_under_extracted:
        old_active_pks = [
            int(r[0])
            for r in conn.execute(
                "SELECT block_pk FROM blocks WHERE book_pk = ? AND is_active = 1",
                (book_pk,),
            ).fetchall()
        ]

    inserted_pks: List[int] = []
    skipped = 0
    for item in cleaned_pages:
        content = item["content"]
        norm_c = normalize_for_match(content)
        if not norm_c:
            skipped += 1
            continue
        pnum = item["pdf_page"]
        blk_uid = make_block_uid(book_uid, pnum, pnum, norm_c)
        exists = conn.execute(
            "SELECT block_pk FROM blocks WHERE block_uid = ?",
            (blk_uid,),
        ).fetchone()
        if exists is not None:
            skipped += 1
            continue

        cur = conn.execute(
            """
            INSERT INTO blocks (
                block_uid, book_pk, book_title, is_active, block_role,
                page_start, page_end, printed_page, section_title,
                content, norm_content, char_count, est_tokens, source_origin
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                blk_uid,
                book_pk,
                title,
                item["block_role"],
                pnum,
                pnum,
                item["printed_page"],
                item["section_title"],
                content,
                norm_c,
                len(content),
                estimate_bpe_tokens(content),
                source_kind,
            ),
        )
        inserted_pks.append(int(cur.lastrowid))

    superseded_count = 0
    if supersede_under_extracted and old_active_pks and inserted_pks:
        anchor_pk = inserted_pks[0]
        for old_pk in old_active_pks:
            if old_pk != anchor_pk:
                supersede_block(conn, old_pk, anchor_pk)
                superseded_count += 1

    conn.commit()
    return {
        "book_pk": book_pk,
        "book_uid": book_uid,
        "surface_domain": eff_domain,
        "inserted_block_pks": inserted_pks,
        "blocks_inserted": len(inserted_pks),
        "blocks_skipped": skipped,
        "blocks_superseded": superseded_count,
    }


def list_gcs_ocr_matches(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    gcs_prefix: str = DEFAULT_GCS_OCR_PREFIX,
) -> List[Dict[str, Any]]:
    """Trova quali volumi del manifesto risultano già elaborati dal runner Baidu su GCS."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["gcloud", "storage", "ls", f"{gcs_prefix.rstrip('/')}/"],
        env=_gcloud_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    gcs_by_ck: Dict[str, str] = {}
    for line in proc.stdout.splitlines():
        clean = line.strip().rstrip("/")
        if clean:
            name = clean.rsplit("/", 1)[-1]
            gcs_by_ck[canonical_stem_key(name)] = clean

    matches: List[Dict[str, Any]] = []
    for wname, wdata in manifest.get("waves", {}).items():
        for doc in wdata.get("documents", []):
            ck = canonical_stem_key(doc["title"])
            if ck in gcs_by_ck:
                matches.append(
                    {
                        "wave": wname,
                        "title": doc["title"],
                        "pages_needed": doc["pages_needed"],
                        "defect_category": doc["defect_category"],
                        "gcs_dir": gcs_by_ck[ck],
                    }
                )
    return matches


def import_gcs_baidu_book(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_path: str,
    gcs_dir: str,
    total_pages: int = 0,
    supersede_under_extracted: bool = False,
) -> Dict[str, Any]:
    """Scarica temporaneamente i file `pages/page_*.md` già presenti nel bucket GCS (0 € di API Vision)
    e li ingerisce in modalità append-only dentro `pack_corpus.db`."""
    with tempfile.TemporaryDirectory(prefix="resuscipack_gcs_ocr_") as tmp_str:
        tmpdir = Path(tmp_str)
        pages_src = f"{gcs_dir.rstrip('/')}/pages/*.md"
        proc = subprocess.run(
            ["gcloud", "storage", "cp", pages_src, str(tmpdir)],
            env=_gcloud_env(),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Impossibile copiare pagine GCS da {pages_src}: {proc.stderr[:240]}")

        parsed_pages: List[Dict[str, Any]] = []
        for md_file in sorted(tmpdir.glob("page_*.md")):
            m = re.search(r"page_(\d+)\.md$", md_file.name)
            pnum = int(m.group(1)) if m else 0
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            parsed_pages.append({"pdf_page": pnum, "text": text})

    return ingest_ocr_pages_append_only(
        conn,
        title=title,
        source_path=source_path,
        source_kind="gcs_baidu_ocr",
        total_pages=total_pages,
        transcribed_pages=parsed_pages,
        supersede_under_extracted=supersede_under_extracted,
    )


def run_vision_ocr_on_document(
    conn: sqlite3.Connection,
    *,
    doc_path: Path,
    page_numbers: Sequence[int],
    title: Optional[str] = None,
    pages_per_call: int = 4,
    dpi: int = 150,
    supersede_under_extracted: bool = False,
    vision_fn: Optional[
        Callable[[Sequence[Tuple[int, bytes]], str], Tuple[List[Dict[str, Any]], int, int]]
    ] = None,
) -> Dict[str, Any]:
    """Esegue OCR end-to-end (render immagine temporanea -> Vision -> append-only in `blocks`)."""
    doc_path = Path(doc_path)
    eff_title = title or doc_path.stem
    tot_pages = count_document_pages(doc_path)
    rendered = render_pages_to_jpeg_bytes(doc_path, page_numbers, dpi=dpi)

    all_transcribed: List[Dict[str, Any]] = []
    tot_in_tok = 0
    tot_out_tok = 0
    step = max(1, min(int(pages_per_call), 6))

    for idx in range(0, len(rendered), step):
        batch = rendered[idx : idx + step]
        if vision_fn is not None:
            pages_out, in_tok, out_tok = vision_fn(batch, eff_title)
        else:
            pages_out, in_tok, out_tok = transcribe_pages_via_vertex_vision(
                batch,
                book_title=eff_title,
            )
        tot_in_tok += in_tok
        tot_out_tok += out_tok
        all_transcribed.extend(pages_out)

    ingest_res = ingest_ocr_pages_append_only(
        conn,
        title=eff_title,
        source_path=str(doc_path),
        source_kind="vertex_vision_ocr",
        total_pages=tot_pages,
        transcribed_pages=all_transcribed,
        supersede_under_extracted=supersede_under_extracted,
    )
    usd = (tot_in_tok / 1e6) * 0.30 + (tot_out_tok / 1e6) * 2.50
    return {
        **ingest_res,
        "pages_requested": list(page_numbers),
        "pages_transcribed": len(all_transcribed),
        "input_tokens": tot_in_tok,
        "output_tokens": tot_out_tok,
        "estimated_eur": round(usd * 0.92, 5),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OCR append-only PDF/DjVu per i volumi muti di resuscipack.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--doc", type=Path, default=None, help="Percorso PDF o DjVu in sola lettura")
    parser.add_argument("--pages", type=str, default="1-4", help="Intervallo pagine 1-based, es. 65-72")
    parser.add_argument("--title", type=str, default=None)
    parser.add_argument("--list-gcs-matches", action="store_true", help="Elenca i volumi già pronti su GCS output/")
    args = parser.parse_args(argv)

    if args.list_gcs_matches:
        res = list_gcs_ocr_matches()
        print(json.dumps({"count": len(res), "matches": res}, indent=2, ensure_ascii=False))
        return 0

    if args.doc is None:
        parser.error("Specifica --doc <file.pdf|file.djvu> oppure --list-gcs-matches")

    tot = count_document_pages(args.doc)
    pnums = parse_page_spec(args.pages, tot)
    conn = init_corpus_db(args.db)
    try:
        res = run_vision_ocr_on_document(
            conn,
            doc_path=args.doc,
            page_numbers=pnums,
            title=args.title,
        )
    finally:
        conn.close()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
