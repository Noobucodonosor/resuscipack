"""Sottosistema editoriale dei *Nuovi Libri* Continui di `resuscipack` (ADR-0004, TASK-BOOK-01):
- Risolutore figure reali Baidu OCR + generatori SVG matematici controllati (`svg_diagrams.py`)
- Audit deterministico + Revisore critico avversario separato (`critique.py`)
- Dossier di contezza simultanea e compilatore di capitoli continui a 3 colori (`author_engine.py`)
"""

from .author_engine import (
    CHAPTER_DRAFT_RESPONSE_SCHEMA,
    DEFAULT_BOOKS_DIR,
    PILOT_CHAPTER_SPEC,
    ChapterDossier,
    ChapterSpec,
    CompiledChapterResult,
    VerifiedQuoteCandidate,
    assemble_chapter_dossier,
    build_author_chapter_prompt,
    compile_chapter_markdown,
    extract_verified_quote_span,
    generate_and_verify_chapter,
    is_clean_editorial_quote,
)
from .critique import (
    ADVERSARIAL_CRITIQUE_RESPONSE_SCHEMA,
    CritiqueIssue,
    CritiqueReport,
    JsonLlmCallable,
    audit_and_critique_chapter,
    build_adversarial_critique_prompt,
    call_editorial_json_llm,
    run_adversarial_llm_critique,
    run_deterministic_chapter_audit,
)
from .svg_diagrams import (
    CONTROLLED_SVG_IDS,
    DEFAULT_ASSETS_DIR,
    DEFAULT_FIGURES_DIR,
    FigureAsset,
    find_corpus_figures_for_blocks,
    generate_controlled_svg,
    save_svg_diagram,
)

__all__ = [
    "ADVERSARIAL_CRITIQUE_RESPONSE_SCHEMA",
    "CHAPTER_DRAFT_RESPONSE_SCHEMA",
    "CONTROLLED_SVG_IDS",
    "ChapterDossier",
    "ChapterSpec",
    "CompiledChapterResult",
    "CritiqueIssue",
    "CritiqueReport",
    "DEFAULT_ASSETS_DIR",
    "DEFAULT_BOOKS_DIR",
    "DEFAULT_FIGURES_DIR",
    "FigureAsset",
    "JsonLlmCallable",
    "PILOT_CHAPTER_SPEC",
    "VerifiedQuoteCandidate",
    "assemble_chapter_dossier",
    "audit_and_critique_chapter",
    "build_adversarial_critique_prompt",
    "build_author_chapter_prompt",
    "call_editorial_json_llm",
    "compile_chapter_markdown",
    "extract_verified_quote_span",
    "find_corpus_figures_for_blocks",
    "generate_and_verify_chapter",
    "generate_controlled_svg",
    "is_clean_editorial_quote",
    "run_adversarial_llm_critique",
    "run_deterministic_chapter_audit",
    "save_svg_diagram",
]
