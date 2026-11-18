"""Sottosistema epistemico di `resuscipack` (ADR-0002):
- Vocabolario chiuso di 24 `OpTag` universali (`op_tags.py`)
- Schema polimorfico `BlockExtraction v2.1` a zero leakage e anti-template (`schema_v21.py`)
- Validatore deterministico a 6 Gate per le schede studio (`verifica_citazioni.py`)
- Motore "Il Libro Sbagliato" e seed dei 3 ponti empirici verificati (`bridge.py`)
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
    "GeneratorArchetype",
    "MacroDiscipline",
    "OP_TAG_DESCRIPTIONS",
    "OpTag",
    "SCHEMA_VERSION",
    "SCHEMA_VERSION_V22",
    "SchemaValidationError",
    "StructuralSignature",
    "UnitKind",
    "UnitMode",
    "ValidationReport",
    "WrongBookCandidate",
    "discover_and_validate_bridges",
    "find_wrong_book_candidates",
    "get_bridges_for_node",
    "normalizza",
    "normalizza_testo",
    "persist_block_extraction",
    "persist_v22_metadata_only",
    "quote_matches_block_ocr_tolerant",
    "seed_verified_empirical_bridges",
    "validate_and_upsert_bridge",
    "validate_batch_anti_template",
    "validate_block_extraction",
    "validate_v22_metadata_only",
    "validate_op_tags",
    "verifica_scheda",
    "verifica_scheda_report",
]
