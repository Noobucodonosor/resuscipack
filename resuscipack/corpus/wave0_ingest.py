"""Wave 0 Ingestion Pipeline (€0, 100% locale, STRICT READ-ONLY sulle cartelle storiche):
1. Splicing reale a livello di pagina delle 4.162+ pagine Baidu Unlimited-OCR sui volumi ibridi di `from_before` (chiusura Buco A).
2. Ingestione XHTML nativa dei 32 volumi `.epub` in `PACK copy 4/source_pdf/` (chiusura metà Buco D).
3. Esclusione dei manuali ASUS multilingua / rumore amministrativo (~52 record) e deduplica cloni `.split('.')[0]`.
4. Segmentazione strutturale onesta con classificazione `block_role` (`'body'`, `'footnote'`, `'paratext'`).
5. Popolamento di `legacy_rowid_map` e `data/legacy_card_migration.json` per tutte le schede esistenti in `from_baidu/grafo/elementari/`."""

from __future__ import annotations

import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

import yaml

from .normalizer import (
    canonical_stem_key,
    classify_block_role,
    classify_surface_domain,
    clean_ocr_markdown,
    detect_language,
    estimate_bpe_tokens,
    is_excluded_noise_title,
    make_block_uid,
    make_book_uid,
    normalize_for_match,
    parse_author_year,
)
from .schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db

DEFAULT_FROM_BAIDU_ROOT = Path.home() / "from_baidu"
DEFAULT_SOURCE_PDF_DIR = Path.home() / "Desktop/PACK copy 4/source_pdf"
DEFAULT_LEGACY_FTS_DB = DEFAULT_FROM_BAIDU_ROOT / "atomic_iceberg" / "data" / "biblioteca_fts5.db"
DEFAULT_LEGACY_CARDS_DIR = DEFAULT_FROM_BAIDU_ROOT / "grafo" / "elementari"
DEFAULT_MIGRATION_JSON = Path(__file__).resolve().parents[2] / "data" / "legacy_card_migration.json"

PAGE_HEADER_RE = re.compile(r"<!--\s*Pagina\s+(\d+)[^>]*-->", re.IGNORECASE)
PRINTED_PAGE_RE = re.compile(r"^\s*(?:pag\.?|p\.)\s*(\d+[ivxlcdm]*)\b", re.IGNORECASE)

SYSTEM_SKIP_DIRS = {
    ".agents",
    ".git",
    ".venv",
    "__pycache__",
    "atomic_iceberg",
    "from_before",
    "grafo",
    "images",
    "static",
    "templates",
    "teoria_quiz",
    "tools",
}


