from __future__ import annotations

import datetime as dt
import json
import secrets
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlmodel import select

from ..config import get_settings
from ..db import ActivityRow, AdjustmentRow, HealthDaily, PlanRow, SyncLog, WeekRow, WorkoutRow, get_setting, session, set_setting
from ..engine import adapt
from ..engine.models import Goal, RunnerProfile
from ..engine.text import steps_text
from ..engine.zones import ZONE_LABELS_VI, fmt_pace, pace_zones
from ..integrations import coros, garmin, strava
from ..services import activities as act_svc
from ..services import calendar, coach, metrics, sync, weather
from ..services import plans as plan_svc
from . import schemas as S


def today() -> dt.date:
    return dt.datetime.now(ZoneInfo(get_settings().timezone)).date()


def require_token(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, get_settings().app_token):
        raise HTTPException(401, "Sai token")


api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
public = APIRouter()


# ------------------------------------------------------------ serialization
def _heat_steps(steps: list[dict], factor: float) -> list[dict]:
    out = []
    for s in steps:
        s = json.loads(json.dumps(s))
        if s.get("steps"):
            s["steps"] = _heat_steps(s["steps"], factor)
        t = s.get("target")
        if t and t.get("fast_s_per_km"):
            t["fast_s_per_km"] = round(t["fast_s_per_km"] * factor, 1)
            t["slow_s_per_km"] = round(t["slow_s_per_km"] * factor, 1)
        out.append(s)
    return out


def workout_out(w: WorkoutRow, heat: dict | None = None) -> dict:
    d = w.model_dump()
    steps = w.steps or []
    if heat and heat.get("factor", 1.0) > 1.0 and w.type not in ("race", "strength") and get_setting("heat_adjust", True):
        d["heat_adjusted_steps"] = _heat_steps(steps, heat["factor"])
        d["heat"] = heat
    d["steps_text"] = steps_text(steps)
    d["synced"] = {"garmin": bool(w.garmin_workout_id), "coros": bool(w.coros_workout_id)}
    return d


def plan_out(p: PlanRow) -> dict:
    with session() as s:
        weeks = s.exec(select(WeekRow).where(WeekRow.plan_id == p.id).order_by(WeekRow.index)).all()
        wos = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == p.id).order_by(WorkoutRow.date)).all()
    by_week: dict[int, list] = {}
    for w in wos:
        by_week.setdefault(w.week_id or -1, []).append(workout_out(w))
    zones = pace_zones(p.current_vdot)
    return {
        "plan": p.model_dump(),
        "zones": {k: {"label": ZONE_LABELS_VI.get(k, k), "fast": fmt_pace(z.fast_s_per_km), "slow": fmt_pace(z.slow_s_per_km), "fast_s": z.fast_s_per_km, "slow_s": z.slow_s_per_km} for k, z in zones.items()},
        "weeks": [{**wk.model_dump(), "workouts": by_week.get(wk.id, []), "planned_km": round(sum(x["distance_km"] for x in by_week.get(wk.id, [])), 1)} for wk in weeks],
    }


def _plan_or_404() -> PlanRow:
    p = plan_svc.active_plan()
    if not p:
        raise HTTPException(404, "Chưa có giáo án")
    return p


# ------------------------------------------------------------ plan
@api.post("/plan")
def create_plan(body: S.CreatePlanIn):
    p = plan_svc.create_plan(body.goal, body.profile)
    return plan_out(p)


@api.post("/plan/preview")
def preview_plan(body: S.CreatePlanIn):
    from ..engine.generator import generate_plan

    plan = generate_plan(body.goal, body.profile)
    return json.loads(plan.model_dump_json())


@api.get("/plan")
def get_plan():
    return plan_out(_plan_or_404())


@api.post("/plan/regenerate")
def regenerate_plan():
    p = _plan_or_404()
    try:
        return plan_out(plan_svc.regenerate(p, today()))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@api.patch("/plan/goal")
