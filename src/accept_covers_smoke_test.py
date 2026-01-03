from pathlib import Path

from csv_loader import load_validated_frames, teachers_from_df, classes_from_df
from indexes import index_regular_classes_by_teacher

from db import get_con, init_db
from cover_store import CoverStore
from cover_repo import insert_cover, get_cover
from accept_repo import list_attempts_for_cover
from accept_service import attempt_accept


def main():
    # Load reference data
    teachers_df, classes_df = load_validated_frames(Path("assets"))
    teachers_by_id = teachers_from_df(teachers_df)
    classes_by_id = classes_from_df(classes_df)
    regular_map = index_regular_classes_by_teacher(classes_by_id)

    # Pick a class_id that exists (choose the first)
    class_id = next(iter(classes_by_id.keys()))

    # Pick two different teachers
    teacher_ids = list(teachers_by_id.keys())
    t1 = teacher_ids[0]
    t2 = teacher_ids[1] if len(teacher_ids) > 1 else teacher_ids[0]

    # Init DB
    con = get_con()
    init_db(con)

    # Create + persist a cover
    store = CoverStore.new()
    cover = store.create_cover(class_id)
    cover_id = insert_cover(con, cover)  # should return cover_id like C000001

    print(f"\n✅ Created cover {cover_id} for class {class_id}")

    # Attempt accept #1
    ok1, msg1 = attempt_accept(
        con=con,
        cover_id=cover_id,
        teacher_id=t1,
        teachers_by_id=teachers_by_id,
        classes_by_id=classes_by_id,
        regular_classes_by_teacher=regular_map,
    )
    print(f"Attempt 1: teacher={t1} accepted={ok1} msg={msg1}")

    # Attempt accept #2 (should fail if #1 filled it; or could win if #1 rejected)
    ok2, msg2 = attempt_accept(
        con=con,
        cover_id=cover_id,
        teacher_id=t2,
        teachers_by_id=teachers_by_id,
        classes_by_id=classes_by_id,
        regular_classes_by_teacher=regular_map,
    )
    print(f"Attempt 2: teacher={t2} accepted={ok2} msg={msg2}")

    # Read back the cover
    stored = get_cover(con, cover_id)
    print("\nStored cover in DB:")
    print(stored)

    # Show attempts log
    print("\nAttempts for cover (in order):")
    rows = list_attempts_for_cover(con, cover_id)
    for r in rows:
        print(
            f"- id={r['id']} ts={r['attempted_at']} teacher={r['teacher_id']} "
            f"outcome={r['outcome']} reason={r['reason']}"
        )


if __name__ == "__main__":
    main()
