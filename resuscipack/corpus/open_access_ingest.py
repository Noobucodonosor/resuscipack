"""Ingestione append-only e idempotente dei 5 pacchetti Open-Access (€0) in `pack_corpus.db` (TASK-BOOK-03).

Colma le lacune moderne assenti dalla biblioteca storica per il Volume II SecAI:
- OA-01: *Pro Git (2nd Edition, traduzione italiana)* — Scott Chacon, Ben Straub (CC BY-NC-SA 3.0)
- OA-02: *A Graduate Course in Applied Cryptography (v0.6)* — Dan Boneh, Victor Shoup (Free Academic PDF)
- OA-03: *Software Engineering at Google (Testing Chapters)* & *OWASP Web Security Testing Guide (v4.2)*
- OA-04: *OpenIntro Statistics (4th Edition)* — David Diez, Mine Çetinkaya-Rundel, Christopher Barr
- OA-05: *Attention Is All You Need*, *Explaining and Harnessing Adversarial Examples*, *Wild Patterns* (arXiv)

Garanzie strutturali:
- Rigorosamente append-only (`INSERT OR IGNORE`): nessun `block_pk` o `book_pk` esistente viene modificato.
- Allineamento garantito `COUNT(blocks WHERE is_active=1) == passages_fts_docsize`.
- Estrazione `BlockExtraction v2.2` reale tramite Vertex AI sui soli nuovi blocchi `open_access_oa` (zero mock).
"""

from __future__ import annotations

import argparse
import html.parser
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .normalizer import make_block_uid, normalize_for_match
from .schema import DEFAULT_DB_PATH, init_corpus_db

DEFAULT_OA_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "open_access_cache"


@dataclass(frozen=True)
class OpenAccessBlockDraft:
    """Singolo blocco testuale pulito pronto per l'inserimento append-only in `blocks`."""

    page: int
    section_title: str
    content: str


@dataclass(frozen=True)
class OpenAccessWorkDraft:
    """Opera Open-Access (€0) normalizzata con i relativi blocchi estratti."""

    book_uid: str
    title: str
    author: str
    year: int
    surface_domain: str
    language: str
    blocks: Tuple[OpenAccessBlockDraft, ...]


