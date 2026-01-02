from __future__ import annotations

from pathlib import Path
import pandas as pd

from models import Teacher, ClassSession
from csv_parse_helpers import (
    split_pipe,
    parse_int_set_pipe,
    parse_availability_weekly,
    parse_rfc3339,
)
from csv_validator import read_csv_or_fail, validate_teachers, validate_classes


def load_validated_frames(assets_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    teachers = read_csv_or_fail(assets_dir / "teachers_test.csv")
    classes = read_csv_or_fail(assets_dir / "classes_test.csv")

    validate_teachers(teachers)
    validate_classes(classes, teachers)

    return teachers, classes


def teachers_from_df(df: pd.DataFrame) -> dict[str, Teacher]:
    teachers_by_id: dict[str, Teacher] = {}

    for _, row in df.iterrows():
        teacher_id = row["teacher_id"].strip()

        t = Teacher(
            teacher_id=teacher_id,
            full_name=row["full_name"].strip(),
            slack_user_id=(row["slack_user_id"].strip() or None),
            employment_type=row[
                "employment_type"
            ].strip(),  # validator enforces allowed values
            primary_campus=row[
                "primary_campus"
            ].strip(),  # validator enforces allowed values
            campuses=set(split_pipe(row["campuses"])),
            subjects=set(split_pipe(row["subjects"])),
            year_levels=parse_int_set_pipe(row["year_levels"]),
            availability=parse_availability_weekly(row["availability_weekly"]),
            teaching_hours=float(row["teaching_hours"]),
            max_covers_per_week=int(row["max_covers_per_week"]),
        )

        teachers_by_id[teacher_id] = t

    return teachers_by_id


def classes_from_df(df: pd.DataFrame) -> dict[str, ClassSession]:
    classes_by_id: dict[str, ClassSession] = {}

    for _, row in df.iterrows():
        class_id = row["class_id"].strip()

        c = ClassSession(
            class_id=class_id,
            class_name=row["class_name"].strip(),
            subject=row["subject"].strip(),
            year_level=int(row["year_level"]),
            campus=row["campus"].strip(),
            start_at=parse_rfc3339(row["start_at"]),
            end_at=parse_rfc3339(row["end_at"]),
            regular_teacher_id=(row["regular_teacher_id"].strip() or None),
        )

        classes_by_id[class_id] = c

    return classes_by_id


def main() -> None:
    assets = Path("assets")
    teachers_df, classes_df = load_validated_frames(assets)

    teachers_by_id = teachers_from_df(teachers_df)
    classes_by_id = classes_from_df(classes_df)

    print(f"\nLoaded {len(teachers_by_id)} teachers into objects\n")
    print(f"Loaded {len(classes_by_id)} classes into objects\n")

    # print one example
    sample = next(iter(teachers_by_id.values()))
    print("Sample Teacher object:")
    print(sample)

    sample_class = next(iter(classes_by_id.values()))
    print("\nSample ClassSession object:")
    print(sample_class)


if __name__ == "__main__":
    main()
