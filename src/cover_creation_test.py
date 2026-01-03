from pathlib import Path

from db import get_con, init_db
from cover_repo import insert_cover, list_open_covers, get_cover, fill_cover
from csv_loader import load_validated_frames, classes_from_df, teachers_from_df
from cover_store import CoverStore


def main():
    # load data
    teachers_df, classes_df = load_validated_frames(Path("assets"))
    teachers_by_id = teachers_from_df(teachers_df)
    classes_by_id = classes_from_df(classes_df)

    # pick ids
    sample_class_id = next(iter(classes_by_id.keys()))
    sample_teacher_id = next(iter(teachers_by_id.keys()))

    # init db
    con = get_con()
    init_db(con)

    # create cover and persist
    store = CoverStore.new()
    cover = store.create_cover(sample_class_id)
    cover_id = insert_cover(con, cover)  # assuming your insert_cover returns cover_id

    print("Created:", cover_id)

    # fill it
    ok = fill_cover(con, cover_id, sample_teacher_id)
    print("Fill 1 success:", ok)

    # try fill again (should fail)
    ok2 = fill_cover(con, cover_id, sample_teacher_id)
    print("Fill 2 success (should be False):", ok2)

    # show stored cover
    stored = get_cover(con, cover_id)
    print("Stored cover:", stored)

    # show open covers count
    open_covers = list_open_covers(con)
    print("Open covers now:", len(open_covers))


if __name__ == "__main__":
    main()
