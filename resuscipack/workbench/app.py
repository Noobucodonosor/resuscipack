#!/usr/bin/env python3
"""Server Flask editoriale di resuscipack (ADR-0003 + ADR-0004, M4).

Caratteristiche chiave:
- `pack_corpus.db` sempre aperto in sola lettura (`file:...?mode=ro`);
- `student_state.db` separato per progressi, Fast-Forward `SymPy` e verifiche;
- Tre superfici editoriali condivise: `/` (Ingresso editoriale), `/libro` (Il Libro Continuo),
  `/atlante` (L'Atlante della Biblioteca con Spettro Percentuale e Libro Sbagliato dal basso).
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from resuscipack.books.author_engine import DEFAULT_BOOKS_DIR, _clean_book_title_for_citation
from resuscipack.books.svg_diagrams import (
    DEFAULT_ASSETS_DIR,
    DEFAULT_FIGURES_DIR,
    find_corpus_figures_for_blocks,
)
from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db
from resuscipack.curriculum.cards import (
    DEFAULT_CARDS_DIR,
    list_available_card_ids,
    load_card,
)
from resuscipack.curriculum.dag import (
    DEFAULT_DAG_PATH,
    DEFAULT_OPEN_ACCESS_PATH,
    compute_frontier_nodes,
    load_open_access_registry,
    load_unified_dag,
)
from resuscipack.curriculum.drills_sympy import (
    evaluate_proof_rubric,
    generate_drill_set,
    grade_drill_answer,
    verify_graph_invariants,
)
from resuscipack.curriculum.student_state import (
    DEFAULT_STATE_DB_PATH,
    flag_card_issue,
    get_student_snapshot,
    init_student_state_db,
    record_drill_attempt,
    record_hero_artifact,
)
from resuscipack.epistemic.bridge import get_bridges_for_node
from resuscipack.epistemic.decompressor import decompress_concept
from resuscipack.epistemic.discipline_reconstructor import reconstruct_discipline
from resuscipack.epistemic.schema_v21 import ALL_MACRO_DISCIPLINES
from resuscipack.epistemic.spectrum import (
    get_book_spectrum,
    is_residual_paratext_block,
    label_for_discipline,
    resolve_macro_discipline,
)
from resuscipack.workbench.books_view import (
    list_volumes_and_chapters,
    load_book_chapter,
    load_ofa_30_questions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ASSETS_DIR = REPO_ROOT / "public" / "assets"


def sanitize_fts5_query(raw_query: str) -> str:
    """Sanifica una stringa utente in sintassi valida per SQLite FTS5 MATCH."""
    if not raw_query or not raw_query.strip():
        return ""
    trimmed = raw_query.strip()[:400]
    raw_tokens = re.findall(r'"([^"]*)"|(\S+)', trimmed)
    tokens: list[str] = []
    for phrase, word in raw_tokens:
        if phrase:
            clean_p = phrase.replace('"', '""').strip()
            if clean_p:
                tokens.append(f'"{clean_p}"')
        elif word:
            upper = word.upper()
            if upper in {"AND", "OR", "NOT"}:
                if tokens and tokens[-1] not in {"AND", "OR", "NOT"}:
                    tokens.append(upper)
            else:
                for sub in re.sub(r"[^0-9A-Za-zÀ-ÿ\s]", " ", word).split():
                    if sub:
                        tokens.append(f'"{sub}"')
    while tokens and tokens[-1] in {"AND", "OR", "NOT"}:
        tokens.pop()
    return " ".join(tokens[:24])


def highlight_verbatim_quote(full_text: str, quote: str | None) -> tuple[str, bool]:
    """Restituisce HTML sicuro del testo completo del blocco evidenziando in `<mark>` la citazione."""
    if not quote or not quote.strip():
        return html.escape(full_text, quote=False), False

    words = [w for w in re.findall(r"\S+", quote.strip()) if w]
    if not words:
        return html.escape(full_text, quote=False), False

    def _word_regex(token: str) -> str:
        core = re.escape(token)
        core = core.replace(r"\'", r"['’‘]").replace("’", r"['’‘]")
        core = core.replace("«", r'[«"“]').replace("»", r'[»"”]')
        core = core.replace(r"\"", r'[«»"“”]')
        return core

    pattern_str = r"\s+".join(_word_regex(w) for w in words)
    m = re.search(pattern_str, full_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return html.escape(full_text, quote=False), False

    before = html.escape(full_text[: m.start()], quote=False)
    matched = html.escape(full_text[m.start() : m.end()], quote=False)
    after = html.escape(full_text[m.end() :], quote=False)
    return f'{before}<mark class="verbatim-highlight">{matched}</mark>{after}', True


def _clean_excerpt(content: str, verbatim_quote: str | None, max_len: int = 260) -> str:
    if verbatim_quote and verbatim_quote.strip():
        return " ".join(verbatim_quote.split()).strip()
    collapsed = " ".join(str(content or "").split()).strip()
    if len(collapsed) <= max_len:
        return collapsed
    cut = collapsed[:max_len].rsplit(" ", 1)[0].strip()
    return f"{cut}…"


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def create_app(
    *,
    corpus_db_path: Path | str = DEFAULT_DB_PATH,
    state_db_path: Path | str = DEFAULT_STATE_DB_PATH,
    dag_path: Path | str = DEFAULT_DAG_PATH,
    open_access_path: Path | str = DEFAULT_OPEN_ACCESS_PATH,
    cards_dir: Path | str = DEFAULT_CARDS_DIR,
    books_dir: Path | str = DEFAULT_BOOKS_DIR,
    status_file_path: Path | str | None = None,
) -> Flask:
    here = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(here / "templates"),
        static_folder=str(here / "static"),
    )
    app.config["CORPUS_DB_PATH"] = Path(corpus_db_path)
    app.config["STATE_DB_PATH"] = Path(state_db_path)
    app.config["DAG_PATH"] = Path(dag_path)
    app.config["OPEN_ACCESS_PATH"] = Path(open_access_path)
    app.config["CARDS_DIR"] = Path(cards_dir)
    app.config["BOOKS_DIR"] = Path(books_dir)
    app.config["STATUS_FILE_PATH"] = (
        Path(status_file_path)
        if status_file_path is not None
        else REPO_ROOT / "data" / "wave1_status.json"
    )

    dag_payload = load_unified_dag(app.config["DAG_PATH"])
    oa_registry = load_open_access_registry(app.config["OPEN_ACCESS_PATH"])
    oa_by_id = {item["id"]: item for item in oa_registry.get("open_access_acquisitions", [])}

    # Inizializza il DB separato dello stato studente (mai pack_corpus.db!)
    init_student_state_db(app.config["STATE_DB_PATH"]).close()

    def _state_conn():
        return init_student_state_db(app.config["STATE_DB_PATH"])

    def _corpus_ro_conn():
        db_p: Path = app.config["CORPUS_DB_PATH"]
        if not db_p.exists():
            return None
        return connect_corpus_db(db_p, read_only=True)

    # ------------------------------------------------------------------
    # Static kit & figure routes
    # ------------------------------------------------------------------
    @app.get("/assets/<path:filename>")
    def serve_public_assets(filename: str):
        if not PUBLIC_ASSETS_DIR.exists():
            abort(404)
        return send_from_directory(PUBLIC_ASSETS_DIR, filename)

    @app.get("/books-assets/<path:filename>")
    def serve_book_assets(filename: str):
        if not DEFAULT_ASSETS_DIR.exists():
            abort(404)
        return send_from_directory(DEFAULT_ASSETS_DIR, filename)

    @app.get("/corpus-figures/<path:filename>")
    def serve_corpus_figures(filename: str):
        if not DEFAULT_FIGURES_DIR.exists():
            abort(404)
        return send_from_directory(DEFAULT_FIGURES_DIR, filename)

    # ------------------------------------------------------------------
    # Editorial HTML pages
    # ------------------------------------------------------------------
    @app.get("/")
    def index() -> str:
        vols = list_volumes_and_chapters(app.config["BOOKS_DIR"])
        books_count = 1424
        canonical_count = 1131
        marconi_slices: list[dict[str, Any]] = []
        marconi_bar_slices: list[dict[str, Any]] = []
        marconi_title = "Guglielmo Marconi"
        marconi_meta = "Giancarlo Masini · 1975"
        geo_books = 69
        geo_passages = 653

        cconn = _corpus_ro_conn()
        if cconn is not None:
            try:
                books_count = int(
                    cconn.execute("SELECT COUNT(*) FROM books WHERE is_active = 1").fetchone()[0]
                )
                has_meta = (
                    cconn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='book_spectrum_meta'"
                    ).fetchone()
                    is not None
                )
                if has_meta:
                    canonical_count = int(
                        cconn.execute(
                            "SELECT COUNT(*) FROM book_spectrum_meta WHERE quality_tier = 'canonical_book'"
                        ).fetchone()[0]
                    )
                    spec = get_book_spectrum(cconn, 514)
                    if spec:
                        marconi_title = _clean_book_title_for_citation(
                            spec["title"], author=spec.get("author")
                        )
                        yr_s = f" · {spec['year']}" if spec.get("year") else ""
                        marconi_meta = f"{spec.get('author') or ''}{yr_s}".strip(" ·")
                        all_slices = [
                            {
                                "slug": d["macro_discipline"],
                                "label": d["label_it"],
                                "share_pct": round(float(d["share_pct"]), 1),
                                "coverage_pct": round(float(d["coverage_pct"]), 1),
                                "block_count": int(d["block_count"]),
                            }
                            for d in spec["disciplines"]
                        ]
                        marconi_bar_slices = all_slices[:8]
                        marconi_slices = all_slices[:5]
            finally:
                cconn.close()

        return render_template(
            "index.html",
            books_count=books_count,
            canonical_count=canonical_count,
            chapters_count=vols["total_chapters"],
            volumes=vols["volumes"],
            marconi_title=marconi_title,
            marconi_meta=marconi_meta,
            marconi_slices=marconi_slices,
            marconi_bar_slices=marconi_bar_slices,
            geo_books=geo_books,
            geo_passages=geo_passages,
        )

    @app.get("/libro")
    @app.get("/libro/<volume_id>/<slug>")
    def book_reader_page(volume_id: str = "vol1_ofa", slug: str = "dall_ovvio_al_numero") -> str:
        return render_template(
            "reader.html",
            initial_volume_id=volume_id,
            initial_slug=slug,
        )

    @app.get("/atlante")
    @app.get("/atlante/libro/<int:book_pk>")
    def atlas_page(book_pk: int | None = None) -> str:
        return render_template(
            "atlas.html",
            initial_book_pk=book_pk,
            initial_discipline=request.args.get("discipline", ""),
        )

    # ------------------------------------------------------------------
    # Book Reader REST APIs
    # ------------------------------------------------------------------
    @app.get("/api/books")
    def api_books_list():
        return jsonify(list_volumes_and_chapters(app.config["BOOKS_DIR"]))

    @app.get("/api/books/ofa-questions")
    def api_books_ofa_questions():
        return jsonify(load_ofa_30_questions(app.config["BOOKS_DIR"]))

    @app.get("/api/books/<volume_id>/<slug>")
    def api_book_chapter(volume_id: str, slug: str):
        seed_val = request.args.get("seed", default=42, type=int)
        chapter = load_book_chapter(
            volume_id,
            slug,
            books_dir=app.config["BOOKS_DIR"],
            dag_payload=dag_payload,
            seed=seed_val,
        )
        if chapter is None:
            abort(404, description="Capitolo non trovato")
        return jsonify(chapter)

    # ------------------------------------------------------------------
    # Atlas & Disciplinary Spectrum REST APIs
    # ------------------------------------------------------------------
    @app.get("/api/atlas/disciplines")
    def api_atlas_disciplines():
        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            cconn.row_factory = sqlite3_row_factory()
            total_by_disc: dict[str, int] = {d: 0 for d in ALL_MACRO_DISCIPLINES}
            primary_by_disc: dict[str, int] = {d: 0 for d in ALL_MACRO_DISCIPLINES}
            wrong_by_disc: dict[str, int] = {d: 0 for d in ALL_MACRO_DISCIPLINES}

            rows = cconn.execute(
                """
                SELECT s.macro_discipline, m.primary_discipline, COUNT(*) AS n
                FROM book_discipline_spectrum s
                JOIN books bk ON bk.book_pk = s.book_pk
                LEFT JOIN book_spectrum_meta m ON m.book_pk = s.book_pk
                WHERE bk.is_active = 1
                  AND COALESCE(m.quality_tier, 'canonical_book') != 'non_book_noise'
                GROUP BY s.macro_discipline, m.primary_discipline
                """
            ).fetchall()
            for r in rows:
                md = str(r["macro_discipline"])
                pm = str(r["primary_discipline"] or "")
                cnt = int(r["n"])
                if md in total_by_disc:
                    total_by_disc[md] += cnt
                    if pm == md:
                        primary_by_disc[md] += cnt
                    else:
                        wrong_by_disc[md] += cnt

            items = [
                {
                    "slug": d,
                    "label_it": label_for_discipline(d),
                    "total_books_count": total_by_disc[d],
                    "primary_books_count": primary_by_disc[d],
                    "wrong_books_count": wrong_by_disc[d],
                }
                for d in ALL_MACRO_DISCIPLINES
            ]
            items.sort(key=lambda x: (-x["total_books_count"], x["label_it"]))
            return jsonify({"disciplines": items})
        finally:
            cconn.close()

    @app.get("/api/atlas/books")
    def api_atlas_books():
        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")

        q_raw = str(request.args.get("q") or "").strip().lower()
        primary_raw = str(request.args.get("primary") or "").strip()
        contains_raw = str(request.args.get("contains") or "").strip()
        min_cov = request.args.get("min_cov", default=0.0, type=float)
        only_secondary = str(request.args.get("only_secondary") or "0").lower() in {"1", "true", "yes"}
        include_noise = str(request.args.get("include_noise") or "0").lower() in {"1", "true", "yes"}
        sort_mode = str(request.args.get("sort") or "").strip().lower()

        try:
            primary_slug = resolve_macro_discipline(primary_raw).value if primary_raw else None
            contains_slug = resolve_macro_discipline(contains_raw).value if contains_raw else None
        except ValueError as exc:
            cconn.close()
            abort(400, description=str(exc))

        try:
            cconn.row_factory = sqlite3_row_factory()
            total_active = int(
                cconn.execute("SELECT COUNT(*) FROM books WHERE is_active = 1").fetchone()[0]
            )
            book_rows = cconn.execute(
                """
                SELECT
                    bk.book_pk, bk.title, bk.author, bk.year, bk.surface_domain, bk.source_kind,
                    COALESCE(m.active_blocks_count, 0) AS active_blocks_count,
                    COALESCE(m.v22_blocks_count, 0) AS v22_blocks_count,
                    m.primary_discipline,
                    COALESCE(m.primary_share_pct, 0.0) AS primary_share_pct,
                    COALESCE(m.distinct_disciplines, 0) AS distinct_disciplines,
                    COALESCE(m.quality_tier, 'canonical_book') AS quality_tier
                FROM books bk
                LEFT JOIN book_spectrum_meta m ON m.book_pk = bk.book_pk
                WHERE bk.is_active = 1
                ORDER BY bk.title COLLATE NOCASE ASC, bk.book_pk ASC
                """
            ).fetchall()

            spec_rows = cconn.execute(
                """
                SELECT book_pk, macro_discipline, coverage_pct, share_pct, block_count
                FROM book_discipline_spectrum
                ORDER BY book_pk ASC, share_pct DESC, coverage_pct DESC
                """
            ).fetchall()

            spec_by_book: dict[int, list[dict[str, Any]]] = {}
            cov_lookup: dict[tuple[int, str], float] = {}
            for sr in spec_rows:
                bpk = int(sr["book_pk"])
                md = str(sr["macro_discipline"])
                cov = float(sr["coverage_pct"])
                spec_by_book.setdefault(bpk, []).append(
                    {
                        "discipline": md,
                        "label_it": label_for_discipline(md),
                        "coverage_pct": round(cov, 1),
                        "share_pct": round(float(sr["share_pct"]), 1),
                        "block_count": int(sr["block_count"]),
                    }
                )
                cov_lookup[(bpk, md)] = cov

            results: list[dict[str, Any]] = []
            for br in book_rows:
                bpk = int(br["book_pk"])
                tier = str(br["quality_tier"])
                if not include_noise and tier == "non_book_noise":
                    continue

                raw_title = str(br["title"] or "")
                author = str(br["author"] or "")
                clean_title = _clean_book_title_for_citation(raw_title, author=author or None)

                if q_raw:
                    hay = f"{clean_title} {raw_title} {author}".lower()
                    if q_raw not in hay:
                        continue

                p_disc = br["primary_discipline"]
                if primary_slug and p_disc != primary_slug:
                    continue

                target_cov = cov_lookup.get((bpk, contains_slug), 0.0) if contains_slug else 0.0
                if contains_slug:
                    if (bpk, contains_slug) not in cov_lookup or target_cov < float(min_cov):
                        continue
                    if only_secondary and p_disc == contains_slug:
                        continue

                results.append(
                    {
                        "book_pk": bpk,
                        "title": clean_title,
                        "author": author or None,
                        "year": br["year"],
                        "source_kind": br["source_kind"],
                        "quality_tier": tier,
                        "active_blocks_count": int(br["active_blocks_count"]),
                        "v22_blocks_count": int(br["v22_blocks_count"]),
                        "distinct_disciplines": int(br["distinct_disciplines"]),
                        "primary_discipline": p_disc,
                        "primary_discipline_label": label_for_discipline(p_disc) if p_disc else "Da catalogare",
                        "primary_share_pct": round(float(br["primary_share_pct"]), 1),
                        "target_coverage_pct": round(target_cov, 1) if contains_slug else None,
                        "spectrum": spec_by_book.get(bpk, []),
                    }
                )

            if sort_mode == "coverage" or (contains_slug and not sort_mode):
                results.sort(
                    key=lambda x: (
                        -(x["target_coverage_pct"] if x["target_coverage_pct"] is not None else x["primary_share_pct"]),
                        -x["active_blocks_count"],
                        x["title"].lower(),
                    )
                )
            elif sort_mode == "blocks":
                results.sort(key=lambda x: (-x["v22_blocks_count"], -x["active_blocks_count"], x["title"].lower()))
            else:
                results.sort(key=lambda x: (0 if x["v22_blocks_count"] > 0 else 1, x["title"].lower(), x["book_pk"]))

            return jsonify(
                {
                    "total": len(results),
                    "total_active_library": total_active,
                    "books": results,
                }
            )
        finally:
            cconn.close()

    @app.get("/api/atlas/book/<int:book_pk>")
    def api_atlas_book_detail(book_pk: int):
        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            spec = get_book_spectrum(cconn, book_pk)
            if spec is None:
                abort(404, description="Opera non trovata nell'atlante")
            spec["clean_title"] = _clean_book_title_for_citation(
                spec["title"], author=spec.get("author")
            )
            return jsonify(spec)
        finally:
            cconn.close()

    @app.get("/api/atlas/book/<int:book_pk>/passages")
    def api_atlas_book_passages(book_pk: int):
        disc_raw = str(request.args.get("discipline") or "").strip()
        if not disc_raw:
            abort(400, description="Parametro discipline obbligatorio")
        try:
            disc_slug = resolve_macro_discipline(disc_raw).value
        except ValueError as exc:
            abort(400, description=str(exc))

        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            cconn.row_factory = sqlite3_row_factory()
            book_row = cconn.execute(
                "SELECT book_pk, title, author, year FROM books WHERE book_pk = ? AND is_active = 1",
                (book_pk,),
            ).fetchone()
            if book_row is None:
                abort(404, description="Opera non trovata")

            spec_row = cconn.execute(
                """
                SELECT coverage_pct, share_pct, block_pks_json
                FROM book_discipline_spectrum
                WHERE book_pk = ? AND macro_discipline = ?
                """,
                (book_pk, disc_slug),
            ).fetchone()

            block_pks: list[int] = (
                [int(pk) for pk in json.loads(spec_row["block_pks_json"] or "[]")]
                if spec_row is not None
                else []
            )
            if not block_pks:
                return jsonify(
                    {
                        "book_pk": book_pk,
                        "book_title": _clean_book_title_for_citation(
                            str(book_row["title"]), author=book_row["author"]
                        ),
                        "author": book_row["author"],
                        "year": book_row["year"],
                        "discipline": disc_slug,
                        "discipline_label": label_for_discipline(disc_slug),
                        "coverage_pct": 0.0,
                        "share_pct": 0.0,
                        "count": 0,
                        "passages": [],
                    }
                )

            blocks_by_pk: dict[int, Any] = {}
            units_by_pk: dict[int, tuple[str, str]] = {}
            for i in range(0, len(block_pks), 500):
                chunk = block_pks[i : i + 500]
                ph = ",".join("?" for _ in chunk)
                b_rows = cconn.execute(
                    f"""
                    SELECT
                        bl.block_pk, bl.page_start, bl.page_end, bl.printed_page,
                        bl.section_title, bl.content, bl.char_count,
                        bm.places_json, bm.emergent_topics_json
                    FROM blocks bl
                    LEFT JOIN block_metadata_v22 bm ON bm.block_pk = bl.block_pk
                    WHERE bl.block_pk IN ({ph}) AND bl.is_active = 1 AND bl.block_role = 'body'
                    """,
                    tuple(chunk),
                ).fetchall()
                for r in b_rows:
                    if not is_residual_paratext_block(str(r["section_title"] or ""), str(r["content"] or "")):
                        blocks_by_pk[int(r["block_pk"])] = r

                u_rows = cconn.execute(
                    f"""
                    SELECT block_pk, stmt, verbatim_quote
                    FROM epistemic_units
                    WHERE block_pk IN ({ph})
                    ORDER BY unit_pk ASC
                    """,
                    tuple(chunk),
                ).fetchall()
                for ur in u_rows:
                    bpk = int(ur["block_pk"])
                    if bpk not in units_by_pk:
                        units_by_pk[bpk] = (str(ur["stmt"] or ""), str(ur["verbatim_quote"] or ""))

            ordered_blocks = sorted(
                blocks_by_pk.values(),
                key=lambda r: (int(r["page_start"] or 0), int(r["block_pk"])),
            )
            passages: list[dict[str, Any]] = []
            for r in ordered_blocks:
                bpk = int(r["block_pk"])
                stmt, vquote = units_by_pk.get(bpk, ("", ""))
                passages.append(
                    {
                        "block_pk": bpk,
                        "page_start": r["page_start"],
                        "printed_page": r["printed_page"],
                        "section_title": str(r["section_title"] or "").strip(),
                        "excerpt": _clean_excerpt(str(r["content"] or ""), vquote),
                        "quote": vquote,
                        "stmt": stmt,
                        "places": _parse_json_list(r["places_json"]),
                        "topics": _parse_json_list(r["emergent_topics_json"]),
                        "char_count": int(r["char_count"] or 0),
                    }
                )

            return jsonify(
                {
                    "book_pk": book_pk,
                    "book_title": _clean_book_title_for_citation(
                        str(book_row["title"]), author=book_row["author"]
                    ),
                    "author": book_row["author"],
                    "year": book_row["year"],
                    "discipline": disc_slug,
                    "discipline_label": label_for_discipline(disc_slug),
                    "coverage_pct": round(float(spec_row["coverage_pct"]), 1),
                    "share_pct": round(float(spec_row["share_pct"]), 1),
                    "count": len(passages),
                    "passages": passages,
                }
            )
        finally:
            cconn.close()

    @app.get("/api/atlas/reconstruct/<path:discipline>")
    def api_atlas_reconstruct(discipline: str):
        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        min_cov = request.args.get("min_coverage_pct", default=0.5, type=float)
        min_blocks = request.args.get("min_book_blocks", default=2, type=int)
        try:
            report = reconstruct_discipline(
                cconn,
                discipline,
                min_book_blocks=min_blocks,
                min_coverage_pct=min_cov,
                limit_books=None,
                limit_passages_per_book=None,
            )
            payload = report.to_dict()
            for book_item in payload.get("books", []):
                book_item["clean_title"] = _clean_book_title_for_citation(
                    book_item.get("book_title", ""),
                    author=book_item.get("author"),
                )
                for p in book_item.get("passages", []):
                    p["clean_book_title"] = book_item["clean_title"]
            return jsonify(payload)
        except ValueError as exc:
            abort(400, description=str(exc))
        except RuntimeError as exc:
            abort(503, description=str(exc))
        finally:
            cconn.close()

    @app.get("/api/atlas/decompress")
    def api_atlas_decompress():
        concept_q = str(request.args.get("q") or "").strip()
        if not concept_q:
            abort(400, description="Parametro q obbligatorio")
        mode_raw = str(request.args.get("mode") or "").strip()
        only_disputes = str(request.args.get("only_disputes") or "0").lower() in {"1", "true", "yes"}

        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            report = decompress_concept(
                cconn,
                concept_q,
                modes=[mode_raw] if mode_raw else None,
                only_disputes=only_disputes,
                max_fts_blocks=800,
            )
            payload = report.to_dict()
            for ent in payload.get("timeline", []):
                ent["clean_book_title"] = _clean_book_title_for_citation(
                    ent.get("book_title", ""),
                    author=ent.get("author"),
                )
            for disp in payload.get("disputes", []):
                disp["clean_book_title"] = _clean_book_title_for_citation(
                    disp.get("book_title", ""),
                )
            for group in payload.get("by_mode", {}).values():
                for ent in group:
                    ent["clean_book_title"] = _clean_book_title_for_citation(
                        ent.get("book_title", ""),
                        author=ent.get("author"),
                    )
            return jsonify(payload)
        except ValueError as exc:
            abort(400, description=str(exc))
        finally:
            cconn.close()

    # ------------------------------------------------------------------
    # Existing SecAI Curriculum & Study APIs (contracts preserved 100%)
    # ------------------------------------------------------------------
    @app.get("/api/overview")
    def api_overview():
        with _state_conn() as sconn:
            snap = get_student_snapshot(sconn)
        mastered_set = set(snap["mastered_ids"])
        failed_set = set(snap["failed_ids"])
        frontier = compute_frontier_nodes(dag_payload, mastered_set, failed_set)
        card_ids = list_available_card_ids(app.config["CARDS_DIR"])

        topo_nodes = []
        for nid in dag_payload["metadata"]["topological_order"]:
            node = dict(dag_payload["nodes"][nid])
            prog = snap["progress_by_node"].get(nid)
            node["student_status"] = prog["status"] if prog else "not_started"
            node["has_card"] = nid in card_ids
            topo_nodes.append(node)

        ofa_gate = dag_payload["nodes"]["G00"]
        ofa_reqs = ofa_gate["prerequisites"]
        ofa_ready_count = sum(1 for r in ofa_reqs if r in mastered_set)

        return jsonify(
            {
                "metadata": dag_payload["metadata"],
                "hero_profile": dag_payload["hero_profile"],
                "nodes": topo_nodes,
                "frontier_nodes": frontier,
                "mastered_ids": snap["mastered_ids"],
                "failed_ids": snap["failed_ids"],
                "hero_artifacts": snap["hero_artifacts"],
                "ofa_readiness": {
                    "gate_id": "G00",
                    "required_units": ofa_reqs,
                    "ready_count": ofa_ready_count,
                    "total_count": len(ofa_reqs),
                    "deadline": ofa_gate.get("window", ""),
                },
                "open_access_registry": oa_registry,
            }
        )

    @app.get("/api/node/<path:node_id>")
    def api_node(node_id: str):
        nodes = dag_payload["nodes"]
        if node_id not in nodes:
            abort(404, description=f"Nodo curricolare sconosciuto: {node_id}")

        node = dict(nodes[node_id])
        card = load_card(node_id, app.config["CARDS_DIR"])

        bridges: list[dict[str, Any]] = []
        cconn = _corpus_ro_conn()
        if cconn is not None:
            try:
                bridges = get_bridges_for_node(cconn, node_id, only_validated=True, prefix_fallback=False)
            finally:
                cconn.close()

        seed_param = request.args.get("seed", type=int)
        drills = generate_drill_set(
            node_id=node_id,
            drill_key=node.get("drill_key"),
            count=5,
            seed=seed_param,
        )

        with _state_conn() as sconn:
            snap = get_student_snapshot(sconn)
        prog = snap["progress_by_node"].get(
            node_id,
            {
                "node_id": node_id,
                "status": "not_started",
                "card_governance": card["status"] if card else "validata_auto",
                "correct_count": 0,
                "attempt_count": 0,
                "distinct_pass_days": 0,
            },
        )

        open_access_books = [
            oa_by_id[oid] for oid in node.get("open_access_ids", []) if oid in oa_by_id
        ]

        return jsonify(
            {
                "node": node,
                "hero_compass": node["hero_compass"],
                "progress": prog,
                "card": card,
                "wrong_book_bridges": bridges,
                "drills": drills,
                "open_access_books": open_access_books,
            }
        )

    @app.post("/api/drill/submit")
    def api_drill_submit():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "").strip()
        drill_id = str(data.get("drill_id") or f"{node_id}#q1").strip()
        expected = str(data.get("expected") or "").strip()
        student_answer = str(data.get("student_answer") or "").strip()
        attempt_day = data.get("attempt_day")

        if node_id not in dag_payload["nodes"] or not expected:
            abort(400, description="Parametri node_id ed expected obbligatori")

        grade = grade_drill_answer(expected=expected, student_answer=student_answer)
        with _state_conn() as sconn:
            updated_prog = record_drill_attempt(
                sconn,
                node_id=node_id,
                drill_id=drill_id,
                student_answer=student_answer,
                expected_answer=expected,
                is_correct=grade["is_correct"],
                attempt_day=str(attempt_day) if attempt_day else None,
            )
            snap = get_student_snapshot(sconn)

        frontier = compute_frontier_nodes(
            dag_payload,
            set(snap["mastered_ids"]),
            set(snap["failed_ids"]),
        )
        return jsonify(
            {
                "grade": grade,
                "progress": updated_prog,
                "frontier_nodes": frontier,
                "mastered_ids": snap["mastered_ids"],
            }
        )

    @app.post("/api/hero/graph-check")
    def api_hero_graph_check():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "P0.6").strip()
        spec_id = str(data.get("spec_id") or "abs_shifted_log").strip()
        answers = data.get("answers") or {}
        try:
            res = verify_graph_invariants(spec_id, answers)
        except ValueError as exc:
            abort(400, description=str(exc))

        with _state_conn() as sconn:
            record_hero_artifact(
                sconn,
                node_id=node_id,
                proof_family="graph_invariants",
                payload={"spec_id": spec_id, "answers": answers, "passed_count": res["passed_count"]},
                passed=res["all_passed"],
            )
        return jsonify(res)

    @app.post("/api/hero/proof-check")
    def api_hero_proof_check():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "P0.4").strip()
        rubric_id = str(data.get("rubric_id") or "sqrt2_irrational").strip()
        proof_text = str(data.get("proof_text") or "")
        try:
            res = evaluate_proof_rubric(rubric_id, proof_text)
        except ValueError as exc:
            abort(400, description=str(exc))

        with _state_conn() as sconn:
            record_hero_artifact(
                sconn,
                node_id=node_id,
                proof_family="rubric_proof",
                payload={"rubric_id": rubric_id, "passed_count": res["passed_count"]},
                passed=res["all_passed"],
            )
        return jsonify(res)

    @app.post("/api/card/flag")
    def api_card_flag():
        data = request.get_json(force=True, silent=True) or {}
        node_id = str(data.get("node_id") or "").strip()
        note = str(data.get("note") or "").strip()
        if not node_id or not note:
            abort(400, description="node_id e note sono obbligatori")
        with _state_conn() as sconn:
            res = flag_card_issue(sconn, node_id=node_id, note=note)
        return jsonify(res)

    @app.get("/api/block/<int:block_pk>")
    def api_block(block_pk: int):
        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            row = cconn.execute(
                """
                SELECT
                    bl.block_pk,
                    bl.block_uid,
                    bl.book_pk,
                    bl.book_title,
                    bl.is_active,
                    bl.superseded_by_pk,
                    bl.block_role,
                    bl.page_start,
                    bl.page_end,
                    bl.printed_page,
                    bl.section_title,
                    bl.content,
                    bl.char_count,
                    bl.source_origin,
                    bk.author,
                    bk.year,
                    bk.surface_domain,
                    bk.source_kind
                FROM blocks bl
                JOIN books bk ON bk.book_pk = bl.book_pk
                WHERE bl.block_pk = ?
                """,
                (block_pk,),
            ).fetchone()
            if row is None:
                abort(404, description=f"Blocco {block_pk} non trovato in pack_corpus.db")

            prev_row = cconn.execute(
                """
                SELECT block_pk FROM blocks
                WHERE book_pk = ? AND is_active = 1 AND block_pk < ?
                ORDER BY block_pk DESC LIMIT 1
                """,
                (row["book_pk"], block_pk),
            ).fetchone()
            next_row = cconn.execute(
                """
                SELECT block_pk FROM blocks
                WHERE book_pk = ? AND is_active = 1 AND block_pk > ?
                ORDER BY block_pk ASC LIMIT 1
                """,
                (row["book_pk"], block_pk),
            ).fetchone()

            quote = request.args.get("quote", "")
            highlighted_html, quote_matched = highlight_verbatim_quote(str(row["content"]), quote)

            fig_assets = find_corpus_figures_for_blocks(cconn, [block_pk], max_figures=4)
            figures_root_resolved = DEFAULT_FIGURES_DIR.resolve()
            figures_payload: list[dict[str, Any]] = []
            for fig in fig_assets:
                try:
                    rel_url = fig.path.relative_to(figures_root_resolved).as_posix()
                except ValueError:
                    rel_url = fig.path.name
                figures_payload.append(
                    {
                        "url": f"/corpus-figures/{rel_url}",
                        "page": fig.page,
                        "book_title": _clean_book_title_for_citation(
                            str(row["book_title"]), author=row["author"]
                        ),
                    }
                )

            disciplines_payload: list[dict[str, str]] = []
            has_v22 = (
                cconn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='block_metadata_v22'"
                ).fetchone()
                is not None
            )
            if has_v22:
                bm_row = cconn.execute(
                    "SELECT macro_disciplines_json FROM block_metadata_v22 WHERE block_pk = ?",
                    (block_pk,),
                ).fetchone()
                if bm_row:
                    for d_slug in _parse_json_list(bm_row["macro_disciplines_json"]):
                        disciplines_payload.append(
                            {"slug": d_slug, "label_it": label_for_discipline(d_slug)}
                        )

            clean_title = _clean_book_title_for_citation(
                str(row["book_title"]), author=row["author"]
            )

            return jsonify(
                {
                    "block_pk": int(row["block_pk"]),
                    "block_uid": row["block_uid"],
                    "book_pk": int(row["book_pk"]),
                    "book_title": row["book_title"],
                    "clean_book_title": clean_title,
                    "author": row["author"],
                    "year": row["year"],
                    "surface_domain": row["surface_domain"],
                    "source_kind": row["source_kind"],
                    "source_origin": row["source_origin"],
                    "block_role": row["block_role"],
                    "page_start": row["page_start"],
                    "page_end": row["page_end"],
                    "printed_page": row["printed_page"],
                    "section_title": row["section_title"],
                    "is_active": bool(row["is_active"]),
                    "superseded_by_pk": row["superseded_by_pk"],
                    "char_count": int(row["char_count"]),
                    "content": row["content"],
                    "highlighted_html": highlighted_html,
                    "quote_matched": quote_matched,
                    "prev_block_pk": int(prev_row["block_pk"]) if prev_row else None,
                    "next_block_pk": int(next_row["block_pk"]) if next_row else None,
                    "figures": figures_payload,
                    "disciplines": disciplines_payload,
                }
            )
        finally:
            cconn.close()

    @app.get("/api/search")
    def api_search():
        raw_q = request.args.get("q", "")
        limit = min(max(request.args.get("limit", default=25, type=int), 1), 100)
        fts_q = sanitize_fts5_query(raw_q)
        if not fts_q:
            return jsonify({"query": raw_q, "sanitized_query": "", "results": []})

        cconn = _corpus_ro_conn()
        if cconn is None:
            abort(503, description="Database pack_corpus.db non disponibile")
        try:
            rows = cconn.execute(
                """
                SELECT
                    bl.block_pk,
                    bl.block_uid,
                    bl.book_pk,
                    bl.book_title,
                    bk.author,
                    bk.year,
                    bk.surface_domain,
                    bl.page_start,
                    bl.printed_page,
                    bl.section_title,
                    snippet(passages_fts, 2, '__PACK_MARK_OPEN__', '__PACK_MARK_CLOSE__', ' … ', 32) AS snippet_html,
                    bm25(passages_fts, 2.0, 1.5, 1.0) AS score
                FROM passages_fts
                JOIN blocks bl ON bl.block_pk = passages_fts.rowid
                JOIN books bk ON bk.book_pk = bl.book_pk
                WHERE passages_fts MATCH ?
                  AND bl.is_active = 1
                ORDER BY score
                LIMIT ?
                """,
                (fts_q, limit),
            ).fetchall()
            results: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                raw_snip = str(d.get("snippet_html", "") or "")
                escaped_snip = html.escape(raw_snip, quote=True)
                d["snippet_html"] = escaped_snip.replace(
                    "__PACK_MARK_OPEN__", "<mark>"
                ).replace("__PACK_MARK_CLOSE__", "</mark>")
                d["clean_book_title"] = _clean_book_title_for_citation(
                    str(d.get("book_title", "")), author=d.get("author")
                )
                results.append(d)
            return jsonify({"query": raw_q, "sanitized_query": fts_q, "count": len(results), "results": results})
        finally:
            cconn.close()

    @app.get("/api/extraction_status")
    def api_extraction_status():
        payload: dict[str, Any] = {
            "books_active": 0,
            "blocks_active": 0,
            "blocks_extracted": 0,
            "epistemic_units": 0,
            "structural_signatures": 0,
            "validated_bridges": 0,
            "state": "idle",
            "live_wave": None,
        }
        cconn = _corpus_ro_conn()
        if cconn is not None:
            try:
                payload["books_active"] = int(
                    cconn.execute("SELECT COUNT(*) FROM books WHERE is_active = 1").fetchone()[0]
                )
                payload["blocks_active"] = int(
                    cconn.execute(
                        "SELECT COUNT(*) FROM blocks WHERE is_active = 1 AND block_role != 'paratext'"
                    ).fetchone()[0]
                )
                has_log = (
                    cconn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='block_extraction_log'"
                    ).fetchone()
                    is not None
                )
                if has_log:
                    payload["blocks_extracted"] = int(
                        cconn.execute("SELECT COUNT(*) FROM block_extraction_log").fetchone()[0]
                    )
                else:
                    payload["blocks_extracted"] = int(
                        cconn.execute("SELECT COUNT(DISTINCT block_pk) FROM epistemic_units").fetchone()[0]
                    )
                payload["epistemic_units"] = int(
                    cconn.execute("SELECT COUNT(*) FROM epistemic_units").fetchone()[0]
                )
                payload["structural_signatures"] = int(
                    cconn.execute("SELECT COUNT(*) FROM structural_signatures").fetchone()[0]
                )
                payload["validated_bridges"] = int(
                    cconn.execute(
                        "SELECT COUNT(*) FROM curiosity_bridges WHERE status = 'validated'"
                    ).fetchone()[0]
                )
            finally:
                cconn.close()

        st_path: Path = app.config["STATUS_FILE_PATH"]
        if st_path.exists():
            try:
                live = json.loads(st_path.read_text(encoding="utf-8"))
                payload["live_wave"] = live
                if isinstance(live, dict) and live.get("state"):
                    payload["state"] = str(live["state"])
            except (OSError, json.JSONDecodeError):
                pass
        return jsonify(payload)

    return app


def sqlite3_row_factory():
    import sqlite3

    return sqlite3.Row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avvia il Server Editoriale SecAI di resuscipack")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
