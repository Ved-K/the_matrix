# src/cover_repo.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from cover_models import CoverRequest


def insert_cover(con: sqlite3.Connection, cover: CoverRequest) -> str:
    """
    Inserts cover with a numeric autoincrement id, then sets cover_id like C000001.
    IMPORTANT: does NOT commit. Caller decides.
    """
    cur = con.execute(
        """
        INSERT INTO covers (cover_id, class_id, cover_date, status, created_at, filled_at, assigned_teacher_id)
        VALUES (NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            cover.class_id,
            cover.cover_date,  # NEW
            cover.status,
            cover.created_at.isoformat(),
            cover.filled_at.isoformat() if cover.filled_at else None,
            cover.assigned_teacher_id,
        ),
    )
    new_id = cur.lastrowid
    cover_id = f"C{new_id:06d}"

    con.execute("UPDATE covers SET cover_id = ? WHERE id = ?", (cover_id, new_id))
    cover.cover_id = cover_id
    return cover_id


def get_cover(con: sqlite3.Connection, cover_id: str) -> CoverRequest | None:
    row = con.execute("SELECT * FROM covers WHERE cover_id = ?", (cover_id,)).fetchone()
    if row is None:
        return None

    return CoverRequest(
        cover_id=row["cover_id"],
        class_id=row["class_id"],
        cover_date=row["cover_date"],  # NEW
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        filled_at=(
            datetime.fromisoformat(row["filled_at"]) if row["filled_at"] else None
        ),
        assigned_teacher_id=row["assigned_teacher_id"],
    )


def fill_cover(con: sqlite3.Connection, cover_id: str, teacher_id: str) -> bool:
    """
    Atomic fill. IMPORTANT: does NOT commit. Caller decides.
    """
    now = datetime.now(timezone.utc).isoformat()

    cur = con.execute(
        """
        UPDATE covers
        SET status = 'FILLED',
            assigned_teacher_id = ?,
            filled_at = ?
        WHERE cover_id = ?
          AND status = 'OPEN'
        """,
        (teacher_id, now, cover_id),
    )

    return cur.rowcount == 1


def list_open_covers(con: sqlite3.Connection) -> list[CoverRequest]:
    rows = con.execute(
        "SELECT * FROM covers WHERE status = 'OPEN' ORDER BY created_at ASC"
    ).fetchall()

    out: list[CoverRequest] = []
    for r in rows:
        out.append(
            CoverRequest(
                cover_id=r["cover_id"],
                class_id=r["class_id"],
                cover_date=r["cover_date"],  # NEW
                status=r["status"],
                created_at=datetime.fromisoformat(r["created_at"]),
                filled_at=(
                    datetime.fromisoformat(r["filled_at"]) if r["filled_at"] else None
                ),
                assigned_teacher_id=r["assigned_teacher_id"],
            )
        )
    return out


def list_filled_covers(con: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    """
    Returns: [(cover_id, class_id, cover_date, assigned_teacher_id), ...] for FILLED covers only
    """
    rows = con.execute(
        """
        SELECT cover_id, class_id, cover_date, assigned_teacher_id
        FROM covers
        WHERE status = 'FILLED' AND assigned_teacher_id IS NOT NULL
        ORDER BY id ASC
        """
    ).fetchall()

    return [
        (r["cover_id"], r["class_id"], r["cover_date"], r["assigned_teacher_id"])
        for r in rows
    ]