class _HtmlBodyExtractor(html.parser.HTMLParser):
    """Estrae testo leggibile da capitoli HTML rimuovendo script, style e navigazione."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in {"script", "style", "nav", "header", "footer"}:
            self._skip_depth += 1
        elif t in {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre", "div"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style", "nav", "header", "footer"} and self._skip_depth > 0:
            self._skip_depth -= 1
        elif t in {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self._chunks).replace("\xa0", " ")
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _fetch_bytes(url: str, *, cache_path: Optional[Path] = None, timeout: int = 45) -> bytes:
    if cache_path is not None and cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "resuscipack-open-access-ingest/1.0 (+https://github.com/Noobucodonosor/resuscipack)"},
    )
    with urllib.request.urlopen(req, timeout=int(timeout)) as resp:
        data = resp.read()
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
    return data


def _pdftotext_pages(pdf_path: Path, pdftotext_bin: str = "/opt/homebrew/bin/pdftotext") -> List[str]:
    bin_path = pdftotext_bin if Path(pdftotext_bin).exists() else "pdftotext"
    res = subprocess.run(
        [bin_path, str(pdf_path), "-"],
        check=True,
        capture_output=True,
    )
    txt = res.stdout.decode("utf-8", errors="replace")
    return [p.strip() for p in txt.split("\x0c") if p.strip()]


def _slice_into_blocks(text: str, *, section_title: str, start_page: int, max_chars: int = 2400) -> List[OpenAccessBlockDraft]:
    paras = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if len(p.strip()) >= 80]
    blocks: List[OpenAccessBlockDraft] = []
    buf: List[str] = []
    cur_len = 0
    page_num = start_page

    def _flush() -> None:
        nonlocal buf, cur_len, page_num
        if not buf:
            return
        body = "\n\n".join(buf).strip()
        if len(body) >= 180:
            blocks.append(OpenAccessBlockDraft(page=page_num, section_title=section_title, content=body))
            page_num += 1
        buf = []
        cur_len = 0

    for p in paras:
        if cur_len + len(p) > max_chars and cur_len >= 600:
            _flush()
        buf.append(p)
        cur_len += len(p) + 2
    _flush()
    return blocks


def _clean_asciidoc(raw: str) -> str:
    txt = re.sub(r"////.*?////", "", raw, flags=re.DOTALL)
    txt = re.sub(r"\[\[[^\]]+\]\]", "", txt)
    txt = re.sub(r"image::[^\n]+", "", txt)
    txt = re.sub(r"\[(?:source|NOTE|TIP|WARNING)[^\]]*\]", "", txt)
    txt = re.sub(r"\(\(\([^\)]+\)\)\)", "", txt)
    txt = re.sub(r"^=+\s*", "", txt, flags=re.MULTILINE)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _clean_markdown(raw: str) -> str:
    txt = re.sub(r"^\|ID\b.*?(?=\n#|\n[A-Z])", "", raw, flags=re.DOTALL | re.MULTILINE)
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.DOTALL)
    txt = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", txt)
    txt = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", txt)
    txt = re.sub(r"^#+\s*", "", txt, flags=re.MULTILINE)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _clean_latex_openintro(raw: str) -> str:
    txt = raw.split("\\exercisesheader", 1)[0]
    txt = re.sub(r"(?<!\\)%.*$", "", txt, flags=re.MULTILINE)
    for env in ("chapterpage", "figure", "table", "center", "tikzpicture", "comment", "exercises"):
        txt = re.sub(rf"\\begin\{{{env}\}}.*?\\end\{{{env}\}}", "", txt, flags=re.DOTALL)
    txt = re.sub(r"\\(?:label|ref|index|vspace|hspace|newpage|clearpage|renewcommand|chapterfolder)\{[^}]*\}(?:\{[^}]*\})?", "", txt)
    for cmd in ("chapter", "section", "subsection", "subsubsection", "textbf", "textit", "emph", "term", "hiddenterm", "vocab", "var", "chapterintro", "noindent"):
        txt = re.sub(rf"\\{cmd}\*?\{{([^}}]*)\}}", r"\1", txt)
    txt = txt.replace("\\chapterintro{", "").replace("\\noindent", "")
    txt = re.sub(r"\\begin\{(?:itemize|enumerate|description|example|tipBox|framed|eqnarray\*?|align\*?)\}(?:\[[^\]]*\])?", "\n", txt)
    txt = re.sub(r"\\end\{(?:itemize|enumerate|description|example|tipBox|framed|eqnarray\*?|align\*?)\}", "\n", txt)
    txt = txt.replace("\\item", "\n- ").replace("~", " ").replace("\\\\", "\n")
    txt = re.sub(r"\\%", "%", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def fetch_all_open_access_works(cache_dir: Path = DEFAULT_OA_CACHE_DIR) -> List[OpenAccessWorkDraft]:
    """Scarica/estrae dalla cache i 5 pacchetti Open-Access ufficiali (€0)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    works: List[OpenAccessWorkDraft] = []

    # OA-01: Pro Git (2nd Ed., italiano)
    progit_urls = [
        ("Cos'è il controllo versione", "https://raw.githubusercontent.com/progit/progit2-it/master/book/01-introduction/sections/about-version-control.asc"),
        ("Creare un repository Git", "https://raw.githubusercontent.com/progit/progit2-it/master/book/02-git-basics/sections/getting-a-repository.asc"),
        ("Registrare le modifiche", "https://raw.githubusercontent.com/progit/progit2-it/master/book/02-git-basics/sections/recording-changes.asc"),
        ("Cosa sono i branch in breve", "https://raw.githubusercontent.com/progit/progit2-it/master/book/03-git-branching/sections/nutshell.asc"),
        ("Branching e merging di base", "https://raw.githubusercontent.com/progit/progit2-it/master/book/03-git-branching/sections/basic-branching-and-merging.asc"),
    ]
    pg_blocks: List[OpenAccessBlockDraft] = []
    pg_page = 1
    for sec_title, url in progit_urls:
        raw = _fetch_bytes(url, cache_path=cache_dir / f"progit_it_{pg_page}.asc").decode("utf-8", errors="replace")
        sec_blocks = _slice_into_blocks(_clean_asciidoc(raw), section_title=sec_title, start_page=pg_page, max_chars=2300)[:2]
        pg_blocks.extend(sec_blocks)
        pg_page = pg_blocks[-1].page + 1 if pg_blocks else pg_page + 1
    works.append(
        OpenAccessWorkDraft(
            book_uid="oa_01_pro_git_it",
            title="Pro Git (2nd Edition, traduzione italiana)",
            author="Scott Chacon, Ben Straub",
            year=2014,
            surface_domain="informatica",
            language="it",
            blocks=tuple(pg_blocks),
        )
    )

    # OA-02: Boneh & Shoup Applied Cryptography (v0.6)
    bs_pdf = cache_dir / "oa_02_boneh_shoup_v0.6.pdf"
    _fetch_bytes("https://toc.cryptobook.us/book.pdf", cache_path=bs_pdf, timeout=90)
    bs_pages = _pdftotext_pages(bs_pdf)
    crypto_keywords = (
        ("Hash functions and collision resistance", "collision resistance"),
        ("Diffie-Hellman key exchange", "diffie-hellman"),
        ("RSA trapdoor and encryption", "rsa"),
        ("Digital signatures and unforgeability", "digital signature"),
        ("Message authentication codes", "message authentication"),
        ("Authenticated encryption and TLS", "authenticated encryption"),
    )
    bs_blocks: List[OpenAccessBlockDraft] = []
    used_idx: set[int] = set()
    for sec_title, kw in crypto_keywords:
        best_idx: Optional[int] = None
        for idx, ptxt in enumerate(bs_pages):
            if idx in used_idx or idx < 25:
                continue
            low = ptxt.lower()
            if kw in low and len(ptxt) >= 900 and "contents" not in low[:120] and "bibliography" not in low[:120]:
                best_idx = idx
                break
        if best_idx is not None:
            used_idx.add(best_idx)
            clean_p = re.sub(r"\s{3,}", " ", bs_pages[best_idx])
            bs_blocks.append(OpenAccessBlockDraft(page=best_idx + 1, section_title=sec_title, content=clean_p[:3200]))
    works.append(
        OpenAccessWorkDraft(
            book_uid="oa_02_boneh_shoup_crypto",
            title="A Graduate Course in Applied Cryptography (v0.6)",
            author="Dan Boneh, Victor Shoup",
            year=2023,
            surface_domain="informatica",
            language="en",
            blocks=tuple(bs_blocks),
        )
    )

    # OA-03a: OWASP Web Security Testing Guide v4.2
    owasp_urls = [
        ("Testing for SQL Injection", "https://raw.githubusercontent.com/OWASP/wstg/v4.2/document/4-Web_Application_Security_Testing/07-Input_Validation_Testing/05-Testing_for_SQL_Injection.md"),
        ("Testing for Reflected XSS", "https://raw.githubusercontent.com/OWASP/wstg/v4.2/document/4-Web_Application_Security_Testing/07-Input_Validation_Testing/01-Testing_for_Reflected_Cross_Site_Scripting.md"),
        ("Authentication Testing Overview", "https://raw.githubusercontent.com/OWASP/wstg/v4.2/document/4-Web_Application_Security_Testing/04-Authentication_Testing/README.md"),
        ("Session Management Testing", "https://raw.githubusercontent.com/OWASP/wstg/v4.2/document/4-Web_Application_Security_Testing/06-Session_Management_Testing/README.md"),
    ]
    ow_blocks: List[OpenAccessBlockDraft] = []
    ow_page = 1
    for sec_title, url in owasp_urls:
        raw = _fetch_bytes(url, cache_path=cache_dir / f"owasp_v42_{ow_page}.md").decode("utf-8", errors="replace")
        sec_blocks = _slice_into_blocks(_clean_markdown(raw), section_title=sec_title, start_page=ow_page, max_chars=2300)[:2]
        ow_blocks.extend(sec_blocks)
        ow_page = ow_blocks[-1].page + 1 if ow_blocks else ow_page + 1
    works.append(
        OpenAccessWorkDraft(
            book_uid="oa_03_owasp_wstg_v42",
            title="OWASP Web Security Testing Guide (v4.2)",
            author="OWASP Foundation",
            year=2021,
            surface_domain="informatica",
            language="en",
            blocks=tuple(ow_blocks),
        )
    )

    # OA-03b: Software Engineering at Google (Testing Chapters)
    swe_urls = [
        ("Testing Overview", "https://abseil.io/resources/swe-book/html/ch11.html"),
        ("Unit Testing", "https://abseil.io/resources/swe-book/html/ch12.html"),
    ]
    swe_blocks: List[OpenAccessBlockDraft] = []
    swe_page = 1
    for sec_title, url in swe_urls:
        html_raw = _fetch_bytes(url, cache_path=cache_dir / f"swe_google_{swe_page}.html").decode("utf-8", errors="replace")
        parser = _HtmlBodyExtractor()
        parser.feed(html_raw)
        sec_blocks = _slice_into_blocks(parser.get_text(), section_title=sec_title, start_page=swe_page, max_chars=2300)[:3]
        swe_blocks.extend(sec_blocks)
        swe_page = swe_blocks[-1].page + 1 if swe_blocks else swe_page + 1
    works.append(
        OpenAccessWorkDraft(
            book_uid="oa_03_swe_google_testing",
            title="Software Engineering at Google (Testing Chapters)",
            author="Titus Winters, Tom Manshreck, Hyrum Wright",
            year=2020,
            surface_domain="informatica",
            language="en",
            blocks=tuple(swe_blocks),
        )
    )

    # OA-04: OpenIntro Statistics 4th Edition (capitoli principali di prosa `.tex`)
    oi_sources = [
        (
            "Introduction to Data and Sampling",
            "https://raw.githubusercontent.com/OpenIntroStat/openintro-statistics/master/ch_intro_to_data/TeX/ch_intro_to_data.tex",
            None,
        ),
        (
            "Confidence Intervals",
            "https://raw.githubusercontent.com/OpenIntroStat/openintro-statistics/master/ch_foundations_for_inf/TeX/ch_foundations_for_inf.tex",
            "Confidence intervals",
        ),
        (
            "Hypothesis Testing and P-values",
            "https://raw.githubusercontent.com/OpenIntroStat/openintro-statistics/master/ch_foundations_for_inf/TeX/ch_foundations_for_inf.tex",
            "Hypothesis testing",
        ),
        (
            "Fitting a Line by Least Squares Regression",
            "https://raw.githubusercontent.com/OpenIntroStat/openintro-statistics/master/ch_regr_simple_linear/TeX/ch_regr_simple_linear.tex",
            "Least squares regression",
        ),
    ]
    oi_blocks: List[OpenAccessBlockDraft] = []
    oi_page = 1
    oi_cache_map: Dict[str, str] = {}
    for sec_title, url, anchor in oi_sources:
        if url not in oi_cache_map:
            fname = url.rsplit("/", 1)[-1]
            oi_cache_map[url] = _fetch_bytes(url, cache_path=cache_dir / f"openintro_{fname}").decode(
                "utf-8", errors="replace"
            )
        raw_tex = oi_cache_map[url]
        if anchor:
            idx_a = raw_tex.lower().find(anchor.lower())
            if idx_a > 0:
                raw_tex = raw_tex[idx_a:]
        sec_blocks = _slice_into_blocks(_clean_latex_openintro(raw_tex), section_title=sec_title, start_page=oi_page, max_chars=2300)[:2]
        oi_blocks.extend(sec_blocks)
        oi_page = oi_blocks[-1].page + 1 if oi_blocks else oi_page + 1
    works.append(
        OpenAccessWorkDraft(
            book_uid="oa_04_openintro_stats4",
            title="OpenIntro Statistics (4th Edition)",
            author="David Diez, Mine Cetinkaya-Rundel, Christopher Barr",
            year=2019,
            surface_domain="matematica",
            language="en",
            blocks=tuple(oi_blocks),
        )
    )

    # OA-05: 3 arXiv foundational papers (Transformer + Adversarial Examples + Wild Patterns)
    arxiv_specs = [
        ("oa_05_arxiv_vaswani_transformer", "Attention Is All You Need", "Ashish Vaswani et al.", 2017, "https://arxiv.org/pdf/1706.03762.pdf", 6),
        ("oa_05_arxiv_goodfellow_advml", "Explaining and Harnessing Adversarial Examples", "Ian J. Goodfellow, Jonathon Shlens, Christian Szegedy", 2015, "https://arxiv.org/pdf/1412.6572.pdf", 6),
        ("oa_05_arxiv_biggio_wild_patterns", "Wild Patterns: Ten Years After the Rise of Adversarial Machine Learning", "Battista Biggio, Fabio Roli", 2018, "https://arxiv.org/pdf/1712.03141.pdf", 6),
    ]
    for b_uid, title, author, yr, pdf_url, max_p in arxiv_specs:
        pdf_path = cache_dir / f"{b_uid}.pdf"
        _fetch_bytes(pdf_url, cache_path=pdf_path, timeout=60)
        pages = _pdftotext_pages(pdf_path)
        ax_blocks = [
            OpenAccessBlockDraft(page=idx + 1, section_title=f"Sezione p. {idx + 1}", content=ptxt[:3200])
            for idx, ptxt in enumerate(pages[:max_p])
            if len(ptxt) >= 350
        ]
        works.append(
            OpenAccessWorkDraft(
                book_uid=b_uid,
                title=title,
                author=author,
                year=yr,
                surface_domain="informatica",
                language="en",
                blocks=tuple(ax_blocks),
            )
        )

    return works


