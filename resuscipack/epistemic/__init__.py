"""Sottosistema epistemico di `resuscipack` (ADR-0002 & ADR-0004):
- Vocabolario chiuso di 24 `OpTag` universali (`op_tags.py`)
- Schema polimorfico `BlockExtraction v2.1`/`v2.2` a zero leakage e anti-template (`schema_v21.py`)
- Spettro Disciplinare Percentuale per Libro (`spectrum.py`)
- Ricostruzione delle Discipline dal Basso e Ponte "Il Libro Sbagliato" (`discipline_reconstructor.py`, `bridge.py`)
- Validatore deterministico a 6 Gate per le schede studio (`verifica_citazioni.py`)
- CLI batch idempotente fail-honest per Wave 1..4 (`batch_cli.py`)
"""

from .bridge import (
    DEFAULT_NODE_ARCHETYPES,
    GeneratorArchetype,
    WrongBookCandidate,
    discover_and_validate_bridges,
    find_wrong_book_candidates,
    get_bridges_for_node,
    seed_verified_empirical_bridges,
    validate_and_upsert_bridge,
)
from .discipline_reconstructor import (
    DISCIPLINE_NATIVE_SURFACE_DOMAINS,
    ReconstructedBookContribution,
    ReconstructedDisciplineReport,
    ReconstructedPassage,
    reconstruct_discipline,
)
from .op_tags import ALL_OP_TAGS, OP_TAG_DESCRIPTIONS, OpTag, validate_op_tags
from .schema_v21 import (
    ALL_MACRO_DISCIPLINES,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V22,
    AntiSudokuRole,
    AtomicEpistemicUnit,
    BlockExtractionV21,
    BlockYield,
    MacroDiscipline,
    SchemaValidationError,
    StructuralSignature,
    UnitKind,
    UnitMode,
    normalizza_testo,
    persist_block_extraction,
    persist_v22_metadata_only,
    quote_matches_block_ocr_tolerant,
    validate_batch_anti_template,
    validate_block_extraction,
    validate_v22_metadata_only,
)
from .spectrum import (
    DISCIPLINE_ALIASES,
    MACRO_DISCIPLINE_LABELS_IT,
    classify_book_quality_tier,
    compute_all_book_spectra,
    get_book_spectrum,
    is_residual_paratext_block,
    label_for_discipline,
    list_books_by_discipline,
    resolve_macro_discipline,
)
from .verifica_citazioni import (
    ValidationReport,
    normalizza,
    verifica_scheda,
    verifica_scheda_report,
)

__all__ = [
    "ALL_MACRO_DISCIPLINES",
    "ALL_OP_TAGS",
    "AntiSudokuRole",
    "AtomicEpistemicUnit",
    "BlockExtractionV21",
    "BlockYield",
    "DEFAULT_NODE_ARCHETYPES",
    "DISCIPLINE_ALIASES",
    "DISCIPLINE_NATIVE_SURFACE_DOMAINS",
    "GeneratorArchetype",
    "MACRO_DISCIPLINE_LABELS_IT",
    "MacroDiscipline",
    "OP_TAG_DESCRIPTIONS",
    "OpTag",
    "ReconstructedBookContribution",
    "ReconstructedDisciplineReport",
    "ReconstructedPassage",
    "SCHEMA_VERSION",
    "SCHEMA_VERSION_V22",
    "SchemaValidationError",
    "StructuralSignature",
    "UnitKind",
    "UnitMode",
    "ValidationReport",
    "WrongBookCandidate",
    "classify_book_quality_tier",
    "compute_all_book_spectra",
    "discover_and_validate_bridges",
    "find_wrong_book_candidates",
    "get_book_spectrum",
    "get_bridges_for_node",
    "is_residual_paratext_block",
    "label_for_discipline",
    "list_books_by_discipline",
    "normalizza",
    "normalizza_testo",
    "persist_block_extraction",
    "persist_v22_metadata_only",
    "quote_matches_block_ocr_tolerant",
    "reconstruct_discipline",
    "resolve_macro_discipline",
    "seed_verified_empirical_bridges",
    "validate_and_upsert_bridge",
    "validate_batch_anti_template",
    "validate_block_extraction",
    "validate_v22_metadata_only",
    "validate_op_tags",
    "verifica_scheda",
    "verifica_scheda_report",
]
