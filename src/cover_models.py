from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CoverStatus = Literal["OPEN", "FILLED", "CANCELLED"]


@dataclass
class CoverRequest:
    cover_id: str
    class_id: str
    cover_date: str
    status: CoverStatus
    created_at: datetime

    filled_at: datetime | None = None
    assigned_teacher_id: str | None = None
