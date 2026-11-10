"""SQLite persistence (single user)."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .config import get_settings

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_url, connect_args={"check_same_thread": False})
    return _engine


def reset_engine(url: str | None = None):
    """Used by tests."""
    global _engine
    _engine = create_engine(url or get_settings().db_url, connect_args={"check_same_thread": False})
    init_db()
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(engine())


def session() -> Session:
    return Session(engine(), expire_on_commit=False)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))


class PlanRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: dt.datetime = Field(default_factory=utcnow)
    active: bool = True
    goal: dict = Field(sa_column=Column(JSON))
    profile: dict = Field(sa_column=Column(JSON))
    start_vdot: float
    goal_vdot: float
    current_vdot: float
    warnings: list = Field(default_factory=list, sa_column=Column(JSON))


class WeekRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(index=True)
    index: int
    start_date: dt.date
    phase: str
    target_km: float
    is_cutback: bool = False
    vdot: float


class WorkoutRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(index=True)
    week_id: int | None = Field(default=None, index=True)
    date: dt.date = Field(index=True)
    type: str
    title: str
    description: str = ""
    distance_km: float = 0.0
    duration_min: float = 0.0
    steps: list = Field(default_factory=list, sa_column=Column(JSON))
    exercises: list | None = Field(default=None, sa_column=Column(JSON))
    key: bool = False
    status: str = "planned"  # planned/completed/partial/missed/skipped
    rpe: int | None = None
    notes: str | None = None
    activity_id: int | None = None
    analysis: dict | None = Field(default=None, sa_column=Column(JSON))
    garmin_workout_id: str | None = None
    garmin_schedule_id: str | None = None
    coros_workout_id: str | None = None
    synced_hash: str | None = None  # hash of content pushed to watches
    updated_at: dt.datetime = Field(default_factory=utcnow)


class ActivityRow(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source", "external_id"),)
    id: int | None = Field(default=None, primary_key=True)
    source: str  # strava/garmin/coros/apple_health/health_connect/manual/phone
    external_id: str
    start_time: dt.datetime = Field(index=True)  # UTC
    local_date: dt.date = Field(index=True)
    name: str = ""
    sport: str = "run"
    distance_m: float = 0.0
    duration_s: float = 0.0  # moving time
    elapsed_s: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    avg_cadence: float | None = None
    calories: float | None = None
    laps: list = Field(default_factory=list, sa_column=Column(JSON))
    duplicate_of: int | None = None  # set when the same run was imported from another source
    load: float | None = None


class HealthDaily(SQLModel, table=True):
    day: dt.date = Field(primary_key=True)
    resting_hr: float | None = None
    hrv_ms: float | None = None
    sleep_hours: float | None = None
    weight_kg: float | None = None
    source: str | None = None


class AdjustmentRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(index=True)
    created_at: dt.datetime = Field(default_factory=utcnow)
    kind: str
    reason: str
    actions: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "pending"  # pending/applied/dismissed
    requires_confirmation: bool = False


class SyncLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    at: dt.datetime = Field(default_factory=utcnow)
    provider: str
    ok: bool
    message: str = ""


# ---- settings helpers
def get_setting(key: str, default: Any = None) -> Any:
    with session() as s:
        row = s.get(Setting, key)
        return row.value if row else default


def set_setting(key: str, value: Any) -> None:
    with session() as s:
        row = s.get(Setting, key)
        if row:
            row.value = json.loads(json.dumps(value, default=str))
        else:
            row = Setting(key=key, value=json.loads(json.dumps(value, default=str)))
        s.add(row)
        s.commit()


def delete_setting(key: str) -> None:
    with session() as s:
        row = s.get(Setting, key)
        if row:
            s.delete(row)
            s.commit()


def log_sync(provider: str, ok: bool, message: str = "") -> None:
    with session() as s:
        s.add(SyncLog(provider=provider, ok=ok, message=message[:2000]))
        s.commit()


__all__ = ["select"]
