"""Adaptive rules: missed workouts, pace insights, fatigue, breaks and
"not feeling 100%" adjustments.

All functions are pure: they inspect workout states and return a list of
Adjustment objects which the backend applies to the database.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from . import library as L
from .models import PlannedWorkout
from .zones import PaceRange

Status = Literal["planned", "completed", "partial", "missed", "skipped"]


class WorkoutState(BaseModel):
    id: int
    workout: PlannedWorkout
    status: Status = "planned"
    compliance: float | None = None
    rpe: int | None = None
    pace_verdict: str | None = None  # on/fast/slow


class Action(BaseModel):
    op: Literal["move", "drop", "replace", "scale", "regenerate", "set_vdot"]
    workout_id: int | None = None
    to_date: date | None = None
    workout: PlannedWorkout | None = None
    factor: float | None = None
    params: dict = Field(default_factory=dict)


class Adjustment(BaseModel):
    kind: str
    reason: str
    actions: list[Action]
    requires_confirmation: bool = False


def _cyc_gap(a: date, b: date) -> int:
    return abs((a - b).days)


def reschedule_missed(states: list[WorkoutState], today: date) -> list[Adjustment]:
    """Missed key workouts this week are moved to a free day; easy runs are dropped."""
    out: list[Adjustment] = []
    week_end = today + timedelta(days=6 - today.weekday())
    busy = {s.workout.date for s in states if s.status == "planned" and s.workout.date >= today and s.workout.type != "strength"}
    key_dates = {s.workout.date for s in states if s.workout.key and s.status in ("planned", "completed")}
    for s in states:
        if s.status != "planned" or s.workout.date >= today or s.workout.type in ("strength", "rest", "race"):
            continue
        if not s.workout.key:
            out.append(Adjustment(kind="missed_easy", reason=f"Bỏ lỡ '{s.workout.title}' — không cần bù, giữ nguyên các buổi tiếp theo.", actions=[Action(op="drop", workout_id=s.id)]))
            continue
        moved = False
        d = today
        while d <= week_end:
            if d not in busy and all(_cyc_gap(d, k) >= 2 for k in key_dates if k != s.workout.date):
                out.append(
                    Adjustment(
                        kind="missed_key_moved",
                        reason=f"Bỏ lỡ '{s.workout.title}' — đã dời sang {d.strftime('%d/%m')}.",
                        actions=[Action(op="move", workout_id=s.id, to_date=d)],
                    )
                )
                busy.add(d)
                key_dates.discard(s.workout.date)
                key_dates.add(d)
                moved = True
                break
            d += timedelta(days=1)
        if not moved:
            out.append(
                Adjustment(
                    kind="missed_key_dropped",
                    reason=f"Bỏ lỡ '{s.workout.title}' và không còn ngày phù hợp trong tuần — bỏ qua để tránh dồn bài nặng.",
                    actions=[Action(op="drop", workout_id=s.id)],
                )
            )
    return out


def pace_insight(states: list[WorkoutState], vdot: float, window: int = 4) -> Adjustment | None:
    """Suggest +/-1 VDOT when quality sessions are consistently beaten / missed."""
    q = [s for s in states if s.status in ("completed", "partial") and s.workout.key and s.workout.type not in ("long", "race") and s.pace_verdict]
    q.sort(key=lambda s: s.workout.date)
    recent = q[-window:]
    if len(recent) < 3:
        return None
    fast = sum(1 for s in recent if s.pace_verdict == "fast" and (s.rpe is None or s.rpe <= 7))
    slow = sum(1 for s in recent if s.pace_verdict == "slow" and (s.rpe is None or s.rpe >= 7))
    if fast >= 3:
        return Adjustment(
            kind="pace_up",
            reason=f"{fast}/{len(recent)} bài chất lượng gần đây nhanh hơn mục tiêu mà vẫn thoải mái. Đề xuất tăng thể lực (VDOT {vdot:.1f} → {vdot + 1:.1f}).",
            actions=[Action(op="set_vdot", params={"delta": 1.0})],
            requires_confirmation=True,
        )
    if slow >= 3:
        return Adjustment(
            kind="pace_down",
            reason=f"{slow}/{len(recent)} bài chất lượng gần đây chậm hơn mục tiêu và rất nặng. Đề xuất giảm pace (VDOT {vdot:.1f} → {vdot - 1:.1f}).",
            actions=[Action(op="set_vdot", params={"delta": -1.0})],
            requires_confirmation=True,
        )
    return None


def fatigue_adjust(states: list[WorkoutState], today: date, readiness_score: int | None, acwr: float | None, zones: dict[str, PaceRange]) -> list[Adjustment]:
    out: list[Adjustment] = []
    upcoming = sorted([s for s in states if s.status == "planned" and today <= s.workout.date <= today + timedelta(days=2)], key=lambda s: s.workout.date)
    if readiness_score is not None and readiness_score < 45:
        for s in upcoming:
            if s.workout.key and s.workout.type not in ("long", "race"):
                km = max(3.0, round(s.workout.distance_km * 0.7))
                out.append(
                    Adjustment(
                        kind="low_readiness",
                        reason=f"Chỉ số sẵn sàng thấp ({readiness_score}). Đổi '{s.workout.title}' thành chạy nhẹ {km:g} km.",
                        actions=[Action(op="replace", workout_id=s.id, workout=L.easy(s.workout.date, km, zones))],
                        requires_confirmation=True,
                    )
                )
                break
    if acwr is not None and acwr > 1.5:
        ids = [s.id for s in states if s.status == "planned" and today <= s.workout.date <= today + timedelta(days=6) and s.workout.type not in ("race", "strength")]
        if ids:
            out.append(
                Adjustment(
                    kind="load_spike",
                    reason=f"Tải 7 ngày cao hơn nhiều so với 4 tuần (ACWR {acwr}). Giảm 20% khối lượng tuần tới để tránh chấn thương.",
                    actions=[Action(op="scale", workout_id=i, factor=0.8) for i in ids],
                    requires_confirmation=True,
                )
            )
    return out


def detect_break(last_run: date | None, today: date) -> Adjustment | None:
    if last_run is None:
        return None
    gap = (today - last_run).days
    if gap < 7:
        return None
    if gap < 14:
        vol, dv = 0.8, 0.0
    elif gap < 28:
        vol, dv = 0.6, -1.0
    else:
        vol, dv = 0.5, -2.5
    return Adjustment(
        kind="break",
        reason=f"Bạn đã nghỉ {gap} ngày. Tính lại giáo án từ hôm nay với khối lượng {int(vol * 100)}% và pace phù hợp hơn.",
        actions=[Action(op="regenerate", params={"volume_factor": vol, "vdot_delta": dv})],
        requires_confirmation=True,
    )


def not_feeling_100(states: list[WorkoutState], today: date, reason: Literal["sick", "niggle", "busy", "tired"], days: int, zones) -> Adjustment:
    window = [s for s in states if s.status == "planned" and today <= s.workout.date < today + timedelta(days=days) and s.workout.type != "race"]
    actions: list[Action] = []
    if reason == "sick":
        for s in window:
            actions.append(Action(op="drop", workout_id=s.id))
        # first days back: easy only
        after = [s for s in states if s.status == "planned" and today + timedelta(days=days) <= s.workout.date < today + timedelta(days=days + 4)]
        for s in after:
            if s.workout.key and s.workout.type != "race":
                actions.append(Action(op="replace", workout_id=s.id, workout=L.easy(s.workout.date, max(3.0, round(s.workout.distance_km * 0.6)), zones)))
        msg = f"Nghỉ {days} ngày để khỏi ốm. Sau đó 3–4 ngày chỉ chạy nhẹ rồi quay lại giáo án."
    elif reason == "niggle":
        for s in window:
            if s.workout.type == "strength":
                continue
            actions.append(Action(op="replace", workout_id=s.id, workout=L.easy(s.workout.date, max(3.0, round(s.workout.distance_km * 0.5)), zones, recovery=True)))
        msg = f"Đau nhẹ: {days} ngày tới chỉ chạy hồi phục ngắn (hoặc đạp xe/bơi). Đau tăng khi chạy → dừng và gặp bác sĩ."
    elif reason == "busy":
        for s in window:
            if s.workout.type == "strength":
                actions.append(Action(op="drop", workout_id=s.id))
            elif not s.workout.key:
                actions.append(Action(op="scale", workout_id=s.id, factor=0.6))
            else:
                actions.append(Action(op="scale", workout_id=s.id, factor=0.8))
        msg = f"Bận rộn: {days} ngày tới rút ngắn các buổi, giữ lại phần chính của bài quan trọng."
    else:  # tired
        for s in window:
            if s.workout.key and s.workout.type not in ("long",):
                actions.append(Action(op="replace", workout_id=s.id, workout=L.easy(s.workout.date, max(3.0, round(s.workout.distance_km * 0.7)), zones)))
            elif s.workout.type == "long":
                actions.append(Action(op="scale", workout_id=s.id, factor=0.8))
        msg = f"Mệt mỏi: {days} ngày tới bỏ bài nặng, chạy nhẹ để hồi phục."
    return Adjustment(kind=f"nf100_{reason}", reason=msg, actions=actions)


def scale_workout(w: PlannedWorkout, factor: float, zones) -> PlannedWorkout:
    """Scale a workout's volume while keeping its structure."""
    new = w.model_copy(deep=True)

    def sc(steps):
        for s in steps:
            if s.kind == "repeat":
                if s.repeats and s.repeats > 2:
                    s.repeats = max(2, round(s.repeats * factor))
                continue
            if s.kind in ("warmup", "cooldown"):
                continue
            if s.distance_m:
                s.distance_m = round(s.distance_m * factor / 100) * 100
            if s.duration_s:
                s.duration_s = round(s.duration_s * factor / 30) * 30

    sc(new.steps)
    L.finalize(new, zones)
    if new.type in ("easy", "recovery", "long"):
        prefix = new.title.rsplit(" ", 2)[0] if new.title.endswith("km") else new.title
        new.title = f"{prefix} {new.distance_km:g} km" if new.title.endswith("km") else new.title
    return new
