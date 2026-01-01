from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd

# data definitions
TEACHERS_COLUMNS = [
    "teacher_id",
    "full_name",
    "slack_user_id",
    "employment_type",
    "primary_campus",
    "campuses",
    "subjects",
    "year_levels",
    "availability_weekly",
    "teaching_hours",
    "max_covers_per_week",
]

CLASSES_COLUMNS = [
    "class_id",
    "class_name",
    "subject",
    "year_level",
    "campus",
    "start_at",
    "end_at",
    "regular_teacher_id",
]

ALLOWED_CAMPUSES = {"parramatta", "strathfield", "chatswood", "epping"}
ALLOWED_EMPLOYMENT = {"CASUAL", "PART_TIME", "FULL_TIME"}
ALLOWED_SUBJECTS = {"MAT", "MADV", "MAS", "MX1", "MX2"}


def fail(msg: str) -> None:
    raise ValueError(msg)


def read_csv_or_fail(path: Path) -> pd.DataFrame:
    if not path.exists():
        fail(f"File not found: {path}")
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except Exception as e:
        fail(f"Could not read CSV '{path}': {e}")


def require_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    extra = [c for c in df.columns if c not in required]
    if missing:
        fail(f"{name}: missing required columns: {missing}")
    if extra:
        # fails if there's unexpected columns
        fail(f"{name}: unexpected extra columns: {extra}")


# checks to see if there's blank or duplicate values
def require_unique_nonempty(df: pd.DataFrame, col: str, name: str) -> None:
    if (df[col].str.strip() == "").any():
        bad = df.index[df[col].str.strip() == ""].tolist()[:10]
        fail(f"{name}: '{col}' contains blank values: {bad}")

    dupes = df[col][df[col].duplicated()].unique().tolist()
    if dupes:
        fail(f"{name}: '{col}' has duplicate values: {dupes}")


# validates every teacher from teachers.csv
def validate_teachers(df: pd.DataFrame) -> None:
    require_columns(df, TEACHERS_COLUMNS, "teachers")

    require_unique_nonempty(df, "teacher_id", "teachers")

    # employment_type
    bad_emp = (
        df.loc[~df["employment_type"].isin(ALLOWED_EMPLOYMENT), "employment_type"]
        .unique()
        .tolist()
    )
    if bad_emp:
        fail(
            f"teachers: invalid employment_type values: {bad_emp} (allowed: {sorted(ALLOWED_EMPLOYMENT)})"
        )

    # campus fields
    bad_primary = (
        df.loc[~df["primary_campus"].isin(ALLOWED_CAMPUSES), "primary_campus"]
        .unique()
        .tolist()
    )
    if bad_primary:
        fail(
            f"teachers: invalid primary_campus values: {bad_primary} (allowed: {sorted(ALLOWED_CAMPUSES)})"
        )

    # teaching_hours
    def is_float(x: str) -> bool:
        try:
            float(x)
            return True
        except Exception:
            return False

    bad_hours = (
        df.loc[~df["teaching_hours"].apply(is_float), "teaching_hours"]
        .unique()
        .tolist()
    )
    if bad_hours:
        fail(f"teachers: teaching_hours must be numeric. Bad values: {bad_hours}")

    # max_covers_per_week int
    def is_int(x: str) -> bool:
        try:
            int(x)
            return True
        except Exception:
            return False

    bad_max = (
        df.loc[~df["max_covers_per_week"].apply(is_int), "max_covers_per_week"]
        .unique()
        .tolist()
    )
    if bad_max:
        fail(f"teachers: max_covers_per_week must be int. Bad values: {bad_max}")

    # campuses list must include primary_campus
    def primary_in_campuses(row) -> bool:
        campuses = {c.strip() for c in str(row["campuses"]).split("|") if c.strip()}
        return row["primary_campus"] in campuses

    missing_primary = df.index[~df.apply(primary_in_campuses, axis=1)].tolist()
    if missing_primary:
        fail(
            f"teachers: primary_campus not included in campuses for row idx: {missing_primary[:10]}"
        )

    # subjects must be valid codes
    def invalid_subjects(s: str) -> list[str]:
        vals = [x.strip() for x in str(s).split("|") if x.strip()]
        return [v for v in vals if v not in ALLOWED_SUBJECTS]

    bad_sub_rows = []
    for i, s in enumerate(df["subjects"].tolist()):
        bad = invalid_subjects(s)
        if bad:
            bad_sub_rows.append((i, bad))
    if bad_sub_rows:
        fail(
            f"teachers: invalid subject codes. Examples: {bad_sub_rows[:5]} (allowed: {sorted(ALLOWED_SUBJECTS)})"
        )

    # year_levels must be ints and from 7 to 12 inclusive
    def invalid_years(s: str) -> list[str]:
        vals = [x.strip() for x in str(s).split("|") if x.strip()]
        bad = []
        for v in vals:
            try:
                y = int(v)
                if y < 7 or y > 12:
                    bad.append(v)
            except Exception:
                bad.append(v)
        return bad

    bad_year_rows = []
    for i, s in enumerate(df["year_levels"].tolist()):
        bad = invalid_years(s)
        if bad:
            bad_year_rows.append((i, bad))
    if bad_year_rows:
        fail(
            f"teachers: invalid year_levels. Examples: {bad_year_rows[:5]} (allowed 7..12)"
        )


