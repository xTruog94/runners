"""Strava: OAuth, activity sync, webhook events, optional coach notes.

Personal use: create your own API application at strava.com/settings/api.
Note: since mid-2026 Strava requires the developer of a Standard-tier app to
hold a Strava subscription; check the current API agreement.
"""

from __future__ import annotations

import datetime as dt
import time
from urllib.parse import urlencode

import httpx

from ..config import get_settings
from ..db import ActivityRow, delete_setting, get_setting, log_sync, select, session, set_setting
from ..services import activities as act_svc

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API = "https://www.strava.com/api/v3"
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
KEY = "strava_tokens"


def configured() -> bool:
    c = get_settings()
    return bool(c.strava_client_id and c.strava_client_secret)


def connected() -> bool:
    return bool(get_setting(KEY))


def redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/api/integrations/strava/callback"


def authorize_url(state: str) -> str:
    c = get_settings()
    scope = "read,activity:read_all" + (",activity:write" if c.strava_write_descriptions else "")
    q = {"client_id": c.strava_client_id, "response_type": "code", "redirect_uri": redirect_uri(), "approval_prompt": "auto", "scope": scope, "state": state}
    return f"{AUTH_URL}?{urlencode(q)}"


def exchange_code(code: str, scope: str | None = None) -> dict:
    c = get_settings()
    r = httpx.post(TOKEN_URL, data={"client_id": c.strava_client_id, "client_secret": c.strava_client_secret, "code": code, "grant_type": "authorization_code"}, timeout=20)
    r.raise_for_status()
    tok = r.json()
    tok["scope"] = scope
    set_setting(KEY, tok)
    return tok


def _token() -> str:
    tok = get_setting(KEY)
    if not tok:
        raise RuntimeError("Strava chưa kết nối")
    if tok.get("expires_at", 0) < time.time() + 120:
        c = get_settings()
        r = httpx.post(TOKEN_URL, data={"client_id": c.strava_client_id, "client_secret": c.strava_client_secret, "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]}, timeout=20)
        r.raise_for_status()
        tok.update(r.json())
        set_setting(KEY, tok)
    return tok["access_token"]


def _get(path: str, **params):
    r = httpx.get(f"{API}{path}", headers={"Authorization": f"Bearer {_token()}"}, params=params, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("Strava rate limit — thử lại sau 15 phút")
    r.raise_for_status()
    return r.json()


def _parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _laps(activity_id: int) -> list[dict]:
    try:
        laps = _get(f"/activities/{activity_id}/laps")
    except httpx.HTTPError:
        return []
    return [
        {"distance_m": lap.get("distance", 0.0), "duration_s": lap.get("moving_time") or lap.get("elapsed_time"), "avg_hr": lap.get("average_heartrate")}
        for lap in laps
    ]


def import_activity(a: dict, with_laps: bool = True) -> ActivityRow | None:
    sport = a.get("sport_type") or a.get("type")
    is_run = sport in RUN_TYPES
    cad = a.get("average_cadence")
    return act_svc.upsert_activity(
        source="strava",
        external_id=str(a["id"]),
        start_time=_parse_time(a["start_date"]),
        distance_m=a.get("distance", 0.0),
        duration_s=a.get("moving_time", 0.0),
        elapsed_s=a.get("elapsed_time"),
        sport="run" if is_run else str(sport).lower(),
        name=a.get("name", ""),
        avg_hr=a.get("average_heartrate"),
        max_hr=a.get("max_heartrate"),
        elevation_gain_m=a.get("total_elevation_gain"),
        avg_cadence=cad * 2 if (cad and is_run) else cad,
        calories=a.get("calories"),
        laps=_laps(a["id"]) if (with_laps and is_run) else None,
    )


def sync(days: int = 30) -> int:
    if not connected():
        return 0
    last = get_setting("strava_last_sync")
    after = int(last - 3600) if last else int(time.time() - days * 86400)
    n, page = 0, 1
    try:
        while True:
            items = _get("/athlete/activities", after=after, per_page=100, page=page)
            if not items:
                break
            for a in items:
                with session() as s:
                    exists = s.exec(select(ActivityRow).where(ActivityRow.source == "strava", ActivityRow.external_id == str(a["id"]))).first()
                import_activity(a, with_laps=exists is None or not exists.laps)
                n += 1
            if len(items) < 100:
                break
            page += 1
        set_setting("strava_last_sync", time.time())
        log_sync("strava", True, f"{n} hoạt động")
    except Exception as e:  # noqa: BLE001
        log_sync("strava", False, str(e))
        raise
    return n


def handle_event(ev: dict) -> None:
    if ev.get("object_type") == "athlete" and (ev.get("updates") or {}).get("authorized") == "false":
        delete_setting(KEY)
        return
    if ev.get("object_type") != "activity" or not connected():
        return
    aid = ev.get("object_id")
    if ev.get("aspect_type") == "delete":
        with session() as s:
            row = s.exec(select(ActivityRow).where(ActivityRow.source == "strava", ActivityRow.external_id == str(aid))).first()
            if row:
                s.delete(row)
                s.commit()
        return
    a = _get(f"/activities/{aid}")
    row = import_activity(a)
    if row and ev.get("aspect_type") == "create":
        maybe_write_notes(row)


def maybe_write_notes(row: ActivityRow) -> None:
    """Append the post-run analysis to the Strava description (opt-in)."""
    c = get_settings()
    tok = get_setting(KEY) or {}
    if not c.strava_write_descriptions or "activity:write" not in (tok.get("scope") or ""):
        return
    from ..db import WorkoutRow

    with session() as s:
        w = s.exec(select(WorkoutRow).where(WorkoutRow.activity_id == (row.duplicate_of or row.id))).first()
    if not w or not w.analysis:
        return
    text = f"🏃 {w.title}\n{w.analysis.get('summary', '')}\n" + "\n".join(w.analysis.get("tips", []))
    httpx.put(f"{API}/activities/{row.external_id}", headers={"Authorization": f"Bearer {_token()}"}, data={"description": text}, timeout=20)


def subscribe_webhook() -> dict:
    c = get_settings()
    r = httpx.post(
        f"{API}/push_subscriptions",
        data={
            "client_id": c.strava_client_id,
            "client_secret": c.strava_client_secret,
            "callback_url": f"{c.public_url.rstrip('/')}/api/strava/webhook",
            "verify_token": c.strava_webhook_verify_token,
        },
        timeout=30,
    )
    return {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}


def disconnect() -> None:
    tok = get_setting(KEY)
    if tok:
        try:
            httpx.post("https://www.strava.com/oauth/deauthorize", data={"access_token": tok.get("access_token")}, timeout=10)
        except httpx.HTTPError:
            pass
    delete_setting(KEY)
    delete_setting("strava_last_sync")
