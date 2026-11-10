"""Human-readable rendering of workout steps (Vietnamese)."""

from __future__ import annotations

from .zones import fmt_pace

KIND_VI = {"warmup": "Khởi động", "run": "Chạy", "recovery": "Hồi phục", "cooldown": "Thả lỏng"}


def _amount(s: dict) -> str:
    if s.get("distance_m"):
        d = s["distance_m"]
        return f"{d / 1000:g} km" if d >= 1000 else f"{d:g} m"
    if s.get("duration_s"):
        t = int(s["duration_s"])
        return f"{t // 60} phút" + (f" {t % 60}s" if t % 60 else "") if t >= 60 else f"{t}s"
    return "tùy ý"


def step_line(s: dict) -> str:
    tgt = s.get("target") or {}
    pace = f" @ {fmt_pace(tgt['fast_s_per_km'])}–{fmt_pace(tgt['slow_s_per_km'])}" if tgt.get("fast_s_per_km") else ""
    note = f" ({s['note']})" if s.get("note") else ""
    return f"{KIND_VI.get(s['kind'], s['kind'])} {_amount(s)}{pace}{note}"


def steps_text(steps: list[dict]) -> str:
    lines = []
    for s in steps:
        if s.get("kind") == "repeat":
            inner = " + ".join(step_line(c) for c in s.get("steps") or [])
            lines.append(f"{s.get('repeats', 1)} x [{inner}]")
        else:
            lines.append(step_line(s))
    return "\n".join(lines)
