from pathlib import Path

from csv_loader import load_validated_frames, teachers_from_df, classes_from_df
from db import get_con, init_db
from cover_store import CoverStore
from cover_repo import insert_cover
from recommendations_engine import get_recommendations_for_cover
from sample_output import format_recommendations_message


def main():
    teachers_df, classes_df = load_validated_frames(Path("assets"))
    teachers_by_id = teachers_from_df(teachers_df)
    classes_by_id = classes_from_df(classes_df)

    target_class_id = "12-MX1-EU11"
    if target_class_id not in classes_by_id:
        print(f"Class id not found: {target_class_id}")
        print("Try one of these:")
        for cid in list(classes_by_id.keys())[:30]:
            print(" -", cid)
        return

    con = get_con()
    init_db(con)

    store = CoverStore.new()
    cover = store.create_cover(target_class_id)
    cover_id = insert_cover(con, cover)

    res = get_recommendations_for_cover(con, cover_id, teachers_by_id, classes_by_id)
    msg = format_recommendations_message(res, teachers_by_id, classes_by_id)

    print(msg)


if __name__ == "__main__":
    main()
