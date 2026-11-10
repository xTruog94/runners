import datetime as dt

from app.api import routes
from app.db import WorkoutRow, session
from app.integrations import coros, garmin


def _create(client, start=None, weeks=12):
    start = start or routes.today()
    body = {
        "goal": {"distance": "10k", "race_date": (start + dt.timedelta(weeks=weeks)).isoformat(), "start_date": start.isoformat(), "target_time_s": 50 * 60},
        "profile": {"level": "intermediate", "current_weekly_km": 25, "days_per_week": 4, "recent_race": {"distance_m": 5000, "time_s": 25 * 60}, "max_hr": 190, "resting_hr": 50},
    }
    r = client.post("/api/plan", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_required(client):
    assert client.get("/api/plan", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_create_and_get_plan(client):
    data = _create(client)
    assert data["weeks"] and data["zones"]["easy"]["fast"].endswith("/km")
    assert client.get("/api/plan").json()["plan"]["id"] == data["plan"]["id"]
    t = client.get("/api/today").json()
    assert "readiness" in t and t["days_to_race"] > 0


def _first_run(plan):
    for wk in plan["weeks"]:
        for w in wk["workouts"]:
            if w["type"] in ("easy", "long", "recovery"):
                return w
    raise AssertionError


def test_health_ingest_matches_and_dedupes(client):
    plan = _create(client)
    w = _first_run(plan)
    start = dt.datetime.fromisoformat(w["date"] + "T00:00:00+07:00")
    km = w["distance_km"]
    pace = 390  # 6:30/km
    payload = {"workouts": [{"source": "apple_health", "external_id": "hk-1", "start_time": start.isoformat(), "distance_m": km * 1000, "duration_s": km * pace, "avg_hr": 140}]}
    r = client.post("/api/health/batch", json=payload)
    assert r.status_code == 200, r.text
    wo = client.get(f"/api/workouts/{w['id']}").json()
    assert wo["status"] == "completed" and wo["analysis"]["compliance"] > 0.95
    # same run from Strava (higher priority) -> health record becomes duplicate
    payload2 = {"workouts": [{"source": "health_connect", "external_id": "hc-1", "start_time": (start + dt.timedelta(minutes=1)).isoformat(), "distance_m": km * 1000 + 30, "duration_s": km * pace}]}
    client.post("/api/health/batch", json=payload2)
    acts = client.get("/api/activities").json()
    assert len(acts) == 1 and acts[0]["source"] == "apple_health"
    all_acts = client.get("/api/activities?include_duplicates=true").json()
    assert len(all_acts) == 2


def test_patch_and_rpe(client):
    plan = _create(client)
    w = _first_run(plan)
    r = client.patch(f"/api/workouts/{w['id']}", json={"rpe": 6, "notes": "ok"})
    assert r.json()["rpe"] == 6


def test_missed_workout_rescheduled(client):
    start = routes.today() - dt.timedelta(days=10)
    _create(client, start=start)
    # one run 2 days ago so it is not treated as a long break
    client.post("/api/activities", json={"start_time": (dt.datetime.now(dt.UTC) - dt.timedelta(days=2)).isoformat(), "distance_m": 5000, "duration_s": 1800})
    r = client.post("/api/maintenance")
    assert r.status_code == 200
    adjs = client.get("/api/adjustments").json()
    assert adjs, "missed workouts should produce adjustments"
    with session() as s:
        past = s.exec(__import__("sqlmodel").select(WorkoutRow).where(WorkoutRow.date < routes.today() - dt.timedelta(days=3), WorkoutRow.type != "strength")).all()
    assert all(w.status != "planned" or w.date >= routes.today() for w in past)


def test_not_feeling_100(client):
    _create(client)
    r = client.post("/api/not-feeling-100", json={"reason": "busy", "days": 3})
    assert r.status_code == 200 and r.json()["reason"]


def test_regenerate_and_goal_update(client):
    _create(client)
    r = client.patch("/api/plan/goal", json={"target_time_s": 48 * 60})
    assert r.status_code == 200
    assert client.post("/api/plan/regenerate").status_code == 200


def test_stats_and_calendar(client):
    _create(client)
    s = client.get("/api/stats").json()
    assert "weekly" in s and "fitness" in s
    ics = client.get("/calendar.ics", params={"token": "test-token"}, headers={"Authorization": ""})
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text


def test_strava_webhook_verify(client):
    r = client.get("/api/strava/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "runners-verify", "hub.challenge": "abc"}, headers={"Authorization": ""})
    assert r.json() == {"hub.challenge": "abc"}


def test_garmin_workout_json(client):
    plan = _create(client)
    w = next(x for wk in plan["weeks"] for x in wk["workouts"] if x["type"] in ("intervals", "fartlek", "hills", "tempo"))
    with session() as s:
        row = s.get(WorkoutRow, w["id"])
    j = garmin.workout_json(row)
    steps = j["workoutSegments"][0]["workoutSteps"]
    orders = []

    def walk(ss):
        for st in ss:
            orders.append(st["stepOrder"])
            if st["type"] == "RepeatGroupDTO":
                assert st["numberOfIterations"] >= 1
                walk(st["workoutSteps"])

    walk(steps)
    assert orders == sorted(orders) and len(set(orders)) == len(orders)
    paced = [st for st in steps if st.get("targetType", {}).get("workoutTargetTypeKey") == "pace.zone"]
    for st in paced:
        assert st["targetValueOne"] < st["targetValueTwo"]  # slower speed first


def test_coros_mapping_helpers():
    schema = {"properties": {"startDay": {"type": "string", "description": "YYYYMMDD"}, "endDay": {"type": "string"}, "size": {"type": "integer"}}, "required": ["startDay"]}
    args = coros._fill_args(schema, {"start": dt.date(2026, 11, 1), "end": dt.date(2026, 11, 10), "limit": 50})
    assert args == {"startDay": "20261101", "endDay": "2026-11-10", "size": 50}
    rec = coros.map_activity({"labelId": "42", "startTime": 1762740000, "distance": 10000, "totalTime": 3000, "sportType": 100, "avgHr": 150})
    assert rec["sport"] == "run" and rec["distance_m"] == 10000 and rec["external_id"] == "42"
    found = coros._find_records({"data": {"dataList": [{"labelId": 1, "distance": 5}]}})
    assert found and found[0]["labelId"] == 1
    tools = [{"name": "get_activity_detail", "description": ""}, {"name": "list_activities", "description": "List recent activities"}, {"name": "create_workout", "description": "Create a workout plan"}]
    assert coros._find_tool(tools, "", ["activit"], ["list", "get"], avoid=["detail"])["name"] == "list_activities"
