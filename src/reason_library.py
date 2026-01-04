from __future__ import annotations

import re


def match_reason(code: str) -> str:
    # Direct matches
    if code == "cover_not_found":
        return "That cover request doesn’t exist."
    if code == "cover_not_open":
        return "That cover has already been filled."
    if code == "teacher_not_found":
        return "Teacher ID not found."
    if code == "class_not_found_for_cover":
        return "Class for this cover could not be found."
    if code == "already_filled":
        return "Someone else already accepted this cover."
    if code == "accepted":
        return "Accepted successfully."

    if code == "is_regular_teacher":
        return "You are the regular teacher for this class."

    if code == "junior_cannot_cover_year12":
        return "Junior teachers can’t cover Year 12 classes."
    if code == "junior_cannot_cover_extension":
        return "Junior teachers can’t cover Extension classes (MX1/MX2)."
    if code == "junior_only_mat_7_10":
        return "Junior teachers can only cover MAT for Years 7–10."
    if code == "junior_only_madv_or_mas_11":
        return "Junior teachers can only cover MADV/MAS for Year 11."

    # Patterned codes
    m = re.match(r"campus_not_allowed\((.+)\)", code)
    if m:
        campus = m.group(1)
        return f"Not eligible for {campus.title()} campus."

    m = re.match(r"subject_mismatch\((.+)\)", code)
    if m:
        subj = m.group(1)
        return f"Not approved to teach {subj}."

    m = re.match(r"year_level_mismatch\((\d+)\)", code)
    if m:
        yr = m.group(1)
        return f"Not approved to teach Year {yr}."

    m = re.match(r"not_available_on_day\((.+)\)", code)
    if m:
        day = m.group(1)
        return f"Not available on {day}."

    # expects: not_available_in_window(Sun:09:00-12:00)
    m = re.match(
        r"not_available_in_window\(([A-Za-z]{3}):(\d\d:\d\d)-(\d\d:\d\d)\)", code
    )
    if m:
        day, s, e = m.group(1), m.group(2), m.group(3)
        return f"Not available {day} {s}–{e}."

    m = re.match(r"timetable_clash\((.+)\)", code)
    if m:
        clash_id = m.group(1)
        return f"Clashes with another class ({clash_id})."

    m = re.match(r"travel_gap_insufficient\(nearest=(.+), gap_min=(\d+)\)", code)
    if m:
        nearest, gap = m.group(1), int(m.group(2))
        return (
            f"Not recommended: only {gap} min gap travel to another campus ({nearest})."
        )

    # Fallback
    return code


def match_reasons(codes: list[str]) -> list[str]:
    return [match_reason(c) for c in codes]


def split_reason_str(reason_str: str) -> list[str]:
    # accept_service stores codes joined by "|"
    if not reason_str:
        return []
    return reason_str.split("|")
