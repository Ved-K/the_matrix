# src/algorithm.py
from __future__ import annotations

from zoneinfo import ZoneInfo

from models import Teacher, ClassSession
from datetime import date

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

EXT_SUBJECTS = {"MX1", "MX2"}
SENIOR_SUBJECTS = {"MADV", "MAS", "MX1", "MX2"}

MIN_TRAVEL_GAP_MIN = 180  # 3 hours


def is_senior_teacher(t: Teacher) -> bool:
    return (12 in t.year_levels) or ("MX1" in t.subjects) or ("MX2" in t.subjects)


def mm_to_hhmm(m: int) -> str:
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def matrix_can_teach(t: Teacher, c: ClassSession) -> bool:
    if is_senior_teacher(t):
        # Senior can cover everything 7–12, all courses
        return 7 <= c.year_level <= 12 and c.subject in {
            "MAT",
            "MADV",
            "MAS",
            "MX1",
            "MX2",
        }

    # Junior rules:
    # - Can cover Years 7–10: MAT only
    # - Can cover Year 11: MADV or MAS only
    # - Cannot cover extensions
    if c.subject in EXT_SUBJECTS:
        return False
    if 7 <= c.year_level <= 10:
        return c.subject == "MAT"
    if c.year_level == 11:
        return c.subject in {"MADV", "MAS"}
    return False  # year 12 not allowed for juniors


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def class_local_day_and_minutes(c: ClassSession) -> tuple[str, int, int]:
    """
    Convert class UTC timestamps -> Sydney local day + minutes since midnight.
    Availability is authored in local time, so this is the correct comparison basis.
    """
    start_local = c.start_at.astimezone(SYDNEY_TZ)
    end_local = c.end_at.astimezone(SYDNEY_TZ)

    day = start_local.strftime("%a")  # Mon/Tue/...
    start_min = start_local.hour * 60 + start_local.minute
    end_min = end_local.hour * 60 + end_local.minute
    return day, start_min, end_min


def class_local_date_day_and_minutes(c: ClassSession) -> tuple[date, str, int, int]:
    start_local = c.start_at.astimezone(SYDNEY_TZ)
    end_local = c.end_at.astimezone(SYDNEY_TZ)
    d = start_local.date()
    day = start_local.strftime("%a")
    start_min = start_local.hour * 60 + start_local.minute
    end_min = end_local.hour * 60 + end_local.minute
    return d, day, start_min, end_min


def within_availability(
    teacher: Teacher, day: str, start_min: int, end_min: int
) -> bool:
    ranges = teacher.availability.get(day, [])
    for a_start, a_end in ranges:
        if start_min >= a_start and end_min <= a_end:
            return True
    return False


def capability_reasons(teacher: Teacher, c: ClassSession) -> list[str]:
    reasons: list[str] = []

    if not matrix_can_teach(teacher, c):
        if not is_senior_teacher(teacher):
            if c.year_level == 12:
                reasons.append("junior_cannot_cover_year12")
            if c.subject in {"MX1", "MX2"}:
                reasons.append("junior_cannot_cover_extension")
            elif 7 <= c.year_level <= 10 and c.subject != "MAT":
                reasons.append("junior_only_mat_7_10")
            elif c.year_level == 11 and c.subject not in {"MADV", "MAS"}:
                reasons.append("junior_only_madv_or_mas_11")
        else:
            reasons.append("invalid_class_subject_or_year")

    # can't select the regular teacher
    if c.regular_teacher_id is not None and teacher.teacher_id == c.regular_teacher_id:
        reasons.append("is_regular_teacher")

    if c.campus not in teacher.campuses:
        reasons.append(f"campus_not_allowed({c.campus})")

    return reasons


def clash_reasons(
    teacher_id: str,
    c: ClassSession,
    busy_sessions_by_teacher: dict[str, list[ClassSession]],
) -> list[str]:
    """
    Clash check against the teacher's regular timetable.
    Later you'll also add: clashes against covers they've already accepted.
    """
    reasons: list[str] = []

    busy = busy_sessions_by_teacher.get(teacher_id, [])
    for b in busy:
        # If this is the same class_id (rare), ignore.
        if b.class_id == c.class_id:
            continue
        if overlaps(c.start_at, c.end_at, b.start_at, b.end_at):
            reasons.append(f"timetable_clash({b.class_id})")
            break

    return reasons


