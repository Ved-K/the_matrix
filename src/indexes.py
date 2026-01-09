from __future__ import annotations
from models import ClassSession
from cover_repo import list_filled_covers
from cover_time import materialize_for_cover_date


# given a teacher id, we need to build a list of all their regular classes so we can check
# whether they have a conflicting class in the cover's period.
def index_regular_classes_by_teacher(
    classes_by_id: dict[str, ClassSession],
) -> dict[str, list[ClassSession]]:
    out: dict[str, list[ClassSession]] = {}
    for c in classes_by_id.values():
        if c.regular_teacher_id:
            out.setdefault(c.regular_teacher_id, []).append(c)

    for tid, arr in out.items():
        arr.sort(key=lambda x: x.start_at)
    return out


def index_filled_cover_classes_by_teacher(
    con,
    classes_by_id: dict[str, ClassSession],
) -> dict[str, list[ClassSession]]:
    out: dict[str, list[ClassSession]] = {}

    for row in list_filled_covers(con):
        # Support both old + new return shapes
        # old: (cover_id, class_id, teacher_id)
        # new: (cover_id, class_id, cover_date, teacher_id)
        if len(row) == 3:
            _cover_id, class_id, teacher_id = row
            cover_date = None
        else:
            _cover_id, class_id, cover_date, teacher_id = row

        template = classes_by_id.get(class_id)
        if template is None:
            continue

        if cover_date:
            try:
                c = materialize_for_cover_date(template, cover_date)
            except Exception:
                # bad date mismatch or invalid data; skip for MVP
                continue
        else:
            # fallback for old DB rows
            c = template

        out.setdefault(teacher_id, []).append(c)

    for tid, arr in out.items():
        arr.sort(key=lambda x: x.start_at)

    return out


def merge_busy_maps(
    regular_map: dict[str, list[ClassSession]],
    cover_map: dict[str, list[ClassSession]],
) -> dict[str, list[ClassSession]]:
    out: dict[str, list[ClassSession]] = {}

    all_ids = set(regular_map.keys()) | set(cover_map.keys())
    for tid in all_ids:
        merged = []
        merged.extend(regular_map.get(tid, []))
        merged.extend(cover_map.get(tid, []))
        merged.sort(key=lambda x: x.start_at)
        out[tid] = merged

    return out
