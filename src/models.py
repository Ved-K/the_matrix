from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EmploymentType = Literal["CASUAL", "PART_TIME", "FULL_TIME"]
Campus = Literal["parramatta", "strathfield", "chatswood", "epping"]
Subject = Literal["MAT", "MADV", "MAS", "MX1", "MX2"]

# minutes since midnight
Minute = int
TimeRange = tuple[Minute, Minute]  # (start_min, end_min)

Day = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
Availability = dict[Day, list[TimeRange]]


@dataclass(frozen=True)
class Teacher:
    teacher_id: str
    full_name: str
    slack_user_id: str | None
    employment_type: EmploymentType
    primary_campus: Campus
    campuses: set[Campus]
    subjects: set[Subject]
    year_levels: set[int]
    availability: Availability
    teaching_hours: float
    max_covers_per_week: int


@dataclass(frozen=True)
class ClassSession:
    class_id: str
    class_name: str
    subject: Subject
    year_level: int
    campus: Campus
    start_at: datetime
    end_at: datetime
    regular_teacher_id: str | None