def update_goal(body: S.GoalUpdateIn):
    p = _plan_or_404()
    goal = Goal(**p.goal)
    if body.target_time_s is not None:
        goal.target_time_s = body.target_time_s
    if body.race_date is not None:
        goal.race_date = body.race_date
    with session() as s:
        row = s.get(PlanRow, p.id)
        row.goal = json.loads(goal.model_dump_json())
        s.add(row)
        s.commit()
        s.refresh(row)
    return plan_out(plan_svc.regenerate(row, today()))


@api.get("/zones")
def zones(vdot: float | None = None):
    p = plan_svc.active_plan()
    v = vdot or (p.current_vdot if p else 40.0)
    return {"vdot": v, "zones": {k: {"label": ZONE_LABELS_VI.get(k, k), "fast": fmt_pace(z.fast_s_per_km), "slow": fmt_pace(z.slow_s_per_km)} for k, z in pace_zones(v).items()}}


# ------------------------------------------------------------ today / workouts
@api.get("/today")
def get_today(date: dt.date | None = None):
    d = date or today()
    p = plan_svc.active_plan()
    heat = weather.heat_for(d)
    out: dict = {"date": d.isoformat(), "heat": heat, "workouts": [], "next": None}
    if p:
        with session() as s:
            rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == p.id, WorkoutRow.date == d)).all()
            nxt = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == p.id, WorkoutRow.date > d, WorkoutRow.status == "planned", WorkoutRow.type != "strength").order_by(WorkoutRow.date)).first()
            pending = s.exec(select(AdjustmentRow).where(AdjustmentRow.plan_id == p.id, AdjustmentRow.status == "pending")).all()
            week = s.exec(select(WeekRow).where(WeekRow.plan_id == p.id, WeekRow.start_date <= d).order_by(WeekRow.start_date.desc())).first()
        out["workouts"] = [workout_out(w, heat) for w in rows]
        out["next"] = workout_out(nxt) if nxt else None
        out["pending_adjustments"] = [a.model_dump() for a in pending]
        out["week"] = week.model_dump() if week else None
        out["goal"] = p.goal
        rd = dt.date.fromisoformat(p.goal["race_date"]) if p.goal.get("race_date") else None
        out["days_to_race"] = (rd - d).days if rd else None
    snap = metrics.snapshot(d)
    out["readiness"] = snap["readiness"]
    out["load"] = {k: snap[k] for k in ("ctl", "atl", "tsb", "acwr")}
    return out


@api.get("/workouts")
def list_workouts(start: dt.date, end: dt.date):
    p = _plan_or_404()
    with session() as s:
        rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == p.id, WorkoutRow.date >= start, WorkoutRow.date <= end).order_by(WorkoutRow.date)).all()
    return [workout_out(w) for w in rows]


@api.get("/workouts/{wid}")
def get_workout(wid: int):
    with session() as s:
        w = s.get(WorkoutRow, wid)
        if not w:
            raise HTTPException(404)
        act = s.get(ActivityRow, w.activity_id) if w.activity_id else None
    out = workout_out(w, weather.heat_for(w.date) if w.date >= today() else None)
    out["activity"] = act.model_dump() if act else None
    return out


@api.patch("/workouts/{wid}")
def patch_workout(wid: int, body: S.WorkoutPatch, bg: BackgroundTasks):
    with session() as s:
        w = s.get(WorkoutRow, wid)
        if not w:
            raise HTTPException(404)
        if body.date:
            w.date = body.date
        if body.status:
            w.status = body.status
        if body.rpe is not None:
            w.rpe = body.rpe
        if body.notes is not None:
            w.notes = body.notes
        s.add(w)
        s.commit()
        s.refresh(w)
    if w.activity_id:
        act_svc.match_and_analyze(w.activity_id)
    bg.add_task(sync.push_all)
    return get_workout(wid)


@api.post("/workouts/{wid}/push")
async def push_workout(wid: int):
    with session() as s:
        w = s.get(WorkoutRow, wid)
    if not w:
        raise HTTPException(404)
    res = {}
    if garmin.connected():
        try:
            garmin.push_workout(w)
            res["garmin"] = "ok"
        except Exception as e:  # noqa: BLE001
            res["garmin"] = str(e)
    if coros.connected():
        with session() as s:
            row = s.get(WorkoutRow, wid)
            row.synced_hash = None
            row.coros_workout_id = None
            s.add(row)
            s.commit()
        res["coros"] = await coros.push_upcoming(days=max(0, (w.date - today()).days))
    return res


