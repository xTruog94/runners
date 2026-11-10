"""COROS via the self-service "Build on COROS" MCP server (single user, OAuth 2.0).

COROS documents an MCP endpoint (default https://mcp.coros.com/mcp) that a
developer can use for their own account without a partner application: read
training data and write workout plans. The MCP client discovers the OAuth
server (RFC 9728/8414), registers dynamically when supported, and runs the
authorization-code + PKCE flow.

The exact tool names/schemas are discovered at runtime (`list_tools`) and
mapped heuristically; they can be pinned with COROS_TOOL_* settings. Treat this
integration as experimental until verified against the live server.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from contextlib import asynccontextmanager
from typing import Any

from ..config import get_settings
from ..db import WorkoutRow, delete_setting, get_setting, log_sync, select, session, set_setting
from ..engine.text import steps_text
from ..services import activities as act_svc
from ..services import plans as plan_svc

TOKENS = "coros_oauth_tokens"
CLIENT = "coros_oauth_client"
TOOLS = "coros_tools"

_login: dict[str, Any] = {}


class DbTokenStorage:
    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        v = get_setting(TOKENS)
        return OAuthToken.model_validate(v) if v else None

    async def set_tokens(self, tokens) -> None:
        set_setting(TOKENS, tokens.model_dump(mode="json", exclude_none=True))
        set_setting("coros_connected", True)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        v = get_setting(CLIENT)
        return OAuthClientInformationFull.model_validate(v) if v else None

    async def set_client_info(self, info) -> None:
        set_setting(CLIENT, info.model_dump(mode="json", exclude_none=True))


def redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/api/integrations/coros/callback"


def connected() -> bool:
    return bool(get_setting("coros_connected"))


async def _no_interaction(url: str) -> None:
    raise RuntimeError("COROS chưa kết nối hoặc phiên đã hết hạn — kết nối lại trong app.")


@asynccontextmanager
async def mcp_session(redirect_handler=None, callback_handler=None):
    import httpx2
    from mcp.client.auth import OAuthClientProvider
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared.auth import OAuthClientMetadata

    cfg = get_settings()
    provider = OAuthClientProvider(
        server_url=cfg.coros_mcp_url,
        client_metadata=OAuthClientMetadata(
            client_name="Runners (personal)",
            redirect_uris=[redirect_uri()],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=DbTokenStorage(),
        redirect_handler=redirect_handler or _no_interaction,
        callback_handler=callback_handler,
    )
    async with httpx2.AsyncClient(auth=provider, timeout=httpx2.Timeout(60.0)) as http:
        async with streamable_http_client(cfg.coros_mcp_url, http_client=http) as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                yield sess


async def _refresh_tools(sess) -> list[dict]:
    res = await sess.list_tools()
    tools = [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema or {}} for t in res.tools]
    set_setting(TOOLS, tools)
    return tools


# ------------------------------------------------------------------ login
async def start_login() -> dict:
    """Returns {"authorize_url": ...} or {"status": "connected"}."""
    from mcp.shared.auth import AuthorizationCodeResult

    loop = asyncio.get_running_loop()
    url_future: asyncio.Future[str] = loop.create_future()
    code_future: asyncio.Future = loop.create_future()

    async def on_redirect(url: str) -> None:
        if not url_future.done():
            url_future.set_result(url)

    async def on_callback() -> AuthorizationCodeResult:
        code, state = await asyncio.wait_for(code_future, timeout=600)
        return AuthorizationCodeResult(code=code, state=state)

    async def run() -> None:
        try:
            async with mcp_session(on_redirect, on_callback) as sess:
                await _refresh_tools(sess)
            set_setting("coros_connected", True)
            log_sync("coros", True, "Đã kết nối")
        except Exception as e:  # noqa: BLE001
            log_sync("coros", False, f"login: {e}")
            if not url_future.done():
                url_future.set_exception(e)

    old = _login.get("task")
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(run())
    _login.update(task=task, code_future=code_future)
    done, _ = await asyncio.wait({task, url_future}, timeout=45, return_when=asyncio.FIRST_COMPLETED)
    if url_future.done():
        return {"authorize_url": url_future.result()}
    if task.done():
        return {"status": "connected"}
    raise RuntimeError("COROS không phản hồi khi bắt đầu đăng nhập")


async def complete_login(code: str, state: str | None) -> None:
    fut = _login.get("code_future")
    if fut is None or fut.done():
        raise RuntimeError("Không có phiên đăng nhập COROS đang chờ")
    fut.set_result((code, state))
    task = _login.get("task")
    if task:
        await asyncio.wait_for(task, timeout=60)


def disconnect() -> None:
    for k in (TOKENS, CLIENT, TOOLS, "coros_connected"):
        delete_setting(k)


# ------------------------------------------------------------------ helpers
def _find_tool(tools: list[dict], configured: str, must: list[str], any_of: list[str], avoid: list[str] = ()) -> dict | None:  # type: ignore[assignment]
    if configured:
        return next((t for t in tools if t["name"] == configured), None)
    scored = []
    for t in tools:
        text = (t["name"] + " " + t["description"]).lower()
        if all(m in text for m in must) and any(a in text for a in any_of) and not any(v in t["name"].lower() for v in avoid):
            scored.append((len(t["name"]), t))
    return min(scored, key=lambda x: x[0])[1] if scored else None


def _date_fmt(prop: dict) -> str:
    text = json.dumps(prop).lower()
    if "yyyymmdd" in text:
        return "%Y%m%d"
    return "%Y-%m-%d"


def _fill_args(schema: dict, values: dict[str, Any]) -> dict:
    """Fill an MCP tool's arguments from semantic values using property names."""
    props = (schema or {}).get("properties", {})
    args: dict[str, Any] = {}
    for name, prop in props.items():
        n = name.lower()
        if any(k in n for k in ("start", "from", "begin")) and ("start" in values or "date" in values):
            args[name] = (values.get("start") or values["date"]).strftime(_date_fmt(prop))
        elif any(k in n for k in ("end", "until")) or n == "to":
            if "end" in values:
                args[name] = values["end"].strftime(_date_fmt(prop))
        elif n in ("date", "day", "scheduledate", "schedule_date", "plandate", "workout_date") and "date" in values:
            args[name] = values["date"].strftime(_date_fmt(prop))
        elif n in ("limit", "size", "count", "pagesize", "page_size", "max_results") and "limit" in values:
            args[name] = values["limit"]
        elif n in ("page", "pagenumber", "page_number"):
            args[name] = 1
        elif n in ("name", "title", "workoutname", "workout_name") and "name" in values:
            args[name] = values["name"]
        elif n in ("description", "desc", "notes", "note", "overview") and "description" in values:
            args[name] = values["description"]
        elif n in ("sport", "sporttype", "sport_type", "type") and "sport" in values:
            args[name] = values["sport"] if prop.get("type") != "integer" else 100
        elif n in ("steps", "exercises", "segments", "intervals", "workout_steps") and "steps" in values:
            args[name] = values["steps"]
        elif n in ("distance", "distance_m", "total_distance") and "distance_m" in values:
            args[name] = values["distance_m"]
        elif n in ("duration", "duration_s", "total_time") and "duration_s" in values:
            args[name] = values["duration_s"]
    missing = [r for r in (schema or {}).get("required", []) if r not in args]
    if missing:
        raise RuntimeError(f"Không tự điền được tham số {missing} cho tool COROS — đặt COROS_TOOL_* hoặc cập nhật mapping.")
    return args


