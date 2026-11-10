"""Plan persistence and adjustment application."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from sqlmodel import select

from ..db import ActivityRow, AdjustmentRow, PlanRow, WeekRow, WorkoutRow, session, utcnow
from ..engine import adapt
from ..engine.generator import generate_plan, monday
from ..engine.models import Goal, PlannedWorkout, RunnerProfile
from ..engine.zones import pace_zones


def to_planned(w: WorkoutRow) -> PlannedWorkout:
    return PlannedWorkout(
        date=w.date,
        type=w.type,  # type: ignore[arg-type]
        title=w.title,
        description=w.description,
        distance_km=w.distance_km,
        duration_min=w.duration_min,
        steps=w.steps or [],
        key=w.key,
        exercises=w.exercises,
    )


def content_hash(w: WorkoutRow) -> str:
    payload = json.dumps([str(w.date), w.type, w.title, w.steps], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


def _apply_planned(row: WorkoutRow, pw: PlannedWorkout) -> None:
    row.date = pw.date
    row.type = pw.type
    row.title = pw.title
    row.description = pw.description
    row.distance_km = pw.distance_km
    row.duration_min = pw.duration_min
    row.steps = [s.model_dump(exclude_none=True) for s in pw.steps]
    row.exercises = pw.exercises
    row.key = pw.key
    row.updated_at = utcnow()


def active_plan() -> PlanRow | None:
    with session() as s:
        return s.exec(select(PlanRow).where(PlanRow.active == True).order_by(PlanRow.id.desc())).first()  # noqa: E712


def _insert_weeks(s, plan_id: int, weeks, index_offset: int = 0, from_date: dt.date | None = None) -> None:
    for wk in weeks:
        wr = WeekRow(
            plan_id=plan_id,
            index=wk.index + index_offset,
            start_date=wk.start_date,
            phase=wk.phase,
            target_km=wk.target_km,
            is_cutback=wk.is_cutback,
            vdot=wk.vdot,
        )
        s.add(wr)
        s.flush()
        for w in wk.workouts:
            if from_date and w.date < from_date:
                continue
            row = WorkoutRow(plan_id=plan_id, week_id=wr.id, date=w.date, type=w.type, title=w.title)
            _apply_planned(row, w)
            s.add(row)


def create_plan(goal: Goal, profile: RunnerProfile) -> PlanRow:
    plan = generate_plan(goal, profile)
    with session() as s:
        for old in s.exec(select(PlanRow).where(PlanRow.active == True)).all():  # noqa: E712
            old.active = False
            s.add(old)
        row = PlanRow(
            goal=json.loads(goal.model_dump_json()),
            profile=json.loads(profile.model_dump_json()),
            start_vdot=plan.start_vdot,
            goal_vdot=plan.goal_vdot,
            current_vdot=plan.start_vdot,
            warnings=plan.warnings,
        )
        s.add(row)
        s.flush()
        _insert_weeks(s, row.id, plan.weeks)  # type: ignore[arg-type]
        s.commit()
        s.refresh(row)
        return row


def recent_weekly_km(today: dt.date, weeks: int = 3) -> float | None:
    start = today - dt.timedelta(days=7 * weeks)
    with session() as s:
        acts = s.exec(
            select(ActivityRow).where(ActivityRow.local_date >= start, ActivityRow.local_date < today, ActivityRow.duplicate_of == None, ActivityRow.sport == "run")  # noqa: E711
        ).all()
    if not acts:
        return None
    return sum(a.distance_m for a in acts) / 1000 / weeks


def regenerate(plan: PlanRow, today: dt.date, volume_factor: float = 1.0, vdot_delta: float = 0.0, reason: str = "") -> PlanRow:
    """Rebuild the plan from `today` on, keeping history before today."""
    goal = Goal(**plan.goal)
    profile = RunnerProfile(**plan.profile)
    km = recent_weekly_km(today)
    if km is not None:
        profile.current_weekly_km = max(5.0, km)
    profile.current_weekly_km = round(profile.current_weekly_km * volume_factor, 1)
    if goal.race_date and goal.race_date < today:
        raise ValueError("Ngày thi đã qua — hãy tạo mục tiêu mới.")
    new_vdot = plan.current_vdot + vdot_delta
    goal_for_new = goal.model_copy(update={"start_date": today})
    new = generate_plan(goal_for_new, profile, vdot_override=new_vdot)
    wk_start = monday(today)
    with session() as s:
        p = s.get(PlanRow, plan.id)
        assert p is not None
        old_future = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == p.id, WorkoutRow.date >= today, WorkoutRow.status == "planned")).all()
        for w in old_future:
            s.delete(w)
        old_weeks = s.exec(select(WeekRow).where(WeekRow.plan_id == p.id, WeekRow.start_date >= wk_start)).all()
        offset = min((w.index for w in old_weeks), default=len(s.exec(select(WeekRow).where(WeekRow.plan_id == p.id)).all()))
        for w in old_weeks:
            s.delete(w)
        s.flush()
        _insert_weeks(s, p.id, new.weeks, index_offset=offset, from_date=today)  # type: ignore[arg-type]
        # keep completed workouts of the current week attached to the new week row
        new_week = s.exec(select(WeekRow).where(WeekRow.plan_id == p.id, WeekRow.start_date == wk_start)).first()
        if new_week:
            for w in s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == p.id, WorkoutRow.date >= wk_start, WorkoutRow.date < today)).all():
                w.week_id = new_week.id
                s.add(w)
        p.current_vdot = round(new_vdot, 1)
        p.goal_vdot = max(p.goal_vdot, new.goal_vdot)
        p.profile = json.loads(profile.model_dump_json())
        p.warnings = new.warnings
        s.add(p)
        s.commit()
        s.refresh(p)
        return p


def states(plan_id: int) -> list[adapt.WorkoutState]:
    with session() as s:
        rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == plan_id).order_by(WorkoutRow.date)).all()
    out = []
    for r in rows:
        status = r.status if r.status in ("planned", "completed", "partial", "missed", "skipped") else "planned"
        out.append(
            adapt.WorkoutState(
                id=r.id,  # type: ignore[arg-type]
                workout=to_planned(r),
                status=status,  # type: ignore[arg-type]
                compliance=(r.analysis or {}).get("compliance"),
                rpe=r.rpe,
                pace_verdict=(r.analysis or {}).get("pace_vs_target"),
            )
        )
    return out


def record_adjustment(plan_id: int, adj: adapt.Adjustment, auto_apply: bool, today: dt.date) -> AdjustmentRow | None:
    """Store an adjustment (de-duplicated) and apply it immediately when allowed."""
    actions = [json.loads(a.model_dump_json()) for a in adj.actions]
    with session() as s:
        recent = s.exec(
            select(AdjustmentRow).where(AdjustmentRow.plan_id == plan_id, AdjustmentRow.kind == adj.kind, AdjustmentRow.created_at >= utcnow() - dt.timedelta(days=3))
        ).all()
        for r in recent:
            if r.actions == actions or (r.status == "pending" and adj.kind in ("pace_up", "pace_down", "break", "load_spike")):
                return None
        row = AdjustmentRow(plan_id=plan_id, kind=adj.kind, reason=adj.reason, actions=actions, requires_confirmation=adj.requires_confirmation)
        s.add(row)
        s.commit()
        s.refresh(row)
    if auto_apply and not adj.requires_confirmation:
        apply_adjustment(row.id, today)  # type: ignore[arg-type]
    return row


def apply_adjustment(adjustment_id: int, today: dt.date) -> AdjustmentRow:
    with session() as s:
        adj = s.get(AdjustmentRow, adjustment_id)
        if adj is None:
            raise KeyError(adjustment_id)
        if adj.status != "pending":
            return adj
        plan = s.get(PlanRow, adj.plan_id)
    assert plan is not None
    zones = pace_zones(plan.current_vdot)
    for a in adj.actions:
        action = adapt.Action(**a)
        if action.op == "regenerate":
            regenerate(plan, today, volume_factor=action.params.get("volume_factor", 1.0), vdot_delta=action.params.get("vdot_delta", 0.0))
            continue
        if action.op == "set_vdot":
            regenerate(plan, today, vdot_delta=action.params.get("delta", 0.0))
            continue
        with session() as s:
            row = s.get(WorkoutRow, action.workout_id)
            if row is None:
                continue
            if action.op == "move" and action.to_date:
                row.date = action.to_date
            elif action.op == "drop":
                row.status = "missed" if row.date < today else "skipped"
            elif action.op == "replace" and action.workout:
                _apply_planned(row, action.workout)
            elif action.op == "scale" and action.factor:
                _apply_planned(row, adapt.scale_workout(to_planned(row), action.factor, zones))
            row.updated_at = utcnow()
            s.add(row)
            s.commit()
    with session() as s:
        adj = s.get(AdjustmentRow, adjustment_id)
        adj.status = "applied"  # type: ignore[union-attr]
        s.add(adj)
        s.commit()
        s.refresh(adj)
        return adj  # type: ignore[return-value]