def availability_reasons(teacher: Teacher, c: ClassSession) -> list[str]:
    day, start_min, end_min = class_local_day_and_minutes(c)

    if day not in teacher.availability:
        return [f"not_available_on_day({day})"]

    if not within_availability(teacher, day, start_min, end_min):
        return [
            f"not_available_in_window({day}:{mm_to_hhmm(start_min)}-{mm_to_hhmm(end_min)})"
        ]

    return []


def eligibility_reasons(
    teacher: Teacher,
    c: ClassSession,
    busy_sessions_by_teacher: dict[str, list[ClassSession]],
) -> list[str]:
    reasons: list[str] = []
    reasons += capability_reasons(teacher, c)
    reasons += availability_reasons(teacher, c)
    reasons += clash_reasons(teacher.teacher_id, c, busy_sessions_by_teacher)
    return reasons


def eligible_teachers_for_class(
    teachers_by_id: dict[str, Teacher],
    c: ClassSession,
    busy_sessions_by_teacher: dict[str, list[ClassSession]],
) -> tuple[list[str], dict[str, list[str]]]:
    eligible: list[str] = []
    rejected: dict[str, list[str]] = {}

    for t in teachers_by_id.values():
        reasons = eligibility_reasons(t, c, busy_sessions_by_teacher)
        if reasons:
            rejected[t.teacher_id] = reasons
        else:
            eligible.append(t.teacher_id)

    return eligible, rejected


def travel_buffer_reason(
    teacher_id: str,
    cover: ClassSession,
    busy_sessions_by_teacher: dict[str, list[ClassSession]],
    min_gap_min: int = MIN_TRAVEL_GAP_MIN,
) -> str | None:
    """
    Recommendation rule (weekly timetable MVP):
    - Look at the teacher's regular classes on the SAME local weekday as the cover.
    - Find the regular class closest in time to the cover (before/after).
    - If that closest class is at a DIFFERENT campus, require >= 3h gap.
    - If closest class is SAME campus, it's chill.
    """
    busy = busy_sessions_by_teacher.get(teacher_id, [])
    if not busy:
        return None

    cover_day, cover_s, cover_e = class_local_day_and_minutes(cover)

    closest: ClassSession | None = None
    closest_gap: int | None = None

    for b in busy:
        b_day, b_s, b_e = class_local_day_and_minutes(b)
        if b_day != cover_day:
            continue

        # skip overlaps (hard-rejected elsewhere)
        if not (cover_e <= b_s or b_e <= cover_s):
            continue

        gap = (cover_s - b_e) if b_e <= cover_s else (b_s - cover_e)

        if closest_gap is None or gap < closest_gap:
            closest_gap = gap
            closest = b

    if closest is None or closest_gap is None:
        return None

    if closest.campus == cover.campus:
        return None

    if closest_gap < min_gap_min:
        return f"travel_gap_insufficient(nearest={closest.class_id}, gap_min={closest_gap})"

    return None


def recommended_teachers_for_class(
    teachers_by_id: dict[str, Teacher],
    c: ClassSession,
    busy_sessions_by_teacher: dict[str, list[ClassSession]],
) -> tuple[list[str], dict[str, list[str]]]:
    """
    Returns a filtered subset of eligible teachers.
    - Eligibility (hard constraints): capability + availability + clash
    - Recommendation (soft constraints): travel buffer rule
    """
    eligible, rejected = eligible_teachers_for_class(
        teachers_by_id, c, busy_sessions_by_teacher
    )

    recommended: list[str] = []
    not_recommended: dict[str, list[str]] = {}

    for tid in eligible:
        reason = travel_buffer_reason(tid, c, busy_sessions_by_teacher)
        if reason:
            not_recommended[tid] = [reason]
        else:
            recommended.append(tid)

    # merge not_recommended into rejected under a different key if you want,
    # but returning separately is usually cleaner.
    return recommended, not_recommended
