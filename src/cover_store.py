from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import itertools

from cover_models import CoverRequest


@dataclass
class CoverStore:
    # simple deterministic ID generator (C000001, C000002...)
    _seq: itertools.count
    open_covers: dict[str, CoverRequest]
    all_covers: dict[str, CoverRequest]

    @staticmethod
    def new() -> "CoverStore":
        return CoverStore(_seq=itertools.count(1), open_covers={}, all_covers={})

    def create_cover(self, class_id: str) -> CoverRequest:
        cover_num = next(self._seq)
        cover_id = f"C{cover_num:06d}"

        now = datetime.now(timezone.utc)
        cover = CoverRequest(
            cover_id=cover_id,
            class_id=class_id,
            status="OPEN",
            created_at=now,
        )

        self.open_covers[cover_id] = cover
        self.all_covers[cover_id] = cover
        return cover
