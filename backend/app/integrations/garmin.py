"""Garmin Connect via the community `garminconnect` library (unofficial).

Garmin's official APIs are for approved business partners only, so for a
personal app we use the same private endpoints as the Garmin Connect website.
They can change without notice; everything here fails soft.

Features: activity import (+laps), daily resting HR / HRV / sleep, and
pushing structured workouts to the Garmin calendar (synced to the watch).
"""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

from ..config import get_settings
from ..db import HealthDaily, WorkoutRow, delete_setting, get_setting, log_sync, select, session, set_setting
from ..services import activities as act_svc
from ..services import plans as plan_svc

_lock = threading.Lock()
_client = None
_pending_mfa: dict = {}


def token_dir() -> Path:
    p = get_settings().data_dir / "garmin_tokens"
    p.mkdir(parents=True, exist_ok=True)
    return p


def connected() -> bool:
    return bool(get_setting("garmin_connected"))


def _new(email: str | None = None, password: str | None = None):
    from garminconnect import Garmin

    return Garmin(email=email, password=password, return_on_mfa=True)


def client():
    global _client
    with _lock:
        if _client is not None:
            return _client
        if not connected():
            raise RuntimeError("Garmin chưa kết nối")
        g = _new()
        g.login(str(token_dir()))
        _client = g
        return g


def login(email: str, password: str) -> dict:
    global _client
    g = _new(email, password)
    status, state = g.login(str(token_dir()))
    if status == "needs_mfa":
        _pending_mfa["client"] = g
        _pending_mfa["state"] = state
        return {"status": "needs_mfa"}
    _finish(g)
    return {"status": "connected"}


def submit_mfa(code: str) -> dict:
    g = _pending_mfa.get("client")
    if not g:
        raise RuntimeError("Không có phiên đăng nhập chờ MFA")
    g.resume_login(_pending_mfa["state"], code)
    _pending_mfa.clear()
    _finish(g)
    return {"status": "connected"}


def _finish(g) -> None:
    global _client
    try:
        g.client.dump(str(token_dir()))
    except Exception:  # noqa: BLE001
        pass
    _client = g
    set_setting("garmin_connected", True)


def disconnect() -> None:
    global _client
    _client = None
    delete_setting("garmin_connected")
    for f in token_dir().glob("*"):
        f.unlink(missing_ok=True)


def _gmt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("T", " ")).replace(tzinfo=dt.UTC)


def _laps(g, activity_id) -> list[dict]:
    try:
        data = g.get_activity_splits(str(activity_id))
    except Exception:  # noqa: BLE001
        return []
    laps = data.get("lapDTOs", []) if isinstance(data, dict) else []
    return [{"distance_m": lap.get("distance", 0.0), "duration_s": lap.get("movingDuration") or lap.get("duration"), "avg_hr": lap.get("averageHR")} for lap in laps]


def sync(days: int = 14) -> int:
    if not connected():
        return 0
    g = client()
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    n = 0
    try:
        acts = g.get_activities_by_date(start.isoformat(), today.isoformat())
        for a in acts:
            type_key = (a.get("activityType") or {}).get("typeKey", "")
            is_run = "running" in type_key or type_key in ("treadmill_running", "trail_running", "track_running")
            act_svc.upsert_activity(
                source="garmin",
                external_id=str(a["activityId"]),
                start_time=_gmt(a["startTimeGMT"]),
                distance_m=a.get("distance") or 0.0,
                duration_s=a.get("movingDuration") or a.get("duration") or 0.0,
                elapsed_s=a.get("elapsedDuration") or a.get("duration"),
                sport="run" if is_run else type_key,
                name=a.get("activityName", ""),
                avg_hr=a.get("averageHR"),
                max_hr=a.get("maxHR"),
                elevation_gain_m=a.get("elevationGain"),
                avg_cadence=a.get("averageRunningCadenceInStepsPerMinute"),
                calories=a.get("calories"),
                laps=_laps(g, a["activityId"]) if is_run else None,
            )
            n += 1
        sync_health(g, days=min(days, 7))
        log_sync("garmin", True, f"{n} hoạt động")
    except Exception as e:  # noqa: BLE001
        log_sync("garmin", False, str(e))
        raise
    return n


def sync_health(g, days: int = 7) -> None:
    today = dt.date.today()
    for i in range(days):
        d = today - dt.timedelta(days=i)
        ds = d.isoformat()
        rhr = hrv = sleep = None
        try:
            r = g.get_rhr_day(ds)
            vals = (((r or {}).get("allMetrics") or {}).get("metricsMap") or {}).get("WELLNESS_RESTING_HEART_RATE") or []
            rhr = vals[0].get("value") if vals else None
        except Exception:  # noqa: BLE001
            pass
        try:
            h = g.get_hrv_data(ds) or {}
            hrv = (h.get("hrvSummary") or {}).get("lastNightAvg")
        except Exception:  # noqa: BLE001
            pass
        try:
            sl = g.get_sleep_data(ds) or {}
            secs = (sl.get("dailySleepDTO") or {}).get("sleepTimeSeconds")
            sleep = round(secs / 3600, 2) if secs else None
        except Exception:  # noqa: BLE001
            pass
        upsert_health(d, rhr, hrv, sleep, "garmin")


