# src/accept_service.py
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from accept_repo import log_attempt
from cover_repo import get_cover, fill_cover
from algorithm import eligibility_reasons
from models import Teacher, ClassSession


def attempt_accept(
    con: sqlite3.Connection,
    cover_id: str,
    teacher_id: str,
    teachers_by_id: dict[str, Teacher],
    classes_by_id: dict[str, ClassSession],
    regular_classes_by_teacher: dict[str, list[ClassSession]],
) -> tuple[bool, str]:
    """
    Returns: (accepted?, message_or_reason)
    Deterministic + explainable.
    """

    ts = datetime.now(timezone.utc).isoformat()

    # Single-writer transaction (important later when multiple accepts happen fast)
    con.execute("BEGIN IMMEDIATE")

    try:
        cover = get_cover(con, cover_id)
        if cover is None:
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", "cover_not_found")
            con.commit()
            return False, "cover_not_found"

        if cover.status != "OPEN":
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", "cover_not_open")
            con.commit()
            return False, "cover_not_open"

        teacher = teachers_by_id.get(teacher_id)
        if teacher is None:
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", "teacher_not_found")
            con.commit()
            return False, "teacher_not_found"

        class_session = classes_by_id.get(cover.class_id)
        if class_session is None:
            log_attempt(
                con, cover_id, teacher_id, ts, "REJECTED", "class_not_found_for_cover"
            )
            con.commit()
            return False, "class_not_found_for_cover"

        reasons = eligibility_reasons(
            teacher, class_session, regular_classes_by_teacher
        )
        if reasons:
            reason_str = "|".join(reasons)
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", reason_str)
            con.commit()
            return False, reason_str

        # Atomic fill (will succeed for exactly one accept attempt)
        ok = fill_cover(con, cover_id, teacher_id)  # no commit inside
        if ok:
            log_attempt(con, cover_id, teacher_id, ts, "ACCEPTED", "")
            con.commit()
            return True, "accepted"
        else:
            log_attempt(con, cover_id, teacher_id, ts, "REJECTED", "already_filled")
            con.commit()
            return False, "already_filled"

    except Exception:
        con.rollback()
        raise