# ------------------------------------------------------------ adaptation
@api.get("/adjustments")
def list_adjustments(status: str | None = None):
    p = _plan_or_404()
    with session() as s:
        q = select(AdjustmentRow).where(AdjustmentRow.plan_id == p.id)
        if status:
            q = q.where(AdjustmentRow.status == status)
        return [a.model_dump() for a in s.exec(q.order_by(AdjustmentRow.created_at.desc())).all()]


@api.post("/adjustments/{aid}/apply")
def apply_adjustment(aid: int, bg: BackgroundTasks):
    try:
        a = plan_svc.apply_adjustment(aid, today())
    except KeyError as e:
        raise HTTPException(404) from e
    bg.add_task(sync.push_all)
    return a.model_dump()


@api.post("/adjustments/{aid}/dismiss")
def dismiss_adjustment(aid: int):
    with session() as s:
        a = s.get(AdjustmentRow, aid)
        if not a:
            raise HTTPException(404)
        a.status = "dismissed"
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.model_dump()


@api.post("/not-feeling-100")
def not_feeling_100(body: S.NotFeeling100In, bg: BackgroundTasks):
    p = _plan_or_404()
    adj = adapt.not_feeling_100(plan_svc.states(p.id), today(), body.reason, body.days, pace_zones(p.current_vdot))  # type: ignore[arg-type]
    row = plan_svc.record_adjustment(p.id, adj, auto_apply=True, today=today())  # type: ignore[arg-type]
    bg.add_task(sync.push_all)
    return {"reason": adj.reason, "adjustment": row.model_dump() if row else None}


@api.post("/maintenance")
def run_maintenance():
    return {"created": act_svc.daily_maintenance(today())}


# ------------------------------------------------------------ activities & health
@api.get("/activities")
def list_activities(limit: int = 50, include_duplicates: bool = False):
    with session() as s:
        q = select(ActivityRow)
        if not include_duplicates:
            q = q.where(ActivityRow.duplicate_of == None)  # noqa: E711
        rows = s.exec(q.order_by(ActivityRow.start_time.desc()).limit(limit)).all()
        linked = {w.activity_id: w.id for w in s.exec(select(WorkoutRow).where(WorkoutRow.activity_id != None)).all()}  # noqa: E711
    return [{**a.model_dump(exclude={"laps"}), "workout_id": linked.get(a.id), "pace": fmt_pace(a.duration_s / max(0.01, a.distance_m / 1000)) if a.distance_m else None} for a in rows]


@api.get("/activities/{aid}")
def get_activity(aid: int):
    with session() as s:
        a = s.get(ActivityRow, aid)
        if not a:
            raise HTTPException(404)
        w = s.exec(select(WorkoutRow).where(WorkoutRow.activity_id == (a.duplicate_of or a.id))).first()
    return {**a.model_dump(), "workout": workout_out(w) if w else None}


@api.post("/activities")
def add_activity(body: S.ManualActivityIn):
    a = act_svc.upsert_activity(
        source=body.source,
        external_id=str(uuid.uuid4()),
        start_time=body.start_time,
        distance_m=body.distance_m,
        duration_s=body.duration_s,
        avg_hr=body.avg_hr,
        name=body.name,
        laps=body.laps,
        analyze_now=body.workout_id is None,
    )
    if body.workout_id:
        with session() as s:
            w = s.get(WorkoutRow, body.workout_id)
            if w:
                w.activity_id = a.id
                if body.rpe:
                    w.rpe = body.rpe
                s.add(w)
                s.commit()
        act_svc.match_and_analyze(a.id)  # type: ignore[arg-type]
    elif body.rpe:
        with session() as s:
            w = s.exec(select(WorkoutRow).where(WorkoutRow.activity_id == a.id)).first()
            if w:
                w.rpe = body.rpe
                s.add(w)
                s.commit()
    return get_activity(a.id)  # type: ignore[arg-type]


