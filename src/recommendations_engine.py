# recommendations_engine.py (or wherever this lives)
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from cover_repo import get_cover
from cover_time import materialize_for_cover_date
from algorithm import eligible_teachers_for_class, recommended_teachers_for_class
from models import Teacher, ClassSession
from indexes import (
    index_regular_classes_by_teacher,
    index_filled_cover_classes_by_teacher,
    merge_busy_maps,
)


@dataclass
class RecommendationResult:
    cover_id: str
    class_id: str
    recommended: list[str]
    soft_excluded: dict[str, list[str]]
    hard_rejected: dict[str, list[str]]


def get_recommendations_for_cover(
    con: sqlite3.Connection,
    cover_id: str,
    teachers_by_id: dict[str, Teacher],
    classes_by_id: dict[str, ClassSession],
) -> RecommendationResult:
    cover = get_cover(con, cover_id)
    if cover is None:
        raise ValueError(f"cover_not_found: {cover_id}")

    template = classes_by_id.get(cover.class_id)
    if template is None:
        raise ValueError(f"class_not_found_for_cover: {cover.class_id}")

    # ✅ MATERIALIZE onto this cover's specific date
    c = materialize_for_cover_date(template, cover.cover_date)

    # Busy sessions = regular timetable + accepted covers
    regular_map = index_regular_classes_by_teacher(classes_by_id)
    filled_map = index_filled_cover_classes_by_teacher(
        con, classes_by_id
    )  # see note below
    busy_map = merge_busy_maps(regular_map, filled_map)

    _eligible, hard_rejected = eligible_teachers_for_class(teachers_by_id, c, busy_map)
    recommended, soft_excluded = recommended_teachers_for_class(
        teachers_by_id, c, busy_map
    )

    return RecommendationResult(
        cover_id=cover.cover_id,
        class_id=cover.class_id,
        recommended=recommended,
        soft_excluded=soft_excluded,
        hard_rejected=hard_rejected,
    )
