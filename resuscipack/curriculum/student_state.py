"""Database SQLite separato (`data/student_state.db`) per i progressi dello studente,
la scansione Fast-Forward, la promozione In-Study delle schede e il Portfolio dell'Hero.

Mantiene `data/pack_corpus.db` rigorosamente immutabile e in sola lettura."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_STATE_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "student_state.db"

STATE_SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS node_progress (
    node_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'not_started',
    card_governance TEXT NOT NULL DEFAULT 'validata_auto',
    correct_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    distinct_pass_days INTEGER NOT NULL DEFAULT 0,
    last_attempt_day TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drill_attempts (
    attempt_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    drill_id TEXT NOT NULL,
    student_answer TEXT NOT NULL,
    expected_answer TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    attempt_day TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hero_artifacts (
    artifact_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    proof_family TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    passed INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_feedback (
    feedback_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    note TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def init_student_state_db(db_path: Path | str = DEFAULT_STATE_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(STATE_SCHEMA_DDL)
    conn.commit()
    return conn


def record_drill_attempt(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    drill_id: str,
    student_answer: str,
    expected_answer: str,
    is_correct: bool,
    attempt_day: str | None = None,
) -> dict[str, Any]:
    """Registra un tentativo di esercizio e ricalcola lo stato di padronanza del nodo:
    - `fast_forwarded` con >= 4 risposte giuste negli ultimi 5 tentativi (con >= 80% accuratezza);
    - `consolidated` quando confermato su >= 2 giorni distinti senza segnalazioni aperte sulla scheda;
    - `needs_study` quando ci sono errori ripetuti sul nodo.
    """
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    day = attempt_day or dt.date.today().isoformat()
    conn.execute(
        """
        INSERT INTO drill_attempts (
            node_id, drill_id, student_answer, expected_answer, is_correct, attempt_day, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (node_id, drill_id, str(student_answer), str(expected_answer), 1 if is_correct else 0, day, now),
    )

    stats = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            COUNT(DISTINCT CASE WHEN is_correct = 1 THEN attempt_day END) AS pass_days
        FROM drill_attempts
        WHERE node_id = ?
        """,
        (node_id,),
    ).fetchone()

    recent = conn.execute(
        """
        SELECT is_correct FROM drill_attempts
        WHERE node_id = ?
        ORDER BY attempt_pk DESC
        LIMIT 5
        """,
        (node_id,),
    ).fetchall()
    recent_correct = sum(int(r["is_correct"]) for r in recent)
    recent_total = len(recent)

    open_flags = conn.execute(
        "SELECT COUNT(*) FROM card_feedback WHERE node_id = ? AND resolved = 0",
        (node_id,),
    ).fetchone()[0]

    total = int(stats["total"] or 0)
    correct = int(stats["correct"] or 0)
    pass_days = int(stats["pass_days"] or 0)

    if recent_total >= 4 and recent_correct >= 4:
        if pass_days >= 2 and open_flags == 0:
            status = "consolidated"
            governance = "consolidata"
        else:
            status = "fast_forwarded"
            governance = "consolidata" if open_flags == 0 else "validata_auto"
    elif not is_correct:
        status = "needs_study"
        governance = "validata_auto"
    else:
        status = "in_progress"
        governance = "validata_auto"

    conn.execute(
        """
        INSERT INTO node_progress (
            node_id, status, card_governance, correct_count, attempt_count,
            distinct_pass_days, last_attempt_day, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            status = excluded.status,
            card_governance = excluded.card_governance,
            correct_count = excluded.correct_count,
            attempt_count = excluded.attempt_count,
            distinct_pass_days = excluded.distinct_pass_days,
            last_attempt_day = excluded.last_attempt_day,
            updated_at = excluded.updated_at
        """,
        (node_id, status, governance, correct, total, pass_days, day, now),
    )
    conn.commit()
    return {
        "node_id": node_id,
        "status": status,
        "card_governance": governance,
        "correct_count": correct,
        "attempt_count": total,
        "recent_correct_of_5": recent_correct,
        "distinct_pass_days": pass_days,
    }


def record_hero_artifact(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    proof_family: str,
    payload: dict[str, Any],
    passed: bool,
) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO hero_artifacts (node_id, proof_family, payload_json, passed, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (node_id, proof_family, json.dumps(payload, ensure_ascii=False), 1 if passed else 0, now),
    )
    if passed:
        conn.execute(
            """
            INSERT INTO node_progress (
                node_id, status, card_governance, correct_count, attempt_count,
                distinct_pass_days, last_attempt_day, updated_at
            ) VALUES (?, 'consolidated', 'consolidata', 1, 1, 1, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                status = 'consolidated',
                card_governance = 'consolidata',
                updated_at = excluded.updated_at
            """,
            (node_id, dt.date.today().isoformat(), now),
        )
    conn.commit()
    return {"node_id": node_id, "proof_family": proof_family, "passed": passed}


def flag_card_issue(conn: sqlite3.Connection, node_id: str, note: str) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    cleaned = note.strip()
    if not cleaned:
        raise ValueError("La nota di segnalazione non può essere vuota")
    conn.execute(
        "INSERT INTO card_feedback (node_id, note, resolved, created_at) VALUES (?, ?, 0, ?)",
        (node_id, cleaned, now),
    )
    conn.commit()
    return {"node_id": node_id, "note": cleaned, "status": "flagged_non_blocking"}


def get_student_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM node_progress").fetchall()
    progress_by_node = {r["node_id"]: dict(r) for r in rows}
    mastered_ids = {
        nid
        for nid, info in progress_by_node.items()
        if info["status"] in {"fast_forwarded", "consolidated"}
    }
    failed_ids = {
        nid for nid, info in progress_by_node.items() if info["status"] == "needs_study"
    }
    artifacts = [
        {
            "artifact_pk": r["artifact_pk"],
            "node_id": r["node_id"],
            "proof_family": r["proof_family"],
            "passed": bool(r["passed"]),
            "created_at": r["created_at"],
        }
        for r in conn.execute(
            "SELECT artifact_pk, node_id, proof_family, passed, created_at FROM hero_artifacts ORDER BY artifact_pk DESC"
        ).fetchall()
    ]
    return {
        "progress_by_node": progress_by_node,
        "mastered_ids": sorted(mastered_ids),
        "failed_ids": sorted(failed_ids),
        "hero_artifacts": artifacts,
    }
