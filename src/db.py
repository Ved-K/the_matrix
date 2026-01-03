# src/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("state.db")


def get_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
    CREATE TABLE IF NOT EXISTS covers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cover_id TEXT UNIQUE,
        class_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        filled_at TEXT,
        assigned_teacher_id TEXT
    );

    CREATE TABLE IF NOT EXISTS accept_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cover_id TEXT NOT NULL,
        teacher_id TEXT NOT NULL,
        attempted_at TEXT NOT NULL,
        outcome TEXT NOT NULL,
        reason TEXT NOT NULL
    );
    """
    )
    con.commit()
