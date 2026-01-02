from __future__ import annotations

from datetime import datetime
import pandas as pd


def split_pipe(s: str) -> list[str]:
    return [x.strip() for x in str(s).split("|") if x.strip()]


def parse_int_set_pipe(s: str) -> set[int]:
    out: set[int] = set()
    for x in split_pipe(s):
        out.add(int(x))
    return out


def hhmm_to_min(t: str) -> int:
    hh, mm = t.split(":")
    return int(hh) * 60 + int(mm)


def parse_availability_weekly(s: str) -> dict[str, list[tuple[int, int]]]:
    """
    Format:
      Mon:13:00-19:30;Sat:09:00-12:00|13:00-16:00
    Returns:
      {"Mon":[(780,1170)], "Sat":[(540,720),(780,960)]}
    """
    avail: dict[str, list[tuple[int, int]]] = {}
    if not str(s).strip():
        return avail

    day_chunks = [c.strip() for c in str(s).split(";") if c.strip()]
    for chunk in day_chunks:
        day, ranges_str = chunk.split(":", 1)
        day = day.strip()
        ranges = []
        for r in ranges_str.split("|"):
            r = r.strip()
            start_s, end_s = r.split("-", 1)
            start_m = hhmm_to_min(start_s.strip())
            end_m = hhmm_to_min(end_s.strip())
            if end_m <= start_m:
                raise ValueError(f"Invalid range {day}:{r} (end <= start)")
            ranges.append((start_m, end_m))
        avail[day] = ranges

    return avail


def parse_rfc3339(dt: str) -> datetime:
    # pandas handles RFC3339 well; keep it simple for MVP
    return pd.to_datetime(dt, utc=True).to_pydatetime()
