# src/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("state.db")


def get_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    # Optional but good hygiene
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def init_db(con: sqlite3.Connection) -> None:
    """
    Central schema bootstrap.
    Repos/services assume these tables + column names exist.
    """
    con.executescript(
        """
        -- Covers
        CREATE TABLE IF NOT EXISTS covers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cover_id TEXT UNIQUE,
          class_id TEXT NOT NULL,
          cover_date TEXT NOT NULL,
          status TEXT NOT NULL,                 -- OPEN | FILLED
          created_at TEXT NOT NULL,             -- RFC3339 / ISO string in UTC
          filled_at TEXT,                       -- nullable
          assigned_teacher_id TEXT              -- nullable
        );

        CREATE INDEX IF NOT EXISTS idx_covers_status ON covers(status);

        -- Accept attempts log
        CREATE TABLE IF NOT EXISTS accept_attempts (
          attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
          cover_id TEXT NOT NULL,
          teacher_id TEXT NOT NULL,
          attempted_at TEXT NOT NULL,           -- RFC3339 / ISO string in UTC
          status TEXT NOT NULL,                 -- ACCEPTED | REJECTED
          reason TEXT NOT NULL                  -- reason codes or "" if accepted
        );

        CREATE INDEX IF NOT EXISTS idx_attempts_cover ON accept_attempts(cover_id);
        CREATE INDEX IF NOT EXISTS idx_attempts_teacher ON accept_attempts(teacher_id);

        -- Coordinator message pointer (so we can chat_update it)
        CREATE TABLE IF NOT EXISTS cover_messages (
          cover_id TEXT PRIMARY KEY,
          channel_id TEXT NOT NULL,
          message_ts TEXT NOT NULL
        );

        -- Teacher DM pointers + per-teacher state for a cover
        CREATE TABLE IF NOT EXISTS cover_dms (
          cover_id TEXT NOT NULL,
          teacher_id TEXT NOT NULL,
          dm_channel_id TEXT NOT NULL,
          dm_ts TEXT NOT NULL,
          status TEXT NOT NULL,                 -- NOTIFIED | DECLINED | ACCEPTED | LOST
          updated_at TEXT NOT NULL,
          PRIMARY KEY (cover_id, teacher_id)
        );

        -- Table to update coordinator panel messages
        CREATE TABLE IF NOT EXISTS cover_admin_messages (
            cover_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            message_ts TEXT NOT NULL
        );


        CREATE INDEX IF NOT EXISTS idx_cover_dms_cover ON cover_dms(cover_id);
        """
    )
    con.commit()