def _result_json(res) -> Any:
    if getattr(res, "isError", False):
        raise RuntimeError("COROS tool lỗi: " + " ".join(getattr(c, "text", "") for c in res.content))
    sc = getattr(res, "structuredContent", None)
    if sc:
        return sc
    texts = [getattr(c, "text", "") for c in res.content]
    for t in texts:
        try:
            return json.loads(t)
        except (TypeError, ValueError):
            continue
    return {"text": "\n".join(texts)}


def _find_records(obj: Any) -> list[dict]:
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        keys = set().union(*(x.keys() for x in obj))
        if any("distance" in k.lower() for k in keys):
            return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = _find_records(v)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _find_records(v)
            if r:
                return r
    return []


def _pick(d: dict, *names: str):
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return low[n.lower()]
    return None


def _to_dt(v) -> dt.datetime | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if v > 1e12:
            v = v / 1000
        if v > 1e9:
            return dt.datetime.fromtimestamp(v, dt.UTC)
        if 19000101 <= v <= 21001231:
            return dt.datetime.strptime(str(int(v)), "%Y%m%d").replace(tzinfo=dt.UTC)
    s = str(v)
    if re.fullmatch(r"\d{8}", s):
        return dt.datetime.strptime(s, "%Y%m%d").replace(tzinfo=dt.UTC)
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.UTC)
    except ValueError:
        return None


COROS_RUN_SPORTS = {100, 101, 102, 103, 104}


def map_activity(r: dict) -> dict | None:
    start = _to_dt(_pick(r, "startTime", "start_time", "startTimestamp", "start_date", "startDate", "date", "time"))
    ext = _pick(r, "labelId", "activityId", "activity_id", "id")
    if not start or ext is None:
        return None
    dist = float(_pick(r, "distance", "totalDistance", "distance_m") or 0)
    if any("km" in k.lower() for k in r if "distance" in k.lower()):
        dist *= 1000
    dur = float(_pick(r, "totalTime", "duration", "movingTime", "workoutTime", "duration_s", "elapsedTime") or 0)
    if dur > 360000:  # milliseconds or centiseconds
        dur = dur / 1000 if dur > 3_600_000 else dur / 100
    sport_raw = _pick(r, "sportType", "sport_type", "sport", "mode", "type", "sportName")
    sport_text = str(sport_raw).lower()
    is_run = (isinstance(sport_raw, int) and sport_raw in COROS_RUN_SPORTS) or "run" in sport_text
    return {
        "external_id": str(ext),
        "start_time": start,
        "distance_m": dist,
        "duration_s": dur,
        "sport": "run" if is_run else sport_text,
        "name": str(_pick(r, "name", "title") or ""),
        "avg_hr": _pick(r, "avgHr", "avgHeartRate", "averageHeartRate", "avg_hr"),
        "max_hr": _pick(r, "maxHr", "maxHeartRate", "max_hr"),
        "elevation_gain_m": _pick(r, "ascent", "totalAscent", "elevationGain", "elevation_gain"),
        "avg_cadence": _pick(r, "avgCadence", "cadence", "avg_cadence"),
        "calories": _pick(r, "calorie", "calories"),
    }


