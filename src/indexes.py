from __future__ import annotations
from models import ClassSession


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
