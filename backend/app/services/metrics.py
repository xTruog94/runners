"""Fitness/fatigue, readiness, weekly volumes, predictions."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from statistics import mean

from sqlmodel import select

from ..db import ActivityRow, HealthDaily, WeekRow, WorkoutRow, session
from ..engine.fitness import RunSample, estimate_vdot, predictions
from ..engine.generator import monday
from ..engine.load import acwr, load_series, readiness
from . import plans as plan_svc


def _activities(since: dt.date) -> list[ActivityRow]:
    with session() as s:
        return list(s.exec(select(ActivityRow).where(ActivityRow.local_date >= since, ActivityRow.duplicate_of == None)).all())  # noqa: E711


def daily_loads(since: dt.date) -> dict[dt.date, float]:
    out: dict[dt.date, float] = defaultdict(float)
    for a in _activities(since):
        out[a.local_date] += a.load or 0.0
    return dict(out)


def snapshot(today: dt.date) -> dict:
    since = today - dt.timedelta(days=120)
    daily = daily_loads(since)
    series = load_series(daily, since, today)
    last = series[-1]
    ac = acwr(daily, today)
    with session() as s:
        hd = list(s.exec(select(HealthDaily).where(HealthDaily.day >= today - dt.timedelta(days=30))).all())
    by_day = {h.day: h for h in hd}
    t = by_day.get(today) or by_day.get(today - dt.timedelta(days=1))

    def base(attr):
        vals = [getattr(h, attr) for h in hd if getattr(h, attr) and h.day < today]
        return mean(vals) if len(vals) >= 5 else None

    plan = plan_svc.active_plan()
    recent_rpe = None
    if plan:
        with session() as s:
            rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == plan.id, WorkoutRow.rpe != None, WorkoutRow.date >= today - dt.timedelta(days=5))).all()  # noqa: E711
        if rows:
            recent_rpe = mean(r.rpe for r in rows)  # type: ignore[misc]
    rd = readiness(
        tsb=last.tsb,
        acwr_value=ac,
        resting_hr_today=t.resting_hr if t else None,
        resting_hr_baseline=base("resting_hr"),
        hrv_today=t.hrv_ms if t else None,
        hrv_baseline=base("hrv_ms"),
        sleep_hours=t.sleep_hours if t else None,
        recent_rpe=recent_rpe,
    )
    return {"ctl": last.ctl, "atl": last.atl, "tsb": last.tsb, "acwr": ac, "readiness": rd.model_dump(), "series": [p.model_dump() for p in series[-90:]]}


def weekly_volumes(today: dt.date, weeks: int = 12) -> list[dict]:
    start = monday(today) - dt.timedelta(weeks=weeks - 1)
    acts = [a for a in _activities(start) if a.sport == "run"]
    actual: dict[dt.date, float] = defaultdict(float)
    for a in acts:
        actual[monday(a.local_date)] += a.distance_m / 1000
    planned: dict[dt.date, float] = {}
    plan = plan_svc.active_plan()
    if plan:
        with session() as s:
            for w in s.exec(select(WeekRow).where(WeekRow.plan_id == plan.id, WeekRow.start_date >= start)).all():
                planned[w.start_date] = w.target_km
    out = []
    for i in range(weeks):
        d = start + dt.timedelta(weeks=i)
        out.append({"week_start": d.isoformat(), "actual_km": round(actual.get(d, 0.0), 1), "planned_km": planned.get(d)})
    return out


def fitness(today: dt.date) -> dict:
    plan = plan_svc.active_plan()
    vdot = plan.current_vdot if plan else None
    rest = plan.profile.get("resting_hr") if plan else None
    mx = plan.profile.get("max_hr") if plan else None
    runs = [a for a in _activities(today - dt.timedelta(days=42)) if a.sport == "run"]
    est = estimate_vdot([RunSample(distance_m=a.distance_m, duration_s=a.duration_s, avg_hr=a.avg_hr) for a in runs], rest, mx)
    with session() as s:
        done = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == (plan.id if plan else -1))).all()
    total = [w for w in done if w.date < today and w.type not in ("strength", "rest")]
    completed = [w for w in total if w.status in ("completed", "partial")]
    return {
        "plan_vdot": vdot,
        "hr_estimated_vdot": est,
        "predictions": [p.model_dump() for p in predictions(est or vdot)] if (est or vdot) else [],
        "completion_rate": round(len(completed) / len(total), 2) if total else None,
        "runs_last_6_weeks": len(runs),
    }
