# src/accept_service.py
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from accept_repo import log_attempt
from cover_repo import get_cover, fill_cover
from algorithm import eligibility_reasons
from models import Teacher, ClassSession
from reason_library import match_reasons


def _friendly(codes: list[str]) -> str:
    """
    Turn reason codes into a Slack-friendly bullet list using reason_library.match_reasons.
    Assumes match_reasons returns list[str]. If you made it return a string, this still handles it.
    """
    out = match_reasons(codes)
    if isinstance(out, str):
        return out
    return "\n".join(f"• {x}" for x in out)


def attempt_accept(
    con: sqlite3.Connection,
    cover_id: str,
    teacher_id: str,
    teachers_by_id: dict[str, Teacher],
    classes_by_id: dict[str, ClassSession],
    busy_sessions_by_teacher: dict[str, list[ClassSession]],
) -> tuple[bool, str]:
    """
    Returns: (accepted?, message_or_reason)
    Deterministic + explainable.
    """
    ts = datetime.now(timezone.utc).isoformat()

    con.execute("BEGIN IMMEDIATE")

    try:
        cover = get_cover(con, cover_id)
        if cover is None:
            code = "cover_not_found"
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
            con.commit()
            return False, _friendly([code])

        if cover.status != "OPEN":
            code = "cover_not_open"
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
            con.commit()
            return False, _friendly([code])

        teacher = teachers_by_id.get(teacher_id)
        if teacher is None:
            code = "teacher_not_found"
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
            con.commit()
            return False, _friendly([code])

        class_session = classes_by_id.get(cover.class_id)
        if class_session is None:
            code = "class_not_found_for_cover"
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
            con.commit()
            return False, _friendly([code])

        reasons = eligibility_reasons(teacher, class_session, busy_sessions_by_teacher)
        if reasons:
            reason_str = "|".join(reasons)  # store raw codes in DB
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", reason_str)
            con.commit()
            return False, _friendly(reasons)

        ok = fill_cover(con, cover_id, teacher_id)  # no commit inside
        if ok:
            log_attempt(con, cover_id, teacher_id, ts, "ACCEPTED", "")
            con.commit()
            return True, "✅ accepted"
        else:
            code = "already_filled"
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
            con.commit()
            return False, _friendly([code])

    except Exception:
        con.rollback()
        raise
