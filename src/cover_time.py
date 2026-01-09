# src/cover_time.py
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from models import ClassSession
from algorithm import class_local_day_and_minutes  # you already have this

SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def materialize_for_cover_date(template: ClassSession, cover_date: str) -> ClassSession:
    """
    Take a timetable template session (class_id + start/end mins) and apply a specific local date.
    cover_date is "YYYY-MM-DD" in Sydney time.
    """
    d = date.fromisoformat(cover_date)

    day_str, start_min, end_min = class_local_day_and_minutes(template)
    # Validate weekday matches template (important)
    if d.strftime("%a") != day_str:
        raise ValueError(
            f"cover_date_day_mismatch: expected {day_str}, got {d.strftime('%a')}"
        )

    base = datetime.combine(d, time(0, 0), tzinfo=SYDNEY_TZ)
    start_local = base + timedelta(minutes=start_min)
    end_local = base + timedelta(minutes=end_min)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    return replace(template, start_at=start_utc, end_at=end_utc)