def ingest_open_access_sources(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    cache_dir: Path = DEFAULT_OA_CACHE_DIR,
    preloaded_works: Optional[Sequence[OpenAccessWorkDraft]] = None,
    extract_v22: bool = True,
    provider: str = "vertex",
    workers: int = 4,
    llm_fn: Optional[Callable[[str, Any], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Inserisce in modo append-only le opere Open-Access (€0) e avvia l'estrazione v2.2 sui nuovi blocchi."""
    works = list(preloaded_works) if preloaded_works is not None else fetch_all_open_access_works(cache_dir)
    conn = init_corpus_db(db_path)
    conn.row_factory = sqlite3.Row

    books_inserted = 0
    blocks_inserted = 0
    inserted_block_pks: List[int] = []
    oa_book_pks: List[int] = []

    try:
        for work in works:
            cur_bk = conn.execute(
                """
                INSERT OR IGNORE INTO books (
                    book_uid, title, author, year, surface_domain, language,
                    source_kind, source_path, page_count, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, 'open_access', ?, ?, 1)
                """,
                (
                    work.book_uid,
                    work.title,
                    work.author,
                    work.year,
                    work.surface_domain,
                    work.language,
                    f"open_access://{work.book_uid}",
                    len(work.blocks),
                ),
            )
            if cur_bk.rowcount > 0:
                books_inserted += 1
            bk_row = conn.execute("SELECT book_pk FROM books WHERE book_uid = ?", (work.book_uid,)).fetchone()
            assert bk_row is not None
            book_pk = int(bk_row["book_pk"])
            oa_book_pks.append(book_pk)

            for blk in work.blocks:
                norm_c = normalize_for_match(blk.content)
                if len(norm_c) < 60:
                    continue
                blk_uid = make_block_uid(work.book_uid, blk.page, blk.page, norm_c)
                est_tok = max(1, len(blk.content) // 4)
                cur_bl = conn.execute(
                    """
                    INSERT OR IGNORE INTO blocks (
                        block_uid, book_pk, book_title, is_active, block_role,
                        page_start, page_end, printed_page, section_title,
                        content, norm_content, char_count, est_tokens, source_origin
                    ) VALUES (?, ?, ?, 1, 'body', ?, ?, ?, ?, ?, ?, ?, ?, 'open_access_oa')
                    """,
                    (
                        blk_uid,
                        book_pk,
                        work.title,
                        blk.page,
                        blk.page,
                        str(blk.page),
                        blk.section_title,
                        blk.content,
                        norm_c,
                        len(blk.content),
                        est_tok,
                    ),
                )
                row_bl = conn.execute("SELECT block_pk FROM blocks WHERE block_uid = ?", (blk_uid,)).fetchone()
                if row_bl is not None:
                    bpk = int(row_bl["block_pk"])
                    if cur_bl.rowcount > 0:
                        blocks_inserted += 1
                    inserted_block_pks.append(bpk)

        conn.commit()
        active_blocks = int(conn.execute("SELECT COUNT(*) FROM blocks WHERE is_active = 1").fetchone()[0])
        fts_rows = int(conn.execute("SELECT COUNT(*) FROM passages_fts_docsize").fetchone()[0])
        if active_blocks != fts_rows:
            raise RuntimeError(f"Disallineamento FTS5 dopo ingestione Open-Access: {active_blocks} != {fts_rows}")

        pending_pks = [
            int(r["block_pk"])
            for r in conn.execute(
                """
                SELECT b.block_pk
                FROM blocks b
                LEFT JOIN block_extraction_log bel ON bel.block_pk = b.block_pk
                WHERE b.source_origin = 'open_access_oa'
                  AND b.is_active = 1
                  AND bel.block_pk IS NULL
                ORDER BY b.block_pk ASC
                """
            ).fetchall()
        ]
    finally:
        conn.close()

    extraction_summary: Optional[Dict[str, Any]] = None
    if extract_v22 and pending_pks:
        from ..epistemic.batch_cli import run_batch_extraction

        extraction_summary = run_batch_extraction(
            db_path=db_path,
            limit=None,
            provider=provider,
            workers=workers,
            pack_size=min(4, max(1, len(pending_pks))) if llm_fn is None else 1,
            require_v22_metadata=True if llm_fn is None else False,
            block_pks=pending_pks,
            discover_bridges=False,
            status_file=None,
            llm_fn=llm_fn,
        )

    return {
        "works_processed": len(works),
        "books_inserted": books_inserted,
        "blocks_inserted": blocks_inserted,
        "oa_blocks_total": len(inserted_block_pks),
        "oa_blocks_pending_v22": len(pending_pks),
        "active_blocks_after": active_blocks,
        "fts_rows_after": fts_rows,
        "extraction_summary": extraction_summary,
    }


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingestione append-only e estrazione v2.2 dei 5 testi Open-Access (€0)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_OA_CACHE_DIR)
    parser.add_argument("--no-extract", action="store_true", help="Salta l'estrazione v2.2 via Vertex AI")
    parser.add_argument("--provider", type=str, default="vertex", choices=("vertex", "gemini", "deepseek"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = ingest_open_access_sources(
        args.db,
        cache_dir=args.cache_dir,
        extract_v22=not args.no_extract,
        provider=args.provider,
        workers=args.workers,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


__all__ = [
    "DEFAULT_OA_CACHE_DIR",
    "OpenAccessBlockDraft",
    "OpenAccessWorkDraft",
    "fetch_all_open_access_works",
    "ingest_open_access_sources",
]

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