# checks if a class is valid
def validate_classes(df: pd.DataFrame, teachers_df: pd.DataFrame) -> None:
    require_columns(df, CLASSES_COLUMNS, "classes")
    require_unique_nonempty(df, "class_id", "classes")

    # subject/campus/year_level
    bad_subject = (
        df.loc[~df["subject"].isin(ALLOWED_SUBJECTS), "subject"].unique().tolist()
    )
    if bad_subject:
        fail(
            f"classes: invalid subject values: {bad_subject} (allowed: {sorted(ALLOWED_SUBJECTS)})"
        )

    bad_campus = (
        df.loc[~df["campus"].isin(ALLOWED_CAMPUSES), "campus"].unique().tolist()
    )
    if bad_campus:
        fail(
            f"classes: invalid campus values: {bad_campus} (allowed: {sorted(ALLOWED_CAMPUSES)})"
        )

    def is_year_int_7_12(x: str) -> bool:
        try:
            y = int(x)
            return 7 <= y <= 12
        except Exception:
            return False

    bad_year = (
        df.loc[~df["year_level"].apply(is_year_int_7_12), "year_level"]
        .unique()
        .tolist()
    )
    if bad_year:
        fail(f"classes: year_level must be int in 7..12. Bad values: {bad_year}")

    # datetime parse (RFC3339 - ensures that dates and times are unambiguous across systems)
    try:
        start = pd.to_datetime(df["start_at"], utc=True)
        end = pd.to_datetime(df["end_at"], utc=True)
    except Exception as e:
        fail(f"classes: start_at/end_at must be parseable RFC3339 datetimes: {e}")

    if not (end > start).all():
        bad = df.index[~(end > start)].tolist()
        fail(f"classes: end_at must be after start_at (bad row idx): {bad[:10]}")

    # regular_teacher_id must exist if provided
    teacher_ids = set(teachers_df["teacher_id"].tolist())
    bad_ref = (
        df.loc[
            (df["regular_teacher_id"].str.strip() != "")
            & (~df["regular_teacher_id"].isin(teacher_ids)),
            "regular_teacher_id",
        ]
        .unique()
        .tolist()
    )
    if bad_ref:
        fail(f"classes: regular_teacher_id references unknown teacher_id(s): {bad_ref}")


def main() -> None:
    assets = Path("assets")
    teachers_path = assets / "teachers_test.csv"
    classes_path = assets / "classes_test.csv"

    teachers = read_csv_or_fail(teachers_path)
    classes = read_csv_or_fail(classes_path)

    validate_teachers(teachers)
    validate_classes(classes, teachers)

    print("\nCSVs loaded and validated\n")

    print(f"Teachers: {len(teachers)} rows")
    print(teachers.head(5).to_string(index=False))

    print("\n---\n")

    print(f"Classes: {len(classes)} rows")
    print(classes.head(5).to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nVALIDATION ERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
