# src/cover_repo.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from cover_models import CoverRequest


def insert_cover(con, cover):
    cur = con.execute(
        """
        INSERT INTO covers (cover_id, class_id, status, created_at, filled_at, assigned_teacher_id)
        VALUES (NULL, ?, ?, ?, ?, ?)
        """,
        (
            cover.class_id,
            cover.status,
            cover.created_at.isoformat(),
            cover.filled_at.isoformat() if cover.filled_at else None,
            cover.assigned_teacher_id,
        ),
    )
    new_id = cur.lastrowid
    cover_id = f"C{new_id:06d}"

    con.execute("UPDATE covers SET cover_id = ? WHERE id = ?", (cover_id, new_id))
    con.commit()

    cover.cover_id = cover_id
    return cover_id


def get_cover(con: sqlite3.Connection, cover_id: str) -> CoverRequest | None:
    row = con.execute("SELECT * FROM covers WHERE cover_id = ?", (cover_id,)).fetchone()
    if row is None:
        return None

    return CoverRequest(
        cover_id=row["cover_id"],
        class_id=row["class_id"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        filled_at=(
            datetime.fromisoformat(row["filled_at"]) if row["filled_at"] else None
        ),
        assigned_teacher_id=row["assigned_teacher_id"],
    )


def fill_cover(con, cover_id: str, teacher_id: str) -> bool:
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
    con.commit()

    # rowcount == 1 means we successfully filled it
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
                status=r["status"],
                created_at=datetime.fromisoformat(r["created_at"]),
                filled_at=(
                    datetime.fromisoformat(r["filled_at"]) if r["filled_at"] else None
                ),
                assigned_teacher_id=r["assigned_teacher_id"],
            )
        )
    return out
