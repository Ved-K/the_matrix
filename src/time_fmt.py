from __future__ import annotations
from zoneinfo import ZoneInfo

SYD = ZoneInfo("Australia/Sydney")


def fmt_local_range(start_utc, end_utc) -> str:
    s = start_utc.astimezone(SYD)
    e = end_utc.astimezone(SYD)

    # Same day: "Sun 11 Jan 09:00–12:00"
    if s.date() == e.date():
        return f"{s:%a %d %b %H:%M}–{e:%H:%M}"
    # crosses midnight
    return f"{s:%a %d %b %H:%M}–{e:%a %d %b %H:%M}"
