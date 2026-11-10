from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from ..engine.models import Goal, RunnerProfile


class CreatePlanIn(BaseModel):
    goal: Goal
    profile: RunnerProfile


class WorkoutPatch(BaseModel):
    date: dt.date | None = None
    status: Literal["planned", "completed", "partial", "missed", "skipped"] | None = None
    rpe: int | None = Field(None, ge=1, le=10)
    notes: str | None = None


class NotFeeling100In(BaseModel):
    reason: Literal["sick", "niggle", "busy", "tired"]
    days: int = Field(3, ge=1, le=14)


class HealthWorkoutIn(BaseModel):
    source: Literal["apple_health", "health_connect"]
    external_id: str
    start_time: dt.datetime
    end_time: dt.datetime | None = None
    distance_m: float = 0.0
    duration_s: float
    sport: str = "run"
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    calories: float | None = None
    laps: list[dict] = []
    name: str = ""


class HealthDailyIn(BaseModel):
    day: dt.date
    resting_hr: float | None = None
    hrv_ms: float | None = None
    sleep_hours: float | None = None
    weight_kg: float | None = None
    source: str = "apple_health"


class HealthBatchIn(BaseModel):
    workouts: list[HealthWorkoutIn] = []
    daily: list[HealthDailyIn] = []


class ManualActivityIn(BaseModel):
    start_time: dt.datetime
    distance_m: float
    duration_s: float
    avg_hr: float | None = None
    rpe: int | None = Field(None, ge=1, le=10)
    workout_id: int | None = None
    laps: list[dict] = []
    source: Literal["manual", "phone"] = "manual"
    name: str = ""


class GarminLoginIn(BaseModel):
    email: str | None = None
    password: str | None = None


class MfaIn(BaseModel):
    code: str


class ChatIn(BaseModel):
    messages: list[dict]


class SettingsIn(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    preferred_run_hour: int | None = Field(None, ge=0, le=23)
    heat_adjust: bool | None = None


class GoalUpdateIn(BaseModel):
    target_time_s: float | None = None
    race_date: dt.date | None = None
