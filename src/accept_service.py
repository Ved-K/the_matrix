# src/accept_service.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from accept_repo import log_attempt
from cover_repo import get_cover, fill_cover
from cover_time import materialize_for_cover_date
from algorithm import eligibility_reasons
from models import Teacher, ClassSession
from reason_library import match_reasons


def _friendly(codes: list[str]) -> str:
    # Slack-friendly bullets
    if not codes:
        return ""
    return "\n".join(f"• {match_reasons(c)}" for c in codes)


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
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

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

        template = classes_by_id.get(cover.class_id)
        if template is None:
            code = "class_not_found_for_cover"
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
            con.commit()
            return False, _friendly([code])

        # Materialize the template onto the requested cover date
        try:
            class_session = materialize_for_cover_date(template, cover.cover_date)
        except Exception:
            # Keep it minimal: reuse an existing code (or add a new one later)
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

        # Atomic fill: succeeds for exactly one teacher
        ok = fill_cover(con, cover_id, teacher_id)
        if ok:
            log_attempt(con, cover_id, teacher_id, ts, "ACCEPTED", "")
            con.commit()
            return True, "accepted"

        code = "already_filled"
        log_attempt(con, cover_id, teacher_id, ts, "REJECTED", code)
        con.commit()
        return False, _friendly([code])

    except Exception:
        con.rollback()
        raise
