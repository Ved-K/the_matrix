import sqlite3


def upsert_dm(
    con: sqlite3.Connection,
    cover_id: str,
    teacher_id: str,
    dm_channel_id: str,
    dm_ts: str,
    status: str,
    updated_at: str,
) -> None:
    con.execute(
        """
      INSERT INTO cover_dms (cover_id, teacher_id, dm_channel_id, dm_ts, status, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(cover_id, teacher_id) DO UPDATE SET
        dm_channel_id=excluded.dm_channel_id,
        dm_ts=excluded.dm_ts,
        status=excluded.status,
        updated_at=excluded.updated_at
    """,
        (cover_id, teacher_id, dm_channel_id, dm_ts, status, updated_at),
    )


def set_status(
    con: sqlite3.Connection,
    cover_id: str,
    teacher_id: str,
    status: str,
    updated_at: str,
) -> None:
    con.execute(
        """
      UPDATE cover_dms SET status=?, updated_at=?
      WHERE cover_id=? AND teacher_id=?
    """,
        (status, updated_at, cover_id, teacher_id),
    )


def list_dms_for_cover(con: sqlite3.Connection, cover_id: str):
    cur = con.execute(
        """
      SELECT teacher_id, dm_channel_id, dm_ts, status
      FROM cover_dms WHERE cover_id=?
    """,
        (cover_id,),
    )
    return cur.fetchall()


def list_declined_teacher_ids(con: sqlite3.Connection, cover_id: str) -> set[str]:
    cur = con.execute(
        """
      SELECT teacher_id FROM cover_dms WHERE cover_id=? AND status='DECLINED'
    """,
        (cover_id,),
    )
    return {r[0] for r in cur.fetchall()}
