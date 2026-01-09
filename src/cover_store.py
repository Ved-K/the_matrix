from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from cover_models import CoverRequest


@dataclass
class CoverStore:
    open_covers: dict[str, CoverRequest]
    all_covers: dict[str, CoverRequest]

    @staticmethod
    def new() -> "CoverStore":
        return CoverStore(open_covers={}, all_covers={})

    def create_cover(self, class_id: str, cover_date: str) -> CoverRequest:
        """
        cover_date: "YYYY-MM-DD" (Sydney local date)
        cover_id will be assigned by the DB insert (C000001, C000002, ...).
        """
        now = datetime.now(timezone.utc)

        cover = CoverRequest(
            cover_id="",  # DB will fill this
            class_id=class_id,
            cover_date=cover_date,  # NEW
            status="OPEN",
            created_at=now,
            filled_at=None,
            assigned_teacher_id=None,
        )

        # Keep in-memory maps optional for debugging; you can also remove these later.
        # We only store it once it has a real cover_id (after insert_cover).
        return cover
