from pathlib import Path

from csv_loader import load_validated_frames, teachers_from_df, classes_from_df
from indexes import index_regular_classes_by_teacher
from algorithm import eligible_teachers_for_class


def main():
    teachers_df, classes_df = load_validated_frames(Path("assets"))
    teachers_by_id = teachers_from_df(teachers_df)
    classes_by_id = classes_from_df(classes_df)

    regular_map = index_regular_classes_by_teacher(classes_by_id)

    target_class_id = "12-MX2-SS21"
    target_class = classes_by_id[target_class_id]
    print(
        "Target class:",
        target_class.class_id,
        target_class.start_at,
        "->",
        target_class.end_at,
    )

    eligible, rejected = eligible_teachers_for_class(
        teachers_by_id, target_class, regular_map
    )

    print("\nEligible teachers:", eligible)
    print("Eligible count:", len(eligible))

    # show a few rejected examples
    print("\nSample rejections:")
    for tid in list(rejected.keys())[:10]:
        print(tid, "=>", rejected[tid])


if __name__ == "__main__":
    main()
