"""Pure data models used by the training engine (no database dependency)."""

from __future__ import annotations

import datetime as dt
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

GoalDistance = Literal["5k", "10k", "half", "marathon", "general"]
Level = Literal["beginner", "intermediate", "advanced"]
WorkoutType = Literal[
    "easy",
    "recovery",
    "long",
    "tempo",
    "intervals",
    "fartlek",
    "hills",
    "progression",
    "race_pace",
    "shakeout",
    "race",
    "strength",
    "rest",
]
QUALITY_TYPES = {"tempo", "intervals", "fartlek", "hills", "progression", "race_pace"}


class Target(BaseModel):
    zone: str | None = None
    fast_s_per_km: float | None = None
    slow_s_per_km: float | None = None


class Step(BaseModel):
    kind: Literal["warmup", "run", "recovery", "cooldown", "repeat"]
    distance_m: float | None = None
    duration_s: float | None = None
    target: Target | None = None
    repeats: int | None = None
    steps: list[Step] | None = None
    note: str | None = None


class PlannedWorkout(BaseModel):
    date: dt.date
    type: WorkoutType
    title: str
    description: str = ""
    distance_km: float = 0.0
    duration_min: float = 0.0
    steps: list[Step] = Field(default_factory=list)
    key: bool = False  # quality/long session that matters most
    exercises: list[dict] | None = None  # for strength sessions


class PlannedWeek(BaseModel):
    index: int
    start_date: date
    phase: Literal["base", "build", "peak", "taper", "maintain"]
    target_km: float
    is_cutback: bool = False
    vdot: float
    workouts: list[PlannedWorkout] = Field(default_factory=list)

    @property
    def planned_km(self) -> float:
        return round(sum(w.distance_km for w in self.workouts), 1)


class RecentRace(BaseModel):
    distance_m: float
    time_s: float
    date: dt.date | None = None


class RunnerProfile(BaseModel):
    level: Level = "intermediate"
    current_weekly_km: float = 20.0
    longest_recent_run_km: float | None = None
    days_per_week: int = Field(4, ge=2, le=7)
    available_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0 = Monday
    long_run_day: int = 6
    recent_race: RecentRace | None = None
    easy_pace_s_per_km: float | None = None
    age: int | None = None
    max_hr: int | None = None
    resting_hr: int | None = None
    include_strength: bool = True
    strides: bool = True


class Goal(BaseModel):
    distance: GoalDistance = "half"
    race_date: date | None = None
    target_time_s: float | None = None
    start_date: date
    name: str | None = None


class Plan(BaseModel):
    goal: Goal
    profile: RunnerProfile
    start_vdot: float
    goal_vdot: float
    weeks: list[PlannedWeek]
    warnings: list[str] = Field(default_factory=list)

    def all_workouts(self) -> list[PlannedWorkout]:
        return [w for wk in self.weeks for w in wk.workouts]