# ------------------------------------------------------------------ sync
async def sync(days: int = 14) -> int:
    if not connected():
        return 0
    cfg = get_settings()
    n = 0
    try:
        async with mcp_session() as sess:
            tools = await _refresh_tools(sess)
            tool = _find_tool(tools, cfg.coros_tool_list_activities, ["activit"], ["list", "get", "query", "search", "recent", "history"], avoid=["detail", "delete"])
            if not tool:
                raise RuntimeError("Không tìm thấy tool đọc hoạt động trên COROS MCP. Xem /api/integrations/coros/tools.")
            end = dt.date.today()
            start = end - dt.timedelta(days=days)
            res = await sess.call_tool(tool["name"], _fill_args(tool["input_schema"], {"start": start, "end": end, "limit": 100}))
            for r in _find_records(_result_json(res)):
                m = map_activity(r)
                if m:
                    act_svc.upsert_activity(source="coros", **m)
                    n += 1
        log_sync("coros", True, f"{n} hoạt động")
    except Exception as e:  # noqa: BLE001
        log_sync("coros", False, str(e))
        raise
    return n


def generic_steps(steps: list[dict]) -> list[dict]:
    """Our steps in a neutral, self-explanatory structure for the COROS tool."""
    out = []
    for s in steps:
        if s.get("kind") == "repeat":
            out.append({"type": "repeat", "repeats": s.get("repeats", 1), "steps": generic_steps(s.get("steps") or [])})
            continue
        tgt = s.get("target") or {}
        item = {"type": s["kind"]}
        if s.get("distance_m"):
            item["distance_m"] = s["distance_m"]
        if s.get("duration_s"):
            item["duration_s"] = s["duration_s"]
        if tgt.get("fast_s_per_km"):
            item["pace_min_s_per_km"] = round(tgt["fast_s_per_km"])
            item["pace_max_s_per_km"] = round(tgt["slow_s_per_km"])
        out.append(item)
    return out


async def push_upcoming(days: int = 7) -> int:
    cfg = get_settings()
    if not connected() or not cfg.coros_push_workouts:
        return 0
    plan = plan_svc.active_plan()
    if not plan:
        return 0
    today = dt.date.today()
    with session() as s:
        rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == plan.id, WorkoutRow.date >= today, WorkoutRow.date <= today + dt.timedelta(days=days), WorkoutRow.status == "planned")).all()
    todo = [w for w in rows if w.type not in ("strength", "rest", "race") and not (w.coros_workout_id and w.synced_hash == plan_svc.content_hash(w))]
    if not todo:
        return 0
    n = 0
    async with mcp_session() as sess:
        tools = get_setting(TOOLS) or await _refresh_tools(sess)
        tool = _find_tool(tools, cfg.coros_tool_create_workout, [], ["workout", "training plan", "schedule"], avoid=["delete", "list", "get"])
        if not tool or not any(k in (tool["name"] + tool["description"]).lower() for k in ("create", "add", "upload", "write", "save", "schedule", "push")):
            log_sync("coros_push", False, "Không tìm thấy tool tạo workout trên COROS MCP")
            return 0
        for w in todo:
            values = {
                "date": w.date,
                "name": f"{w.date.strftime('%d/%m')} {w.title}"[:60],
                "description": (w.description + "\n\n" + steps_text(w.steps or []))[:2000],
                "sport": "run",
                "steps": generic_steps(w.steps or []),
                "distance_m": round(w.distance_km * 1000),
                "duration_s": round(w.duration_min * 60),
            }
            try:
                res = await sess.call_tool(tool["name"], _fill_args(tool["input_schema"], values))
                data = _result_json(res)
                wid = _pick(data, "id", "workoutId", "planId", "programId") if isinstance(data, dict) else None
                with session() as s:
                    row = s.get(WorkoutRow, w.id)
                    row.coros_workout_id = str(wid or "pushed")
                    row.synced_hash = plan_svc.content_hash(row)
                    s.add(row)
                    s.commit()
                n += 1
            except Exception as e:  # noqa: BLE001
                log_sync("coros_push", False, f"{w.title}: {e}")
    return n
