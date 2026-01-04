from __future__ import annotations
from models import ClassSession
from cover_repo import list_filled_covers


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

    for _, class_id, teacher_id in list_filled_covers(con):
        c = classes_by_id.get(class_id)
        if c is None:
            # cover references a class_id we don't know about (bad data / future change)
            continue
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
