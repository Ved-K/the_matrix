from __future__ import annotations

from algorithm import SYDNEY_TZ
from reason_library import match_reasons
from models import Teacher, ClassSession
from recommendations_engine import RecommendationResult


def format_cover_header(c: ClassSession) -> str:
    s = c.start_at.astimezone(SYDNEY_TZ)
    e = c.end_at.astimezone(SYDNEY_TZ)
    return f"*{c.class_id}* • {c.campus.title()} • {s:%a %d %b %H:%M}–{e:%H:%M}"


def format_recommendations_message(
    res: RecommendationResult,
    teachers_by_id: dict[str, Teacher],
    classes_by_id: dict[str, ClassSession],
    max_recommended: int = 8,
    max_soft_excluded: int = 5,
) -> str:
    c = classes_by_id[res.class_id]

    lines: list[str] = []
    lines.append("📌 *Cover recommendations*")
    lines.append(format_cover_header(c))
    lines.append("")

    # Recommended
    lines.append("✅ *Recommended*")
    if not res.recommended:
        lines.append("• (none)")
    else:
        for tid in res.recommended[:max_recommended]:
            t = teachers_by_id[tid]
            lines.append(f"• {t.full_name} ({tid})")
    lines.append("")

    # Soft excluded (travel)
    lines.append("🟡 *Eligible but not recommended (travel buffer)*")
    if not res.soft_excluded:
        lines.append("• (none)")
    else:
        shown = 0
        for tid, codes in res.soft_excluded.items():
            if shown >= max_soft_excluded:
                break
            t = teachers_by_id.get(tid)
            name = t.full_name if t else tid
            friendly = match_reasons(codes)[0] if codes else "Not recommended."
            lines.append(f"• {name} ({tid}) — {friendly}")
            shown += 1

    lines.append("")
    lines.append(
        "ℹ️ Teachers can still manually accept if they want (even if not recommended)."
    )
    return "\n".join(lines)
