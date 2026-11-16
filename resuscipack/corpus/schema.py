"""Schema relazionale canonico append-only per `/Users/dany/resuscipack/data/pack_corpus.db`
con indice full-text `passages_fts` (`content='blocks'`, `content_rowid='block_pk'`) e trigger SQL."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pack_corpus.db"

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    book_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    book_uid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    year INTEGER,
    surface_domain TEXT NOT NULL,
    language TEXT,
    source_kind TEXT NOT NULL,
    source_path TEXT,
    page_count INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS blocks (
    block_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    block_uid TEXT UNIQUE NOT NULL,
    book_pk INTEGER NOT NULL REFERENCES books(book_pk),
    book_title TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    superseded_by_pk INTEGER REFERENCES blocks(block_pk),
    block_role TEXT NOT NULL DEFAULT 'body',
    page_start INTEGER,
    page_end INTEGER,
    printed_page TEXT,
    section_title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    norm_content TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    est_tokens INTEGER NOT NULL,
    source_origin TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    book_title,
    section_title,
    content,
    content='blocks',
    content_rowid='block_pk',
    tokenize='unicode61'
);

-- Immutabilità fisica: nessun blocco emesso può essere cancellato (evita riciclo o buchi distruttivi)
CREATE TRIGGER IF NOT EXISTS trg_blocks_forbid_delete
BEFORE DELETE ON blocks
BEGIN
    SELECT RAISE(ABORT, 'blocks table is append-only: set is_active=0 and superseded_by_pk instead of DELETE');
END;

-- Sincronizzazione automatica FTS5 su INSERT
CREATE TRIGGER IF NOT EXISTS trg_blocks_ai
AFTER INSERT ON blocks
WHEN NEW.is_active = 1
BEGIN
    INSERT INTO passages_fts(rowid, book_title, section_title, content)
    VALUES (NEW.block_pk, NEW.book_title, COALESCE(NEW.section_title, ''), NEW.content);
END;

-- Sincronizzazione automatica FTS5 su UPDATE (es. superseding is_active 1 -> 0)
CREATE TRIGGER IF NOT EXISTS trg_blocks_au_deactivate
AFTER UPDATE ON blocks
WHEN OLD.is_active = 1 AND NEW.is_active = 0
BEGIN
    INSERT INTO passages_fts(passages_fts, rowid, book_title, section_title, content)
    VALUES ('delete', OLD.block_pk, OLD.book_title, COALESCE(OLD.section_title, ''), OLD.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_blocks_au_reactivate
AFTER UPDATE ON blocks
WHEN OLD.is_active = 0 AND NEW.is_active = 1
BEGIN
    INSERT INTO passages_fts(rowid, book_title, section_title, content)
    VALUES (NEW.block_pk, NEW.book_title, COALESCE(NEW.section_title, ''), NEW.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_blocks_au_modify
AFTER UPDATE OF book_title, section_title, content ON blocks
WHEN OLD.is_active = 1 AND NEW.is_active = 1
BEGIN
    INSERT INTO passages_fts(passages_fts, rowid, book_title, section_title, content)
    VALUES ('delete', OLD.block_pk, OLD.book_title, COALESCE(OLD.section_title, ''), OLD.content);
    INSERT INTO passages_fts(rowid, book_title, section_title, content)
    VALUES (NEW.block_pk, NEW.book_title, COALESCE(NEW.section_title, ''), NEW.content);
END;

CREATE TABLE IF NOT EXISTS epistemic_units (
    unit_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_uid TEXT UNIQUE NOT NULL,
    block_pk INTEGER NOT NULL REFERENCES blocks(block_pk),
    kind TEXT NOT NULL,
    mode TEXT NOT NULL,
    stmt TEXT NOT NULL,
    verbatim_quote TEXT NOT NULL,
    actors_json TEXT,
    vs_dispute TEXT,
    concepts_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS structural_signatures (
    sig_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    block_pk INTEGER UNIQUE NOT NULL REFERENCES blocks(block_pk),
    mech TEXT NOT NULL,
    op_tags_json TEXT NOT NULL,
    anti_sudoku_role TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS curiosity_bridges (
    bridge_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    block_pk INTEGER NOT NULL REFERENCES blocks(block_pk),
    target_op_tags_json TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    chain_steps_json TEXT NOT NULL,
    score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'validated',
    UNIQUE(node_id, block_pk)
);

CREATE TABLE IF NOT EXISTS legacy_rowid_map (
    legacy_fts_rowid INTEGER PRIMARY KEY,
    block_pk INTEGER NOT NULL REFERENCES blocks(block_pk),
    block_uid TEXT NOT NULL,
    match_method TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS block_extraction_log (
    block_pk INTEGER PRIMARY KEY REFERENCES blocks(block_pk),
    block_uid TEXT NOT NULL,
    yield TEXT NOT NULL,
    provider_model TEXT NOT NULL,
    units_count INTEGER NOT NULL,
    has_sig INTEGER NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_books_domain_active ON books(surface_domain, is_active);
CREATE INDEX IF NOT EXISTS idx_blocks_book_seq ON blocks(book_pk, page_start, block_pk);
CREATE INDEX IF NOT EXISTS idx_blocks_active_role ON blocks(is_active, block_role);
CREATE INDEX IF NOT EXISTS idx_epistemic_units_block ON epistemic_units(block_pk);
CREATE INDEX IF NOT EXISTS idx_curiosity_bridges_node ON curiosity_bridges(node_id, status);
CREATE INDEX IF NOT EXISTS idx_extraction_log_yield ON block_extraction_log(yield);
"""


def connect_corpus_db(db_path: Path | str = DEFAULT_DB_PATH, read_only: bool = False) -> sqlite3.Connection:
    """Apre una connessione SQLite a `pack_corpus.db` (in URI `mode=ro` quando `read_only=True`)."""
    path = Path(db_path).resolve()
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_corpus_db(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Inizializza idempotentemente lo schema completo di `pack_corpus.db`."""
    conn = connect_corpus_db(db_path=db_path, read_only=False)
    conn.executescript(SCHEMA_DDL)
    conn.execute(
        """
        INSERT OR IGNORE INTO block_extraction_log (
            block_pk, block_uid, yield, provider_model, units_count, has_sig, processed_at
        )
        SELECT
            bl.block_pk,
            bl.block_uid,
            'high',
            'legacy-seed',
            COUNT(eu.unit_pk),
            CASE WHEN EXISTS (
                SELECT 1 FROM structural_signatures ss WHERE ss.block_pk = bl.block_pk
            ) THEN 1 ELSE 0 END,
            COALESCE(MIN(eu.created_at), datetime('now'))
        FROM blocks bl
        JOIN epistemic_units eu ON eu.block_pk = bl.block_pk
        GROUP BY bl.block_pk, bl.block_uid
        """
    )
    conn.commit()
    return conn


def supersede_block(conn: sqlite3.Connection, old_block_pk: int, new_block_pk: int) -> None:
    """Disattiva un blocco sostituito da OCR superiore mantenendo intatto il suo `block_pk` storico."""
    if old_block_pk == new_block_pk:
        raise ValueError("old_block_pk and new_block_pk must differ")
    conn.execute(
        "UPDATE blocks SET is_active = 0, superseded_by_pk = ? WHERE block_pk = ?",
        (new_block_pk, old_block_pk),
    )
