#!/usr/bin/env python3
"""Esporta la Vista Libro di resuscipack in un sito 100% statico (GitHub Pages, €0).

Compila i 20 capitoli di Volume I e Volume II, i 20 diagrammi SVG, i 30 quesiti OFA
e l'indice di ricerca client-side senza dipendere dal database locale `pack_corpus.db`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from resuscipack.books.author_engine import DEFAULT_BOOKS_DIR
from resuscipack.books.svg_diagrams import DEFAULT_ASSETS_DIR
from resuscipack.curriculum.drills_sympy import PROOF_RUBRICS
from resuscipack.workbench.books_view import (
    list_volumes_and_chapters,
    load_book_chapter,
    load_ofa_30_questions,
)

TEMPLATES_DIR = REPO_ROOT / "resuscipack" / "workbench" / "templates"
STATIC_DIR = REPO_ROOT / "resuscipack" / "workbench" / "static"
PUBLIC_ASSETS_DIR = REPO_ROOT / "public" / "assets"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw_html: str) -> str:
    return " ".join(_TAG_RE.sub(" ", raw_html or "").split())


def _rewrite_static_html(rendered: str) -> str:
    """Adatta i path di reader.html alla pubblicazione statica sotto sottopercorso."""
    out = rendered
    out = out.replace(
        "<body ",
        '<body data-static-mode="true" ',
        1,
    )
    out = out.replace('href="/assets/', 'href="./assets/')
    out = out.replace('src="/assets/', 'src="./assets/')
    out = out.replace('href="/static/', 'href="./static/')
    out = out.replace('src="/static/', 'src="./static/')
    out = out.replace('href="/libro"', 'href="./"')
    out = out.replace(
        '<a class="nav__logo" href="/">',
        '<a class="nav__logo" href="./">',
    )
    out = out.replace(
        '<div class="nav__item"><a class="nav__link" href="/">Home</a></div>',
        '<div class="nav__item"><a class="nav__link" href="https://noobucodonosor-hub-664856461640.us-central1.run.app/?app=resuscipack">Hub AI</a></div>',
    )
    out = out.replace(
        '<div class="nav__item"><a class="nav__link" href="/atlante">Atlante</a></div>',
        '<div class="nav__item"><a class="nav__link" href="https://github.com/Noobucodonosor/resuscipack">GitHub</a></div>',
    )
    out = out.replace(
        '<a class="link" href="/atlante">Vai all\'atlante</a>',
        '<a class="link" href="https://noobucodonosor-hub-664856461640.us-central1.run.app/?app=resuscipack">Apri Playground AI</a>',
    )
    out = out.replace(
        '<a class="btn btn--primary" href="./">Apri i libri</a>',
        '<a class="btn btn--primary" href="https://noobucodonosor-hub-664856461640.us-central1.run.app/?app=resuscipack">Chiedi all\'AI</a>',
    )
    return out


def export_static_book(out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copia asset statici
    shutil.copytree(PUBLIC_ASSETS_DIR, out_dir / "assets")
    shutil.copytree(STATIC_DIR, out_dir / "static")
    shutil.copytree(DEFAULT_ASSETS_DIR, out_dir / "books-assets")

    # 2. Esporta catalogo, 20 capitoli e 30 quesiti OFA
    data_dir = out_dir / "data"
    chapters_dir = data_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    catalog = list_volumes_and_chapters(DEFAULT_BOOKS_DIR)
    (data_dir / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ofa_data = load_ofa_30_questions(DEFAULT_BOOKS_DIR)
    (data_dir / "ofa-questions.json").write_text(
        json.dumps(ofa_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    search_entries: list[dict[str, Any]] = []
    exported_chapters = 0

    for vol in catalog.get("volumes", []):
        vid = vol["volume_id"]
        vol_out = chapters_dir / vid
        vol_out.mkdir(parents=True, exist_ok=True)

        for ch_meta in vol.get("chapters", []):
            slug = ch_meta["slug"]
            chapter = load_book_chapter(vid, slug, books_dir=DEFAULT_BOOKS_DIR)
            if not chapter:
                continue

            # Path relativi per i diagrammi SVG
            chapter["html"] = str(chapter.get("html") or "").replace(
                'src="/books-assets/',
                'src="./books-assets/',
            )

            # Includi i criteri della rubrica dimostrativa per verifica client-side
            pr = chapter.get("proof_rubric")
            if isinstance(pr, dict) and pr.get("id") in PROOF_RUBRICS:
                pr["lemmas"] = [
                    {
                        "label": lem.get("label", ""),
                        "keywords": list(lem.get("keywords", [])),
                        "missing_hint": lem.get("missing_hint", ""),
                    }
                    for lem in PROOF_RUBRICS[pr["id"]]
                ]

            (vol_out / f"{slug}.json").write_text(
                json.dumps(chapter, ensure_ascii=False),
                encoding="utf-8",
            )
            exported_chapters += 1

            plain_text = _strip_html(chapter["html"])
            search_entries.append(
                {
                    "volume_id": vid,
                    "volume_short_title": chapter["volume_short_title"],
                    "chapter_number": chapter["chapter_number"],
                    "slug": slug,
                    "title": chapter["title"],
                    "subtitle": chapter.get("subtitle", ""),
                    "excerpt": plain_text[:2800],
                    "footnotes": [
                        {
                            "num": fn.get("num"),
                            "block_pk": fn.get("block_pk"),
                            "quote": fn.get("quote", ""),
                            "source_label": fn.get("source_label", ""),
                        }
                        for fn in chapter.get("footnotes", [])
                    ],
                }
            )

    (data_dir / "search-index.json").write_text(
        json.dumps({"chapters": search_entries}, ensure_ascii=False),
        encoding="utf-8",
    )

    # 3. Renderizza index.html dal template ufficiale reader.html
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("reader.html")
    rendered = template.render(
        initial_volume_id="vol1_ofa",
        initial_slug="dall_ovvio_al_numero",
    )
    static_html = _rewrite_static_html(rendered)
    (out_dir / "index.html").write_text(static_html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    return {
        "out_dir": str(out_dir),
        "volumes": len(catalog.get("volumes", [])),
        "chapters": exported_chapters,
        "ofa_questions": ofa_data.get("count", 0),
        "svg_assets": len(list((out_dir / "books-assets").glob("*.svg"))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Esporta la Vista Libro statica di resuscipack")
    parser.add_argument(
        "--out",
        default="_site",
        help="Directory di destinazione della build statica (default: _site)",
    )
    args = parser.parse_args()
    summary = export_static_book(Path(args.out))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
