from pathlib import Path

from csv_loader import load_validated_frames, teachers_from_df, classes_from_df
from indexes import index_regular_classes_by_teacher
from algorithm import (
    eligible_teachers_for_class,
    recommended_teachers_for_class,
    travel_buffer_reason,
    class_local_day_and_minutes,
)
from algorithm import SYDNEY_TZ


def main():
    teachers_df, classes_df = load_validated_frames(Path("assets"))
    teachers_by_id = teachers_from_df(teachers_df)
    classes_by_id = classes_from_df(classes_df)

    regular_map = index_regular_classes_by_teacher(classes_by_id)

    # Pick a class that likely has more eligible teachers (MX2 can be tiny).
    # Change this to whatever you want.
    target_class_id = "12-MX1-EU11"

    if target_class_id not in classes_by_id:
        print(f"Class id not found: {target_class_id}")
        print("Try one of these:")
        for cid in list(classes_by_id.keys())[:30]:
            print(" -", cid)
        return

    target_class = classes_by_id[target_class_id]

    start_local = target_class.start_at.astimezone(SYDNEY_TZ)
    end_local = target_class.end_at.astimezone(SYDNEY_TZ)
    print(
        "Local time:",
        start_local.strftime("%a %H:%M"),
        "->",
        end_local.strftime("%H:%M"),
    )

    # 1) Eligibility (hard rules)
    eligible, rejected = eligible_teachers_for_class(
        teachers_by_id, target_class, regular_map
    )
    print("\nEligible teachers:", eligible)
    print("Eligible count:", len(eligible))

    # 2) Recommendation (soft travel rule)
    recommended, excluded = recommended_teachers_for_class(
        teachers_by_id, target_class, regular_map
    )
    print("\nRecommended teachers:", recommended)
    print("Recommended count:", len(recommended))

    print("\nExcluded by recommendation (travel rule):")
    if not excluded:
        print("  (none)")
    else:
        for tid, reasons in excluded.items():
            print(f"  {tid} => {reasons}")

    # 3) Debug: for each excluded teacher, show their same-day regular classes
    if excluded:
        cover_day, cover_s, cover_e = class_local_day_and_minutes(target_class)
        print(
            f"\nDebug (cover local weekday={cover_day}, window={cover_s}-{cover_e} mins):"
        )
        for tid in excluded.keys():
            print(f"\nTeacher {tid} ({teachers_by_id[tid].full_name})")
            busy = regular_map.get(tid, [])
            # show only same weekday classes
            for b in busy:
                b_day, b_s, b_e = class_local_day_and_minutes(b)
                if b_day == cover_day:
                    print(
                        f"  regular: {b.class_id} campus={b.campus} window={b_s}-{b_e}"
                    )

            # also print the actual computed reason again
            print(
                "  computed reason:",
                travel_buffer_reason(tid, target_class, regular_map),
            )

    # Optional: show a few hard rejections too
    print("\nSample hard rejections (first 10):")
    for tid in list(rejected.keys())[:30]:
        print(tid, "=>", rejected[tid])


if __name__ == "__main__":
    main()