@api.post("/health/batch")
def health_batch(body: S.HealthBatchIn):
    n = 0
    for w in body.workouts:
        act_svc.upsert_activity(
            source=w.source,
            external_id=w.external_id,
            start_time=w.start_time,
            distance_m=w.distance_m,
            duration_s=w.duration_s,
            elapsed_s=(w.end_time - w.start_time).total_seconds() if w.end_time else None,
            sport=w.sport,
            name=w.name,
            avg_hr=w.avg_hr,
            max_hr=w.max_hr,
            elevation_gain_m=w.elevation_gain_m,
            calories=w.calories,
            laps=w.laps,
        )
        n += 1
    for d in body.daily:
        garmin.upsert_health(d.day, d.resting_hr, d.hrv_ms, d.sleep_hours, d.source)
        if d.weight_kg:
            with session() as s:
                row = s.get(HealthDaily, d.day)
                row.weight_kg = d.weight_kg
                s.add(row)
                s.commit()
    if n:
        act_svc.daily_maintenance(today())
    set_setting(f"{body.workouts[0].source if body.workouts else 'health'}_last_sync", dt.datetime.now(dt.UTC).isoformat())
    return {"workouts": n, "daily": len(body.daily)}


# ------------------------------------------------------------ stats & coach
@api.get("/stats")
def stats():
    d = today()
    snap = metrics.snapshot(d)
    return {"load": snap, "weekly": metrics.weekly_volumes(d), "fitness": metrics.fitness(d)}


@api.get("/coach/weekly")
def coach_weekly():
    return coach.weekly_summary(today())


@api.post("/coach/chat")
async def coach_chat(body: S.ChatIn):
    try:
        return {"reply": await coach.chat(body.messages, today())}
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e


# ------------------------------------------------------------ settings
@api.get("/settings")
def get_settings_api():
    c = get_settings()
    return {
        "latitude": get_setting("latitude", c.latitude),
        "longitude": get_setting("longitude", c.longitude),
        "preferred_run_hour": get_setting("preferred_run_hour", 5),
        "heat_adjust": get_setting("heat_adjust", True),
        "timezone": c.timezone,
        "calendar_url": f"{c.public_url.rstrip('/')}/calendar.ics?token={c.app_token}",
        "ai_coach": bool(c.anthropic_api_key),
    }


@api.put("/settings")
def put_settings(body: S.SettingsIn):
    for k, v in body.model_dump(exclude_none=True).items():
        set_setting(k, v)
    return get_settings_api()


# ------------------------------------------------------------ integrations
@api.get("/integrations")
def integrations_status():
    with session() as s:
        logs = s.exec(select(SyncLog).order_by(SyncLog.at.desc()).limit(30)).all()
    last = {}
    for l in logs:  # noqa: E741
        last.setdefault(l.provider, l.model_dump())
    return {
        "strava": {"configured": strava.configured(), "connected": strava.connected(), "last": last.get("strava")},
        "garmin": {"connected": garmin.connected(), "last": last.get("garmin"), "push": last.get("garmin_push")},
        "coros": {"connected": coros.connected(), "last": last.get("coros"), "push": last.get("coros_push"), "tools": [t["name"] for t in (get_setting("coros_tools") or [])]},
        "apple_health": {"last_sync": get_setting("apple_health_last_sync")},
        "health_connect": {"last_sync": get_setting("health_connect_last_sync")},
    }


@api.post("/integrations/sync")
async def sync_now():
    return await sync.sync_all()


@api.get("/integrations/strava/connect")
def strava_connect():
    if not strava.configured():
        raise HTTPException(400, "Thiếu STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET trong .env")
    state = secrets.token_urlsafe(16)
    set_setting("strava_oauth_state", state)
    return {"authorize_url": strava.authorize_url(state)}


@api.post("/integrations/strava/sync")
def strava_sync(days: int = 30):
    return {"imported": strava.sync(days)}


@api.post("/integrations/strava/webhook/subscribe")
def strava_subscribe():
    return strava.subscribe_webhook()


