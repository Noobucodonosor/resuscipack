"""Sottosistema Corpus (`pack_corpus.db`): schema immutabile, normalizzatore,
ingestione Wave 0 e pianificatore OCR multi-ondata."""

from .normalizer import (
    classify_block_role,
    classify_surface_domain,
    clean_ocr_markdown,
    estimate_bpe_tokens,
    make_block_uid,
    make_book_uid,
    normalize_for_match,
)
from .ocr_manifest import build_ocr_wave_manifest
from .schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db, supersede_block
from .wave0_ingest import migrate_legacy_card_rowids, run_wave0_ingestion

__all__ = [
    "DEFAULT_DB_PATH",
    "build_ocr_wave_manifest",
    "classify_block_role",
    "classify_surface_domain",
    "clean_ocr_markdown",
    "connect_corpus_db",
    "estimate_bpe_tokens",
    "init_corpus_db",
    "make_block_uid",
    "make_book_uid",
    "migrate_legacy_card_rowids",
    "normalize_for_match",
    "run_wave0_ingestion",
    "supersede_block",
]
