"""Generatore del manifesto multi-ondata (`wave_1`..`wave_4`) per tutte le pagine ancora da
sottoporre a OCR/Vision (Buco B `Cultura_in_Ita5`, Buco C `ocr_priority_manifest` + sotto-estratti,
e i 7 volumi `.djvu` di Buco D), operando in STRICT READ-ONLY sulle fonti storiche."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sqlite3
import unicodedata
from typing import Any

from .normalizer import canonical_stem_key, is_excluded_noise_title
from .schema import DEFAULT_DB_PATH, connect_corpus_db

DEFAULT_PACK_NEXT_DB = Path.home() / "Documents/ChatGPT/pack-next/state/library.sqlite3"
DEFAULT_PC4_MANIFEST = Path.home() / "Desktop/pc4/ocr_priority_manifest.json"
DEFAULT_SOURCE_PDF_DIR = Path.home() / "Desktop/PACK copy 4/source_pdf"
DEFAULT_OCR_MANIFEST_OUT = Path(__file__).resolve().parents[2] / "data" / "ocr_wave_manifest.json"

WAVE1_CANONICAL_KEYWORDS = (
    "euclide",
    "galileo galilei",
    "archimede",
    "apostol",
    "principi matematici della filosofia naturale",
    "scritti di ottica",
    "carnap",
    "franciosi",
    "amerio",
    "ben-ari",
    "berzolari",
    "wittgenstein",
    "collins",
)

WAVE2_HUMANITIES_HISTORY_KEYWORDS = (
    "boyle",
    "volta",
    "ampere",
    "ampère",
    "laplace",
    "copernico",
    "maxwell",
    "galvanic",
    "scienze umanistiche",
    "leonardo da vinci",
    "beethoven",
)

WAVE3_STEM_SECAI_KEYWORDS = (
    "conte",
    "architettura dei calcolatori",
    "deitel",
    "dietel",
    "domenici",
    "spoletini",
    "mandrioli",
    "informatica teorica",
    "millman",
    "nigro",
    "gasparini",
    "schwinger",
    "franceschetti",
    "ravalico",
    "benato",
)


def _assign_wave(title: str, defect_kind: str, pages_needed: int) -> str:
    tl = unicodedata.normalize("NFC", title).lower()
    if any(k in tl for k in WAVE1_CANONICAL_KEYWORDS):
        return "wave_1"
    if any(k in tl for k in WAVE2_HUMANITIES_HISTORY_KEYWORDS):
        return "wave_2"
    if any(k in tl for k in WAVE3_STEM_SECAI_KEYWORDS) or defect_kind == "buco_d_djvu":
        return "wave_3"
    return "wave_4"


def _estimate_djvu_pages(djvu_path: Path) -> int:
    """Stima conservativa delle pagine per i 7 file `.djvu` basata sulla densità media (~25 KB/pag. B/N)."""
    size_kb = djvu_path.stat().st_size / 1024.0
    return max(120, min(650, int(round(size_kb / 24.0))))


def build_ocr_wave_manifest(
    corpus_db_path: Path = DEFAULT_DB_PATH,
    pack_next_db_path: Path = DEFAULT_PACK_NEXT_DB,
    pc4_manifest_path: Path = DEFAULT_PC4_MANIFEST,
    source_pdf_dir: Path = DEFAULT_SOURCE_PDF_DIR,
    manifest_out_path: Path | None = DEFAULT_OCR_MANIFEST_OUT,
) -> dict[str, Any]:
    """Costruisce e salva `data/ocr_wave_manifest.json` riconciliando i 4 buchi fisici."""
    conn_corpus = connect_corpus_db(corpus_db_path, read_only=True)
    corpus_books = conn_corpus.execute(
        """
        SELECT bk.book_pk, bk.title, bk.source_kind,
               COALESCE(SUM(bl.char_count), 0) AS total_chars,
               COUNT(bl.block_pk) AS block_cnt
        FROM books bk
        LEFT JOIN blocks bl ON bl.book_pk = bk.book_pk AND bl.is_active = 1
        WHERE bk.is_active = 1
        GROUP BY bk.book_pk
        """
    ).fetchall()

    corpus_by_ckey: dict[str, dict[str, Any]] = {}
    ellipsis_entries: list[tuple[str, str, dict[str, Any]]] = []
    for r in corpus_books:
        title_nfc = unicodedata.normalize("NFC", r["title"]).strip()
        ck = canonical_stem_key(title_nfc)
        words_approx = int(round(r["total_chars"] / 6.2))
        info = {
            "title": title_nfc,
            "source_kind": r["source_kind"],
            "words_approx": words_approx,
            "blocks": r["block_cnt"],
        }
        corpus_by_ckey[ck] = info
        if "…" in title_nfc:
            left, right = title_nfc.split("…", 1)
            ellipsis_entries.append((canonical_stem_key(left), canonical_stem_key(right), info))
    conn_corpus.close()

    def _lookup_in_corpus(stem: str) -> dict[str, Any] | None:
        ck = canonical_stem_key(stem)
        if ck in corpus_by_ckey:
            return corpus_by_ckey[ck]
        dot0 = canonical_stem_key(stem.split(".")[0])
        if len(dot0) >= 12 and dot0 in corpus_by_ckey:
            return corpus_by_ckey[dot0]
        for pref, suff, inf in ellipsis_entries:
            if pref and suff and ck.startswith(pref) and ck.endswith(suff):
                return inf
        return None

    pc4_docs: dict[str, list[int]] = {}
    if pc4_manifest_path.exists():
        raw_m = json.loads(pc4_manifest_path.read_text(encoding="utf-8"))
        for k, pages in (raw_m.get("documents") or {}).items():
            pc4_docs[canonical_stem_key(k)] = list(pages)

    items: list[dict[str, Any]] = []
    seen_ckeys: set[str] = set()

    if pack_next_db_path.exists():
        conn_pn = sqlite3.connect(f"file:{pack_next_db_path}?mode=ro", uri=True)
        pn_rows = conn_pn.execute(
            """
            SELECT d.path, d.status, COALESCE(e.total_pages, 0) AS total_pages,
                   COALESCE(e.text_pages, 0) AS text_pages, e.method
            FROM documents d
            LEFT JOIN extractions e ON d.id = e.document_id
            """
        ).fetchall()
        conn_pn.close()

        for path_str, status, tot_pages, txt_pages, method in pn_rows:
            stem = unicodedata.normalize("NFC", Path(path_str).stem).strip()
            if is_excluded_noise_title(stem):
                continue
            ck = canonical_stem_key(stem)
            if ck in seen_ckeys:
                continue

            in_corpus = _lookup_in_corpus(stem)
            manifest_missing_pages = pc4_docs.get(ck, [])

            if in_corpus is None:
                if tot_pages < 6:
                    continue
                seen_ckeys.add(ck)
                if status == "ocr_required" or manifest_missing_pages:
                    defect = "buco_c_ocr_priority_manifest"
                    p_need = len(manifest_missing_pages) if manifest_missing_pages else int(tot_pages)
                else:
                    defect = "buco_b_cultura_in_ita5_or_silent_blank"
                    p_need = int(tot_pages)
                items.append(
                    {
                        "title": stem,
                        "source_path": path_str,
                        "format": "pdf",
                        "defect_category": defect,
                        "total_pages": int(tot_pages),
                        "pages_needed": p_need,
                        "specific_pages": manifest_missing_pages if len(manifest_missing_pages) <= 50 else [],
                        "wave": _assign_wave(stem, defect, p_need),
                    }
                )
            else:
                words_est = in_corpus["words_approx"]
                already_full_via_alt_name = (
                    tot_pages > 0
                    and len(manifest_missing_pages) >= tot_pages * 0.85
                    and words_est >= tot_pages * 150
                )
                if manifest_missing_pages and not already_full_via_alt_name:
                    seen_ckeys.add(ck)
                    p_need = len(manifest_missing_pages)
                    defect = "buco_c_partial_ocr_tail"
                    items.append(
                        {
                            "title": stem,
                            "source_path": path_str,
                            "format": "pdf",
                            "defect_category": defect,
                            "total_pages": int(tot_pages),
                            "pages_needed": p_need,
                            "specific_pages": manifest_missing_pages if len(manifest_missing_pages) <= 50 else [],
                            "wave": _assign_wave(stem, defect, p_need),
                        }
                    )
                elif tot_pages >= 30 and (words_est / max(1, tot_pages)) < 35:
                    seen_ckeys.add(ck)
                    defect = "buco_c_under_extracted_pdf"
                    items.append(
                        {
                            "title": stem,
                            "source_path": path_str,
                            "format": "pdf",
                            "defect_category": defect,
                            "total_pages": int(tot_pages),
                            "pages_needed": int(tot_pages),
                            "specific_pages": [],
                            "wave": _assign_wave(stem, defect, int(tot_pages)),
                        }
                    )

    # Aggiunta dei 7 volumi `.djvu` in `PACK copy 4/source_pdf` (Buco D)
    if source_pdf_dir.is_dir():
        for djvu_file in sorted(source_pdf_dir.glob("*.djvu")):
            stem = unicodedata.normalize("NFC", djvu_file.stem).strip()
            ck = canonical_stem_key(stem)
            if ck in seen_ckeys or _lookup_in_corpus(stem) is not None:
                continue
            seen_ckeys.add(ck)
            est_p = _estimate_djvu_pages(djvu_file)
            defect = "buco_d_djvu"
            items.append(
                {
                    "title": stem,
                    "source_path": str(djvu_file),
                    "format": "djvu",
                    "defect_category": defect,
                    "total_pages": est_p,
                    "pages_needed": est_p,
                    "specific_pages": [],
                    "wave": _assign_wave(stem, defect, est_p),
                }
            )

    items.sort(key=lambda x: (x["wave"], -x["pages_needed"], x["title"]))

    waves_summary: dict[str, dict[str, Any]] = {}
    for w_name in ("wave_1", "wave_2", "wave_3", "wave_4"):
        w_items = [it for it in items if it["wave"] == w_name]
        w_pages = sum(it["pages_needed"] for it in w_items)
        waves_summary[w_name] = {
            "documents_count": len(w_items),
            "pages_needed": w_pages,
            "kaggle_single_t4_gpu_hours_est": round(w_pages / 260.0, 2),
            "cloud_4x4090_wall_hours_est": round(w_pages / (4 * 1350.0), 2),
            "gemini_25_flash_vision_batch_usd_est": round(
                (w_pages * 1548 / 1e6) * 0.15 + (w_pages * 550 / 1e6) * 1.25, 2
            ),
            "documents": w_items,
        }

    by_defect: dict[str, dict[str, int]] = {}
    for it in items:
        cat = it["defect_category"]
        slot = by_defect.setdefault(cat, {"documents": 0, "pages_needed": 0})
        slot["documents"] += 1
        slot["pages_needed"] += it["pages_needed"]

    total_pages_all = sum(it["pages_needed"] for it in items)
    manifest_payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_documents_needing_ocr": len(items),
        "total_pages_needing_ocr": total_pages_all,
        "estimates_total": {
            "kaggle_t4_gpu_hours": round(total_pages_all / 260.0, 2),
            "cloud_4x4090_spot_usd": round((total_pages_all / 1350.0) * 0.35, 2),
            "gemini_25_flash_vision_batch_usd": round(
                (total_pages_all * 1548 / 1e6) * 0.15 + (total_pages_all * 550 / 1e6) * 1.25, 2
            ),
        },
        "by_defect_category": by_defect,
        "waves": waves_summary,
    }

    if manifest_out_path is not None:
        manifest_out_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_out_path.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return manifest_payload


if __name__ == "__main__":
    res = build_ocr_wave_manifest()
    print(
        json.dumps(
            {k: v for k, v in res.items() if k != "waves"},
            indent=2,
            ensure_ascii=False,
        )
    )
    for wn, wdata in res["waves"].items():
        print(
            f"  {wn}: {wdata['documents_count']} docs, {wdata['pages_needed']} pages "
            f"(T4={wdata['kaggle_single_t4_gpu_hours_est']} GPU-h, Vision=${wdata['gemini_25_flash_vision_batch_usd_est']})"
        )