@api.delete("/integrations/strava")
def strava_disconnect():
    strava.disconnect()
    return {"ok": True}


@api.post("/integrations/garmin/login")
def garmin_login(body: S.GarminLoginIn):
    c = get_settings()
    email = body.email or c.garmin_email
    pw = body.password or c.garmin_password
    if not email or not pw:
        raise HTTPException(400, "Cần email/mật khẩu Garmin")
    try:
        return garmin.login(email, pw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Đăng nhập Garmin thất bại: {e}") from e


@api.post("/integrations/garmin/mfa")
def garmin_mfa(body: S.MfaIn):
    try:
        return garmin.submit_mfa(body.code)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e


@api.post("/integrations/garmin/sync")
def garmin_sync(days: int = 14):
    return {"imported": garmin.sync(days), "pushed": garmin.push_upcoming()}


@api.delete("/integrations/garmin")
def garmin_disconnect():
    garmin.disconnect()
    return {"ok": True}


@api.post("/integrations/coros/connect")
async def coros_connect():
    try:
        return await coros.start_login()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Không kết nối được COROS: {e}") from e


@api.post("/integrations/coros/sync")
async def coros_sync(days: int = 14):
    return {"imported": await coros.sync(days), "pushed": await coros.push_upcoming()}


@api.get("/integrations/coros/tools")
def coros_tools():
    return get_setting("coros_tools") or []


@api.delete("/integrations/coros")
def coros_disconnect():
    coros.disconnect()
    return {"ok": True}


# ------------------------------------------------------------ public endpoints
_DONE_HTML = "<html><body style='font-family:sans-serif;text-align:center;padding:40px'><h2>{msg}</h2><p>Bạn có thể quay lại app.</p></body></html>"


@public.get("/api/integrations/strava/callback", response_class=HTMLResponse)
def strava_callback(code: str = "", state: str = "", scope: str = "", error: str = ""):
    if error or not code:
        return _DONE_HTML.format(msg=f"Strava từ chối: {error}")
    if state != get_setting("strava_oauth_state"):
        raise HTTPException(400, "state không hợp lệ")
    strava.exchange_code(code, scope)
    try:
        strava.sync(30)
    except Exception:  # noqa: BLE001
        pass
    return _DONE_HTML.format(msg="✅ Đã kết nối Strava")


@public.get("/api/integrations/coros/callback", response_class=HTMLResponse)
async def coros_callback(code: str = "", state: str | None = None, error: str = ""):
    if error or not code:
        return _DONE_HTML.format(msg=f"COROS từ chối: {error}")
    try:
        await coros.complete_login(code, state)
    except Exception as e:  # noqa: BLE001
        return _DONE_HTML.format(msg=f"Lỗi kết nối COROS: {e}")
    return _DONE_HTML.format(msg="✅ Đã kết nối COROS")


@public.get("/api/strava/webhook")
def strava_webhook_verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"), challenge: str = Query("", alias="hub.challenge")):
    if mode == "subscribe" and token == get_settings().strava_webhook_verify_token:
        return {"hub.challenge": challenge}
    raise HTTPException(403)


@public.post("/api/strava/webhook")
async def strava_webhook(request: Request, bg: BackgroundTasks):
    ev = await request.json()
    c = get_settings()
    # events are unsigned: only accept ones for our own app/athlete
    tok = get_setting("strava_tokens") or {}
    athlete_id = (tok.get("athlete") or {}).get("id")
    if str(ev.get("subscription_id", "")) and athlete_id and str(ev.get("owner_id")) != str(athlete_id):
        return {"ignored": True}
    if c.strava_client_id:

        def work():
            strava.handle_event(ev)
            act_svc.daily_maintenance(today())

        bg.add_task(work)
        bg.add_task(sync.push_all)
    return {"ok": True}


@public.get("/calendar.ics", response_class=PlainTextResponse)
def calendar_feed(token: str):
    if not secrets.compare_digest(token, get_settings().app_token):
        raise HTTPException(401)
    return PlainTextResponse(calendar.ics(), media_type="text/calendar")


@public.get("/health")
def healthcheck():
    return {"ok": True}
