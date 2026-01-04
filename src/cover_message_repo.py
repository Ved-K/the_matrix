import sqlite3


def upsert_cover_message(
    con: sqlite3.Connection, cover_id: str, channel_id: str, message_ts: str
) -> None:
    con.execute(
        """
      INSERT INTO cover_messages (cover_id, channel_id, message_ts)
      VALUES (?, ?, ?)
      ON CONFLICT(cover_id) DO UPDATE SET
        channel_id=excluded.channel_id,
        message_ts=excluded.message_ts
    """,
        (cover_id, channel_id, message_ts),
    )


def get_cover_message(con: sqlite3.Connection, cover_id: str) -> tuple[str, str] | None:
    cur = con.execute(
        "SELECT channel_id, message_ts FROM cover_messages WHERE cover_id=?",
        (cover_id,),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else None