class _EpubTextExtractor(HTMLParser):
    """Parser HTML/XHTML leggero e deterministico per estrarre headings e paragrafi dagli EPUB."""

    BLOCK_TAGS = {"p", "li", "blockquote", "pre", "tr", "div", "section", "article"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4"}
    SKIP_TAGS = {"script", "style", "head", "nav", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_heading = False
        self._cur_buf: list[str] = []
        self.items: list[tuple[str, str]] = []  # ("heading" | "para", text)

    def _flush(self, kind: str) -> None:
        if not self._cur_buf:
            return
        raw = "".join(self._cur_buf)
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", html.unescape(raw)).strip()
        self._cur_buf.clear()
        if cleaned:
            self.items.append((kind, cleaned))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower().split(":")[-1]
        if t in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t in self.HEADING_TAGS:
            self._flush("para")
            self._in_heading = True
        elif t == "br":
            self._cur_buf.append("\n")
        elif t in self.BLOCK_TAGS:
            self._flush("heading" if self._in_heading else "para")
            self._in_heading = False

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower().split(":")[-1]
        if t in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if t in self.HEADING_TAGS:
            self._flush("heading")
            self._in_heading = False
        elif t in self.BLOCK_TAGS:
            self._flush("para")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._cur_buf.append(data)

    def close(self) -> None:
        self._flush("heading" if self._in_heading else "para")
        super().close()


def extract_epub_blocks(epub_path: Path) -> list[dict[str, Any]]:
    """Estrae in sola lettura i capitoli XHTML da un file `.epub` rispettando lo `<spine>` OPF
    e li segmenta lungo i confini di paragrafo (~400-750 parole, zero troncamento)."""
    blocks: list[dict[str, Any]] = []
    with zipfile.ZipFile(epub_path, "r") as zf:
        namelist = set(zf.namelist())
        ordered_docs: list[str] = []

        if "META-INF/container.xml" in namelist:
            try:
                c_root = ET.fromstring(zf.read("META-INF/container.xml"))
                rf = c_root.find(".//{*}rootfile")
                if rf is not None and rf.attrib.get("full-path"):
                    opf_path = rf.attrib["full-path"]
                    if opf_path in namelist:
                        opf_dir = str(Path(opf_path).parent)
                        opf_root = ET.fromstring(zf.read(opf_path))
                        manifest_map: dict[str, str] = {}
                        for item in opf_root.findall(".//{*}manifest/{*}item"):
                            iid = item.attrib.get("id")
                            href = item.attrib.get("href")
                            mtype = item.attrib.get("media-type", "")
                            if iid and href and ("html" in mtype or href.lower().endswith((".xhtml", ".html", ".htm"))):
                                clean_href = href.split("#")[0]
                                full_href = f"{opf_dir}/{clean_href}" if opf_dir and opf_dir != "." else clean_href
                                full_href = os.path.normpath(full_href).replace("\\", "/")
                                if full_href in namelist:
                                    manifest_map[iid] = full_href
                                elif clean_href in namelist:
                                    manifest_map[iid] = clean_href
                        for itemref in opf_root.findall(".//{*}spine/{*}itemref"):
                            idref = itemref.attrib.get("idref", "")
                            if idref in manifest_map and manifest_map[idref] not in ordered_docs:
                                ordered_docs.append(manifest_map[idref])
            except ET.ParseError:
                ordered_docs = []

        if not ordered_docs:
            ordered_docs = sorted(
                n for n in namelist if n.lower().endswith((".xhtml", ".html", ".htm"))
            )

        seq_idx = 0
        for doc_idx, member in enumerate(ordered_docs, 1):
            try:
                raw_xhtml = zf.read(member).decode("utf-8", errors="ignore")
            except KeyError:
                continue
            parser = _EpubTextExtractor()
            parser.feed(raw_xhtml)
            parser.close()

            current_heading = ""
            buf_paras: list[str] = []
            buf_words = 0

            def _emit_buf(ch_num: int, heading: str) -> None:
                nonlocal seq_idx
                if not buf_paras:
                    return
                joined = clean_ocr_markdown("\n\n".join(buf_paras))
                buf_paras.clear()
                if len(joined) < 60:
                    return
                seq_idx += 1
                blocks.append(
                    {
                        "page_start": ch_num,
                        "page_end": ch_num,
                        "printed_page": f"ch.{ch_num}",
                        "section_title": heading[:140],
                        "content": joined,
                        "source_origin": "epub_xhtml",
                    }
                )

            for kind, txt in parser.items:
                if kind == "heading":
                    if buf_words >= 180:
                        _emit_buf(doc_idx, current_heading)
                        buf_words = 0
                    current_heading = txt
                    buf_paras.append(f"## {txt}")
                    buf_words += len(txt.split())
                else:
                    buf_paras.append(txt)
                    buf_words += len(txt.split())
                    if buf_words >= 500:
                        _emit_buf(doc_idx, current_heading)
                        buf_words = 0

            if buf_paras:
                _emit_buf(doc_idx, current_heading)

    return blocks


def _extract_heading(text: str, fallback: str = "") -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            h = s.lstrip("#").strip()
            if h:
                return h[:140]
    return fallback


def _load_baidu_pages_map(book_dir: Path) -> dict[int, str]:
    """Carica tutte le pagine `pages/page_NNNN.md` pulite di una cartella Baidu OCR."""
    pages_dir = book_dir / "pages"
    page_map: dict[int, str] = {}
    if not pages_dir.is_dir():
        return page_map
    for pf in sorted(pages_dir.glob("page_*.md")):
        m = re.search(r"page_(\d+)", pf.name)
        if not m:
            continue
        pnum = int(m.group(1))
        raw = pf.read_text(encoding="utf-8", errors="ignore")
        cleaned = clean_ocr_markdown(raw)
        if len(cleaned) >= 40:
            page_map[pnum] = cleaned
    return page_map


def _parse_markdown_pages_or_paragraphs(
    raw_text: str, default_origin: str
) -> tuple[bool, dict[int, tuple[str, str]], list[dict[str, Any]]]:
    """Analizza un file `.md` restituendo:
    - `has_page_markers`: True se strutturato con `<!-- Pagina N -->`;
    - `paged_map`: `{page_num: (heading, cleaned_content)}` se paginato;
    - `unpaged_blocks`: lista di blocchi segmentati lungo paragrafi se non paginato."""
    parts = PAGE_HEADER_RE.split(raw_text)
    if len(parts) > 2:
        paged_map: dict[int, tuple[str, str]] = {}
        current_heading = ""
        for idx in range(1, len(parts), 2):
            try:
                pnum = int(parts[idx])
            except ValueError:
                pnum = (idx // 2) + 1
            cleaned = clean_ocr_markdown(parts[idx + 1])
            if len(cleaned) < 50:
                continue
            current_heading = _extract_heading(cleaned, current_heading)
            paged_map[pnum] = (current_heading, cleaned)
        return True, paged_map, []

    cleaned_full = clean_ocr_markdown(raw_text)
    paragraphs = re.split(r"\n\s*\n", cleaned_full)
    unpaged_blocks: list[dict[str, Any]] = []
    buf: list[str] = []
    buf_words = 0
    chunk_idx = 1
    current_heading = ""

    for para in paragraphs:
        p = para.strip()
        if not p:
            continue
        if p.startswith("#"):
            current_heading = p.lstrip("#").strip()[:140]
        buf.append(p)
        buf_words += len(p.split())
        if buf_words >= 450:
            joined = "\n\n".join(buf)
            if len(joined) >= 50:
                unpaged_blocks.append(
                    {
                        "page_start": chunk_idx,
                        "page_end": chunk_idx,
                        "printed_page": None,
                        "section_title": current_heading,
                        "content": joined,
                        "source_origin": default_origin,
                    }
                )
            chunk_idx += 1
            buf = []
            buf_words = 0

    if buf:
        joined = "\n\n".join(buf)
        if len(joined) >= 50:
            unpaged_blocks.append(
                {
                    "page_start": chunk_idx,
                    "page_end": chunk_idx,
                    "printed_page": None,
                    "section_title": current_heading,
                    "content": joined,
                    "source_origin": default_origin,
                }
            )

    return False, {}, unpaged_blocks


def build_merged_markdown_volume_blocks(
    before_md: Path | None, baidu_dir: Path | None
) -> tuple[list[dict[str, Any]], str, str, int]:
    """Unisce `from_before` e `from_baidu` facendo vero **page-level splicing** (chiusura Buco A):
    restituisce `(blocks, primary_source_kind, source_path_str, spliced_baidu_pages_count)`."""
    baidu_pages = _load_baidu_pages_map(baidu_dir) if baidu_dir is not None else {}

    # Fallback su singolo .md nella cartella Baidu SOLO se non esiste la sottocartella pages/
    baidu_single_mds: list[Path] = []
    if baidu_dir is not None and not (baidu_dir / "pages").is_dir() and not baidu_pages:
        baidu_single_mds = [
            f for f in sorted(baidu_dir.glob("*.md")) if not f.name.endswith("_debug.md")
        ]

    if before_md is not None and baidu_pages:
        raw_before = before_md.read_text(encoding="utf-8", errors="ignore")
        has_markers, before_paged, before_unpaged = _parse_markdown_pages_or_paragraphs(
            raw_before, default_origin="from_before"
        )
        words_before = (
            sum(len(v[1].split()) for v in before_paged.values())
            if has_markers
            else sum(len(b["content"].split()) for b in before_unpaged)
        )
        words_baidu = sum(len(txt.split()) for txt in baidu_pages.values())

        # Caso 1: `from_before` è paginato -> Page-Level Splicing esatto!
        if has_markers and baidu_pages:
            merged_pages: dict[int, tuple[str, str, str]] = {
                p: (sec, txt, "from_before") for p, (sec, txt) in before_paged.items()
            }
            spliced_cnt = 0
            last_sec = ""
            for pnum, btxt in sorted(baidu_pages.items()):
                sec = _extract_heading(btxt, merged_pages.get(pnum, ("", "", ""))[0] or last_sec)
                if sec:
                    last_sec = sec
                origin_tag = "from_baidu_spliced" if words_before >= 500 else "from_baidu_ocr"
                merged_pages[pnum] = (sec, btxt, origin_tag)
                if words_before >= 500:
                    spliced_cnt += 1

            out_blocks = [
                {
                    "page_start": pnum,
                    "page_end": pnum,
                    "printed_page": str(pnum),
                    "section_title": sec,
                    "content": txt,
                    "source_origin": orig,
                }
                for pnum, (sec, txt, orig) in sorted(merged_pages.items())
            ]
            kind = "baidu_ocr" if words_before < 500 else "hybrid_baidu_spliced"
            spath = str(baidu_dir) if words_before < 500 else str(before_md)
            return out_blocks, kind, spath, spliced_cnt

        # Caso 2: `from_before` non aveva commenti pagina, ma Baidu ha l'intero libro (es. Kelvin 963p, Elenkov 585p)
        if baidu_pages and (words_before < 500 or words_baidu >= words_before * 0.75):
            out_blocks = []
            cur_sec = ""
            for pnum, btxt in sorted(baidu_pages.items()):
                cur_sec = _extract_heading(btxt, cur_sec)
                out_blocks.append(
                    {
                        "page_start": pnum,
                        "page_end": pnum,
                        "printed_page": str(pnum),
                        "section_title": cur_sec,
                        "content": btxt,
                        "source_origin": "from_baidu_ocr",
                    }
                )
            return out_blocks, "baidu_ocr", str(baidu_dir), 0

        # Caso 3: `from_before` non paginato con poche pagine extra Baidu -> conserva `from_before` + accoda pagine Baidu inedite
        if baidu_pages:
            existing_norms = [normalize_for_match(b["content"]) for b in before_unpaged]
            spliced_cnt = 0
            cur_sec = before_unpaged[-1]["section_title"] if before_unpaged else ""
            for pnum, btxt in sorted(baidu_pages.items()):
                nb = normalize_for_match(btxt)
                probe = nb[:120]
                if len(probe) >= 35 and any(probe in ex for ex in existing_norms):
                    continue
                cur_sec = _extract_heading(btxt, cur_sec)
                before_unpaged.append(
                    {
                        "page_start": pnum,
                        "page_end": pnum,
                        "printed_page": str(pnum),
                        "section_title": cur_sec,
                        "content": btxt,
                        "source_origin": "from_baidu_spliced",
                    }
                )
                spliced_cnt += 1
            kind = "hybrid_baidu_spliced" if spliced_cnt > 0 else "from_before"
            return before_unpaged, kind, str(before_md), spliced_cnt

        return before_unpaged, "from_before", str(before_md), 0

    if before_md is not None:
        raw_before = before_md.read_text(encoding="utf-8", errors="ignore")
        has_markers, before_paged, before_unpaged = _parse_markdown_pages_or_paragraphs(
            raw_before, default_origin="from_before"
        )
        if has_markers:
            out_blocks = [
                {
                    "page_start": pnum,
                    "page_end": pnum,
                    "printed_page": str(pnum),
                    "section_title": sec,
                    "content": txt,
                    "source_origin": "from_before",
                }
                for pnum, (sec, txt) in sorted(before_paged.items())
            ]
            return out_blocks, "from_before", str(before_md), 0
        return before_unpaged, "from_before", str(before_md), 0

    # Solo `baidu_dir`
    assert baidu_dir is not None
    if baidu_pages:
        out_blocks = []
        cur_sec = ""
        for pnum, btxt in sorted(baidu_pages.items()):
            cur_sec = _extract_heading(btxt, cur_sec)
            out_blocks.append(
                {
                    "page_start": pnum,
                    "page_end": pnum,
                    "printed_page": str(pnum),
                    "section_title": cur_sec,
                    "content": btxt,
                    "source_origin": "from_baidu_ocr",
                }
            )
        return out_blocks, "baidu_ocr", str(baidu_dir), 0

    out_blocks = []
    for mf in baidu_single_mds:
        raw = mf.read_text(encoding="utf-8", errors="ignore")
        has_m, pmap, unp = _parse_markdown_pages_or_paragraphs(raw, default_origin="from_baidu_ocr")
        if has_m:
            for pnum, (sec, txt) in sorted(pmap.items()):
                out_blocks.append(
                    {
                        "page_start": pnum,
                        "page_end": pnum,
                        "printed_page": str(pnum),
                        "section_title": sec,
                        "content": txt,
                        "source_origin": "from_baidu_ocr",
                    }
                )
        else:
            out_blocks.extend(unp)
    return out_blocks, "baidu_ocr", str(baidu_dir), 0


def migrate_legacy_card_rowids(
    conn: sqlite3.Connection,
    legacy_fts_db_path: Path = DEFAULT_LEGACY_FTS_DB,
    legacy_cards_dir: Path = DEFAULT_LEGACY_CARDS_DIR,
    migration_json_out: Path | None = DEFAULT_MIGRATION_JSON,
) -> dict[str, Any]:
    """Risolve deterministicamente tutti i vecchi `rowid` usati nelle schede elementari
    cercando la citazione normalizzata esatta in `blocks.norm_content` e salva `legacy_rowid_map`."""
    if not legacy_fts_db_path.exists() or not legacy_cards_dir.exists():
        return {"cards": {}, "rowid_map": {}}

    leg_conn = sqlite3.connect(f"file:{legacy_fts_db_path}?mode=ro", uri=True)
    leg_cur = leg_conn.cursor()

    card_files = sorted(p for p in legacy_cards_dir.glob("*.md") if not p.name.startswith("_"))
    cards_report: dict[str, list[dict[str, Any]]] = {}
    resolved_by_rowid: dict[int, dict[str, Any]] = {}

    for cf in card_files:
        txt = cf.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", txt, flags=re.DOTALL)
        if not m:
            continue
        meta = yaml.safe_load(m.group(1)) or {}
        fonti = meta.get("fonti") or []
        card_entries: list[dict[str, Any]] = []

        for idx, f in enumerate(fonti, 1):
            old_rid = int(f["rowid"])
            cit = str(f["citazione"])
            norm_cit = normalize_for_match(cit)

            leg_row = leg_cur.execute(
                "SELECT c0, c1, c2, c4 FROM passages_fts_content WHERE id = ?",
                (old_rid,),
            ).fetchone()
            old_title = leg_row[0] if leg_row else ""
            old_page_str = str(leg_row[2]) if leg_row else "0"
            old_page = int(old_page_str) if old_page_str.isdigit() else 0

            # Cerchiamo prima sul libro con lo stesso titolo canonico, altrimenti su tutto il DB attivo
            cand_rows = conn.execute(
                """
                SELECT b.block_pk, b.block_uid, b.book_title, b.page_start, b.printed_page, b.norm_content,
                       bk.author, bk.year
                FROM blocks b
                JOIN books bk ON bk.book_pk = b.book_pk
                WHERE b.is_active = 1
                  AND b.book_title = ?
                  AND instr(b.norm_content, ?) > 0
                """,
                (unicodedata.normalize("NFC", old_title).strip(), norm_cit),
            ).fetchall()

            match_method = "exact_book_verbatim_quote"
            if not cand_rows:
                cand_rows = conn.execute(
                    """
                    SELECT b.block_pk, b.block_uid, b.book_title, b.page_start, b.printed_page, b.norm_content,
                           bk.author, bk.year
                    FROM blocks b
                    JOIN books bk ON bk.book_pk = b.book_pk
                    WHERE b.is_active = 1
                      AND instr(b.norm_content, ?) > 0
                    """,
                    (norm_cit,),
                ).fetchall()
                match_method = "global_verbatim_quote"

            if not cand_rows:
                raise RuntimeError(
                    f"Impossibile migrare citazione in {cf.name} (old_rowid={old_rid}): {cit!r}"
                )

            best = min(
                cand_rows,
                key=lambda r: abs((r["page_start"] or 0) - old_page),
            )

            entry = {
                "footnote_index": idx,
                "legacy_fts_rowid": old_rid,
                "block_pk": int(best["block_pk"]),
                "block_uid": str(best["block_uid"]),
                "book_title": str(best["book_title"]),
                "author": best["author"],
                "year": best["year"],
                "page_start": best["page_start"],
                "citazione": cit,
                "match_method": match_method,
            }
            card_entries.append(entry)
            resolved_by_rowid.setdefault(old_rid, entry)

        cards_report[cf.stem] = card_entries

    leg_conn.close()

    for old_rid, info in sorted(resolved_by_rowid.items()):
        conn.execute(
            """
            INSERT OR REPLACE INTO legacy_rowid_map(legacy_fts_rowid, block_pk, block_uid, match_method)
            VALUES (?, ?, ?, ?)
            """,
            (old_rid, info["block_pk"], info["block_uid"], info["match_method"]),
        )
    conn.commit()

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_cards_inspected": len(cards_report),
        "unique_legacy_rowids_mapped": len(resolved_by_rowid),
        "rowid_map": {str(k): v for k, v in sorted(resolved_by_rowid.items())},
        "cards": cards_report,
    }
    if migration_json_out is not None:
        migration_json_out.parent.mkdir(parents=True, exist_ok=True)
        migration_json_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def run_wave0_ingestion(
    db_path: Path = DEFAULT_DB_PATH,
    from_baidu_root: Path = DEFAULT_FROM_BAIDU_ROOT,
    source_pdf_dir: Path = DEFAULT_SOURCE_PDF_DIR,
    legacy_fts_db_path: Path | None = DEFAULT_LEGACY_FTS_DB,
    legacy_cards_dir: Path | None = DEFAULT_LEGACY_CARDS_DIR,
    migration_json_out: Path | None = DEFAULT_MIGRATION_JSON,
) -> dict[str, Any]:
    """Esegue l'ingestione completa idempotente di Wave 0 nel DB SQLite `pack_corpus.db`."""
    t0 = time.time()
    conn = init_corpus_db(db_path)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    existing_book_uids = {
        r["book_uid"] for r in conn.execute("SELECT book_uid FROM books").fetchall()
    }
    existing_block_uids = {
        r["block_uid"] for r in conn.execute("SELECT block_uid FROM blocks").fetchall()
    }

    from_before_dir = from_baidu_root / "from_before"
    before_files: dict[str, Path] = {}
    if from_before_dir.is_dir():
        for mf in sorted(from_before_dir.glob("*.md")):
            before_files[unicodedata.normalize("NFC", mf.stem).strip()] = mf

    baidu_dirs: dict[str, Path] = {}
    if from_baidu_root.is_dir():
        for d in sorted(from_baidu_root.iterdir()):
            if not d.is_dir() or d.name.startswith(".") or d.name in SYSTEM_SKIP_DIRS:
                continue
            if (d / "pages").is_dir() or list(d.glob("*.md")):
                baidu_dirs[unicodedata.normalize("NFC", d.name).strip()] = d

    all_md_titles = sorted(set(before_files.keys()) | set(baidu_dirs.keys()))

    stats = {
        "books_inserted": 0,
        "books_skipped_noise_or_dup": 0,
        "books_skipped_empty": 0,
        "hybrid_spliced_books": 0,
        "hybrid_spliced_baidu_pages": 0,
        "epub_books_inserted": 0,
        "blocks_inserted": 0,
        "body_blocks": 0,
        "footnote_blocks": 0,
        "paratext_blocks": 0,
        "total_chars": 0,
        "total_est_tokens": 0,
    }

    seen_canonical_keys: set[str] = set()

    def _insert_book_and_blocks(
        title: str,
        source_kind: str,
        source_path_str: str,
        raw_blocks: list[dict[str, Any]],
    ) -> bool:
        b_uid = make_book_uid(title, source_kind)
        if b_uid in existing_book_uids:
            return False

        total_words = sum(len(b["content"].split()) for b in raw_blocks)
        if total_words < 30:
            stats["books_skipped_empty"] += 1
            return False

        sample_text = "\n\n".join(b["content"] for b in raw_blocks[:10])
        author, year = parse_author_year(title)
        surface_domain = classify_surface_domain(title, sample_text)
        lang = detect_language(sample_text)
        page_cnt = max((b.get("page_end") or 0) for b in raw_blocks) or len(raw_blocks)

        cur = conn.execute(
            """
            INSERT INTO books(
                book_uid, title, author, year, surface_domain, language,
                source_kind, source_path, page_count, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                b_uid,
                title,
                author,
                year,
                surface_domain,
                lang,
                source_kind,
                source_path_str,
                page_cnt,
                now_iso,
            ),
        )
        book_pk = int(cur.lastrowid)
        existing_book_uids.add(b_uid)
        stats["books_inserted"] += 1

        rows_to_insert: list[tuple[Any, ...]] = []
        for b in raw_blocks:
            content = b["content"]
            norm_c = normalize_for_match(content)
            if not norm_c:
                continue
            p_start = b.get("page_start")
            p_end = b.get("page_end")
            blk_uid = make_block_uid(b_uid, p_start, p_end, norm_c)
            if blk_uid in existing_block_uids:
                continue
            existing_block_uids.add(blk_uid)

            sec_title = b.get("section_title") or ""
            role = classify_block_role(content, sec_title)
            c_len = len(content)
            t_est = estimate_bpe_tokens(content)

            rows_to_insert.append(
                (
                    blk_uid,
                    book_pk,
                    title,
                    role,
                    p_start,
                    p_end,
                    b.get("printed_page"),
                    sec_title,
                    content,
                    norm_c,
                    c_len,
                    t_est,
                    b["source_origin"],
                )
            )
            stats["blocks_inserted"] += 1
            stats["total_chars"] += c_len
            stats["total_est_tokens"] += t_est
            if role == "paratext":
                stats["paratext_blocks"] += 1
            elif role == "footnote":
                stats["footnote_blocks"] += 1
            else:
                stats["body_blocks"] += 1

        if rows_to_insert:
            conn.executemany(
                """
                INSERT INTO blocks(
                    block_uid, book_pk, book_title, is_active, superseded_by_pk,
                    block_role, page_start, page_end, printed_page, section_title,
                    content, norm_content, char_count, est_tokens, source_origin
                ) VALUES (?, ?, ?, 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        return True

    conn.execute("BEGIN")
    try:
        # 1. Volumi Markdown (from_before + page-level splicing Baidu OCR)
        for title in all_md_titles:
            if is_excluded_noise_title(title):
                stats["books_skipped_noise_or_dup"] += 1
                continue

            ckey = canonical_stem_key(title)
            if ckey in seen_canonical_keys and len(ckey) >= 18:
                stats["books_skipped_noise_or_dup"] += 1
                continue

            raw_blocks, src_kind, src_path, spliced_n = build_merged_markdown_volume_blocks(
                before_files.get(title), baidu_dirs.get(title)
            )
            if _insert_book_and_blocks(title, src_kind, src_path, raw_blocks):
                seen_canonical_keys.add(ckey)
                if spliced_n > 0:
                    stats["hybrid_spliced_books"] += 1
                    stats["hybrid_spliced_baidu_pages"] += spliced_n

        # 2. Volumi EPUB nativi in `PACK copy 4/source_pdf` (chiusura metà Buco D)
        if source_pdf_dir.is_dir():
            for epub_file in sorted(source_pdf_dir.glob("*.epub")):
                ep_title = unicodedata.normalize("NFC", epub_file.stem).strip()
                if is_excluded_noise_title(ep_title):
                    stats["books_skipped_noise_or_dup"] += 1
                    continue
                ckey = canonical_stem_key(ep_title)
                if ckey in seen_canonical_keys and len(ckey) >= 18:
                    continue
                epub_blocks = extract_epub_blocks(epub_file)
                if _insert_book_and_blocks(ep_title, "epub", str(epub_file), epub_blocks):
                    seen_canonical_keys.add(ckey)
                    stats["epub_books_inserted"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    migration_summary: dict[str, Any] = {}
    if legacy_fts_db_path and legacy_cards_dir and legacy_fts_db_path.exists() and legacy_cards_dir.exists():
        migration_summary = migrate_legacy_card_rowids(
            conn,
            legacy_fts_db_path=legacy_fts_db_path,
            legacy_cards_dir=legacy_cards_dir,
            migration_json_out=migration_json_out,
        )

    stats["elapsed_seconds"] = round(time.time() - t0, 2)
    stats["legacy_rowids_migrated"] = migration_summary.get("unique_legacy_rowids_mapped", 0)
    conn.close()
    return stats


if __name__ == "__main__":
    summary = run_wave0_ingestion()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
