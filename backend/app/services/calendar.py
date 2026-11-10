"""iCalendar feed so the plan shows up in the phone's calendar."""

from __future__ import annotations

import datetime as dt

from sqlmodel import select

from ..db import WorkoutRow, session
from . import plans as plan_svc


def _esc(s: str) -> str:
    for a, b in (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")):
        s = s.replace(a, b)
    return s


def ics() -> str:
    plan = plan_svc.active_plan()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//runners//plan//VI", "X-WR-CALNAME:Giáo án chạy bộ", "CALSCALE:GREGORIAN"]
    if plan:
        with session() as s:
            rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == plan.id, WorkoutRow.status.in_(["planned", "completed", "partial"]))).all()  # type: ignore[attr-defined]
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        for w in rows:
            d = w.date.strftime("%Y%m%d")
            end = (w.date + dt.timedelta(days=1)).strftime("%Y%m%d")
            summary = ("✅ " if w.status != "planned" else "") + w.title
            lines += [
                "BEGIN:VEVENT",
                f"UID:workout-{w.id}@runners",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{d}",
                f"DTEND;VALUE=DATE:{end}",
                f"SUMMARY:{_esc(summary)}",
                f"DESCRIPTION:{_esc(w.description)}",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
