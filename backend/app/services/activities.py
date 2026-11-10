"""Activity ingestion: de-duplication across sources, matching to the plan,
post-run analysis and the daily adaptation pass."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import select

from ..config import get_settings
from ..db import ActivityRow, PlanRow, WorkoutRow, session, utcnow
from ..engine import adapt
from ..engine.analysis import ActualRun, Lap, analyze
from ..engine.load import ActivityLoadInput, activity_load
from ..engine.zones import pace_zones
from . import plans as plan_svc

# lower number wins when the same run arrives from several sources
SOURCE_PRIORITY = {"garmin": 0, "coros": 1, "strava": 2, "apple_health": 3, "health_connect": 4, "phone": 5, "manual": 6}


def local_date(start_utc: dt.datetime) -> dt.date:
    tz = ZoneInfo(get_settings().timezone)
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=dt.UTC)
    return start_utc.astimezone(tz).date()


def _profile_hr() -> tuple[float | None, float | None]:
    plan = plan_svc.active_plan()
    if not plan:
        return None, None
    return plan.profile.get("resting_hr"), plan.profile.get("max_hr")


def current_vdot() -> float:
    plan = plan_svc.active_plan()
    return plan.current_vdot if plan else 40.0


def upsert_activity(
    *,
    source: str,
    external_id: str,
    start_time: dt.datetime,
    distance_m: float,
    duration_s: float,
    sport: str = "run",
    name: str = "",
    elapsed_s: float | None = None,
    avg_hr: float | None = None,
    max_hr: float | None = None,
    elevation_gain_m: float | None = None,
    avg_cadence: float | None = None,
    calories: float | None = None,
    laps: list[dict] | None = None,
    analyze_now: bool = True,
) -> ActivityRow:
    start_time = start_time.replace(tzinfo=dt.UTC) if start_time.tzinfo is None else start_time.astimezone(dt.UTC)
    rest_hr, mx = _profile_hr()
    with session() as s:
        row = s.exec(select(ActivityRow).where(ActivityRow.source == source, ActivityRow.external_id == str(external_id))).first()
        if row is None:
            row = ActivityRow(source=source, external_id=str(external_id), start_time=start_time, local_date=local_date(start_time))
        row.start_time = start_time
        row.local_date = local_date(start_time)
        row.name = name or row.name
        row.sport = sport
        row.distance_m = distance_m
        row.duration_s = duration_s
        row.elapsed_s = elapsed_s
        row.avg_hr = avg_hr
        row.max_hr = max_hr
        row.elevation_gain_m = elevation_gain_m
        row.avg_cadence = avg_cadence
        row.calories = calories
        if laps:
            row.laps = laps
        threshold = pace_zones(current_vdot())["threshold"].mid
        row.load = round(
            activity_load(ActivityLoadInput(day=row.local_date, duration_s=duration_s, distance_m=distance_m, avg_hr=avg_hr, elevation_gain_m=elevation_gain_m), threshold, rest_hr, mx),
            1,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
    _dedupe(row)
    if analyze_now and row.sport == "run":
        match_and_analyze(row.id)  # type: ignore[arg-type]
    with session() as s:
        return s.get(ActivityRow, row.id)  # type: ignore[return-value]


def _dedupe(row: ActivityRow) -> None:
    """Mark the same physical run coming from different sources."""
    with session() as s:
        window = dt.timedelta(minutes=5)
        others = s.exec(
            select(ActivityRow).where(
                ActivityRow.id != row.id,
                ActivityRow.source != row.source,
                ActivityRow.start_time >= row.start_time - window,
                ActivityRow.start_time <= row.start_time + window,
            )
        ).all()
        group = [row] + [o for o in others if o.distance_m == 0 or row.distance_m == 0 or abs(o.distance_m - row.distance_m) / max(o.distance_m, row.distance_m) < 0.1]
        if len(group) == 1:
            return
        group = [s.get(ActivityRow, g.id) for g in group]
        primary = min(group, key=lambda a: (SOURCE_PRIORITY.get(a.source, 9), a.id))
        for g in group:
            new_dup = None if g.id == primary.id else primary.id
            if g.duplicate_of != new_dup:
                g.duplicate_of = new_dup
                s.add(g)
        # move workout link to primary
        for w in s.exec(select(WorkoutRow).where(WorkoutRow.activity_id.in_([g.id for g in group if g.id != primary.id]))).all():  # type: ignore[union-attr]
            w.activity_id = primary.id
            s.add(w)
        # copy laps to primary if it has none
        if not primary.laps:
            donor = next((g for g in group if g.laps), None)
            if donor:
                primary.laps = donor.laps
                s.add(primary)
        s.commit()


def match_and_analyze(activity_id: int) -> WorkoutRow | None:
    with session() as s:
        act = s.get(ActivityRow, activity_id)
        if act is None or act.sport != "run":
            return None
        if act.duplicate_of:
            act = s.get(ActivityRow, act.duplicate_of)
        plan = s.exec(select(PlanRow).where(PlanRow.active == True)).first()  # noqa: E712
        if plan is None:
            return None
        linked = s.exec(select(WorkoutRow).where(WorkoutRow.activity_id == act.id)).first()
        if linked:
            cand = linked
        else:
            cands = s.exec(
                select(WorkoutRow).where(
                    WorkoutRow.plan_id == plan.id,
                    WorkoutRow.date == act.local_date,
                    WorkoutRow.type != "strength",
                    WorkoutRow.activity_id == None,  # noqa: E711
                )
            ).all()
            if not cands:
                return None
            cand = min(cands, key=lambda w: abs(w.distance_km * 1000 - act.distance_m))
        pw = plan_svc.to_planned(cand)
        run = ActualRun(
            distance_m=act.distance_m,
            duration_s=act.duration_s,
            avg_hr=act.avg_hr,
            max_hr=act.max_hr,
            laps=[Lap(**{k: v for k, v in lap.items() if k in ("distance_m", "duration_s", "avg_hr")}) for lap in (act.laps or []) if lap.get("distance_m") and lap.get("duration_s")],
            rpe=cand.rpe,
        )
        res = analyze(pw, run)
        cand.activity_id = act.id
        cand.analysis = res.model_dump()
        cand.status = "completed" if res.compliance >= 0.7 else "partial"
        cand.updated_at = utcnow()
        s.add(cand)
        s.commit()
        s.refresh(cand)
        return cand


def daily_maintenance(today: dt.date | None = None) -> list[int]:
    """Runs after each sync: missed workouts, breaks, pace insights, fatigue."""
    from . import metrics  # avoid cycle

    today = today or dt.datetime.now(ZoneInfo(get_settings().timezone)).date()
    plan = plan_svc.active_plan()
    if plan is None:
        return []
    created: list[int] = []
    sts = plan_svc.states(plan.id)  # type: ignore[arg-type]

    with session() as s:
        last = s.exec(select(ActivityRow).where(ActivityRow.sport == "run", ActivityRow.duplicate_of == None).order_by(ActivityRow.start_time.desc())).first()  # noqa: E711
    plan_start = dt.date.fromisoformat(plan.goal["start_date"])
    last_run = last.local_date if last else None
    if last_run is None or last_run < plan_start:
        last_run = plan_start if (today - plan_start).days >= 7 else None
    brk = adapt.detect_break(last_run, today)
    if brk:
        r = plan_svc.record_adjustment(plan.id, brk, auto_apply=False, today=today)  # type: ignore[arg-type]
        if r:
            created.append(r.id)  # type: ignore[arg-type]
    else:
        for adj in adapt.reschedule_missed(sts, today):
            r = plan_svc.record_adjustment(plan.id, adj, auto_apply=True, today=today)  # type: ignore[arg-type]
            if r:
                created.append(r.id)  # type: ignore[arg-type]

    sts = plan_svc.states(plan.id)  # type: ignore[arg-type]
    pi = adapt.pace_insight(sts, plan.current_vdot)
    if pi:
        r = plan_svc.record_adjustment(plan.id, pi, auto_apply=False, today=today)  # type: ignore[arg-type]
        if r:
            created.append(r.id)  # type: ignore[arg-type]

    snap = metrics.snapshot(today)
    for adj in adapt.fatigue_adjust(sts, today, snap["readiness"]["score"], snap["acwr"], pace_zones(plan.current_vdot)):
        r = plan_svc.record_adjustment(plan.id, adj, auto_apply=False, today=today)  # type: ignore[arg-type]
        if r:
            created.append(r.id)  # type: ignore[arg-type]
    return created
