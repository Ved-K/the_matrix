# src/accept_repo.py
from __future__ import annotations
import sqlite3


def log_attempt(
    con: sqlite3.Connection,
    cover_id: str,
    teacher_id: str,
    attempted_at: str,
    outcome: str,
    reason: str,
) -> None:
    con.execute(
        """
        INSERT INTO accept_attempts (cover_id, teacher_id, attempted_at, status, reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cover_id, teacher_id, attempted_at, outcome, reason),
    )


def list_attempts_for_cover(con: sqlite3.Connection, cover_id: str):
    return con.execute(
        """
        SELECT * FROM accept_attempts
        WHERE cover_id = ?
        ORDER BY id ASC
        """,
        (cover_id,),
    ).fetchall()