def upsert_health(day: dt.date, rhr, hrv, sleep, source: str) -> None:
    if rhr is None and hrv is None and sleep is None:
        return
    with session() as s:
        row = s.get(HealthDaily, day) or HealthDaily(day=day)
        row.resting_hr = rhr if rhr is not None else row.resting_hr
        row.hrv_ms = hrv if hrv is not None else row.hrv_ms
        row.sleep_hours = sleep if sleep is not None else row.sleep_hours
        row.source = source
        s.add(row)
        s.commit()


# ---------------------------------------------------------------- workouts
_STEP_TYPE = {"warmup": (1, "warmup"), "cooldown": (2, "cooldown"), "run": (3, "interval"), "recovery": (4, "recovery")}


def _step_json(step: dict, order: list[int]) -> dict:
    order[0] += 1
    my_order = order[0]
    if step["kind"] == "repeat":
        children = [_step_json(c, order) for c in step.get("steps") or []]
        return {
            "type": "RepeatGroupDTO",
            "stepOrder": my_order,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
            "numberOfIterations": step.get("repeats") or 1,
            "smartRepeat": False,
            "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
            "endConditionValue": float(step.get("repeats") or 1),
            "workoutSteps": children,
        }
    tid, tkey = _STEP_TYPE.get(step["kind"], (3, "interval"))
    out: dict = {"type": "ExecutableStepDTO", "stepOrder": my_order, "stepType": {"stepTypeId": tid, "stepTypeKey": tkey, "displayOrder": tid}}
    if step.get("distance_m"):
        out["endCondition"] = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
        out["endConditionValue"] = float(step["distance_m"])
    elif step.get("duration_s"):
        out["endCondition"] = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
        out["endConditionValue"] = float(step["duration_s"])
    else:
        out["endCondition"] = {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True}
    tgt = step.get("target") or {}
    if tgt.get("fast_s_per_km") and tgt.get("slow_s_per_km"):
        # Garmin pace targets are speeds in m/s; slower pace = lower limit
        out["targetType"] = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}
        out["targetValueOne"] = round(1000.0 / tgt["slow_s_per_km"], 3)
        out["targetValueTwo"] = round(1000.0 / tgt["fast_s_per_km"], 3)
    else:
        out["targetType"] = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
    if step.get("note"):
        out["description"] = step["note"][:500]
    return out


def workout_json(w: WorkoutRow) -> dict:
    order = [0]
    steps = [_step_json(s, order) for s in (w.steps or [])]
    sport = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
    return {
        "workoutName": f"{w.date.strftime('%d/%m')} {w.title}"[:80],
        "description": w.description[:1000],
        "sportType": sport,
        "estimatedDurationInSecs": int(w.duration_min * 60),
        "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}],
    }


def push_workout(w: WorkoutRow) -> None:
    g = client()
    if w.garmin_workout_id:
        try:
            if w.garmin_schedule_id:
                g.unschedule_workout(w.garmin_schedule_id)
            g.delete_workout(w.garmin_workout_id)
        except Exception:  # noqa: BLE001
            pass
    res = g.upload_workout(workout_json(w))
    wid = res.get("workoutId")
    sched = g.schedule_workout(wid, w.date.isoformat())
    sid = (sched or {}).get("workoutScheduleId") or (sched or {}).get("id")
    with session() as s:
        row = s.get(WorkoutRow, w.id)
        row.garmin_workout_id = str(wid)
        row.garmin_schedule_id = str(sid) if sid else None
        row.synced_hash = plan_svc.content_hash(row)
        s.add(row)
        s.commit()


def remove_workout(w: WorkoutRow) -> None:
    if not w.garmin_workout_id:
        return
    g = client()
    try:
        if w.garmin_schedule_id:
            g.unschedule_workout(w.garmin_schedule_id)
        g.delete_workout(w.garmin_workout_id)
    except Exception:  # noqa: BLE001
        pass
    with session() as s:
        row = s.get(WorkoutRow, w.id)
        row.garmin_workout_id = row.garmin_schedule_id = None
        s.add(row)
        s.commit()


def push_upcoming(days: int = 7) -> int:
    """Keep the next `days` of runs in the Garmin calendar in sync with the plan."""
    if not connected() or not get_settings().garmin_push_workouts:
        return 0
    plan = plan_svc.active_plan()
    if not plan:
        return 0
    today = dt.date.today()
    n = 0
    with session() as s:
        rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == plan.id, WorkoutRow.date >= today, WorkoutRow.date <= today + dt.timedelta(days=days))).all()
    for w in rows:
        if w.type in ("strength", "rest", "race"):
            continue
        if w.status != "planned":
            if w.status == "skipped":
                remove_workout(w)
            continue
        if w.garmin_workout_id and w.synced_hash == plan_svc.content_hash(w):
            continue
        try:
            push_workout(w)
            n += 1
        except Exception as e:  # noqa: BLE001
            log_sync("garmin_push", False, f"{w.title}: {e}")
    return n
