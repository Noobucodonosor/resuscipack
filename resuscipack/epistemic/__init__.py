"""Sottosistema epistemico di `resuscipack` (ADR-0002):
- Vocabolario chiuso di 24 `OpTag` universali (`op_tags.py`)
- Schema polimorfico `BlockExtraction v2.1` a zero leakage e anti-template (`schema_v21.py`)
- Validatore deterministico a 6 Gate per le schede studio (`verifica_citazioni.py`)
- Motore "Il Libro Sbagliato" e seed dei 3 ponti empirici verificati (`bridge.py`)
- CLI batch idempotente fail-honest per Wave 1..4 (`batch_cli.py`)
"""

from .bridge import (
    GeneratorArchetype,
    WrongBookCandidate,
    find_wrong_book_candidates,
    get_bridges_for_node,
    seed_verified_empirical_bridges,
    validate_and_upsert_bridge,
)
from .op_tags import ALL_OP_TAGS, OP_TAG_DESCRIPTIONS, OpTag, validate_op_tags
from .schema_v21 import (
    SCHEMA_VERSION,
    AntiSudokuRole,
    AtomicEpistemicUnit,
    BlockExtractionV21,
    BlockYield,
    SchemaValidationError,
    StructuralSignature,
    UnitKind,
    UnitMode,
    normalizza_testo,
    persist_block_extraction,
    validate_batch_anti_template,
    validate_block_extraction,
)
from .verifica_citazioni import (
    ValidationReport,
    normalizza,
    verifica_scheda,
    verifica_scheda_report,
)

__all__ = [
    "ALL_OP_TAGS",
    "AntiSudokuRole",
    "AtomicEpistemicUnit",
    "BlockExtractionV21",
    "BlockYield",
    "GeneratorArchetype",
    "OP_TAG_DESCRIPTIONS",
    "OpTag",
    "SCHEMA_VERSION",
    "SchemaValidationError",
    "StructuralSignature",
    "UnitKind",
    "UnitMode",
    "ValidationReport",
    "WrongBookCandidate",
    "find_wrong_book_candidates",
    "get_bridges_for_node",
    "normalizza",
    "normalizza_testo",
    "persist_block_extraction",
    "seed_verified_empirical_bridges",
    "validate_and_upsert_bridge",
    "validate_batch_anti_template",
    "validate_block_extraction",
    "validate_op_tags",
    "verifica_scheda",
    "verifica_scheda_report",
]
