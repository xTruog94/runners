from datetime import date, timedelta

import pytest

from app.engine import adapt
from app.engine.analysis import ActualRun, Lap, analyze
from app.engine.fitness import RunSample, estimate_vdot, predictions
from app.engine.generator import generate_plan, split_phases
from app.engine.heat import heat_factor, heat_slowdown_pct
from app.engine.load import acwr, load_series, readiness, running_tss
from app.engine.models import QUALITY_TYPES, Goal, RecentRace, RunnerProfile
from app.engine.vdot import predict_race_time, vdot_from_race
from app.engine.zones import pace_zones

START = date(2026, 11, 9)  # Monday


def test_vdot_reference_values():
    # Daniels tables: 5K 19:57 = VDOT 50 ; marathon 3:00:00 ≈ 53.5
    assert vdot_from_race(5000, 19 * 60 + 57) == pytest.approx(50.0, abs=0.2)
    assert vdot_from_race(42195, 3 * 3600) == pytest.approx(53.5, abs=0.3)


def test_prediction_roundtrip():
    v = vdot_from_race(10000, 45 * 60)
    assert predict_race_time(v, 10000) == pytest.approx(45 * 60, abs=2)
    assert predict_race_time(v, 21097.5) > 2 * 45 * 60  # slower than double


def test_zones_ordered():
    z = pace_zones(45)
    assert z["repetition"].mid < z["interval"].mid < z["threshold"].mid < z["half"].mid < z["marathon"].mid < z["easy"].mid < z["recovery"].mid
    hot = pace_zones(45, heat_factor=1.05)
    assert hot["easy"].mid == pytest.approx(z["easy"].mid * 1.05)


def test_heat():
    assert heat_slowdown_pct(15, 50) == 0
    assert heat_slowdown_pct(30, 80) >= 4.5  # typical Saigon morning
    assert heat_factor(None, None) == 1.0


def test_phases():
    ph = split_phases(16, "marathon")
    assert len(ph) == 16 and ph[-3:] == ["taper"] * 3 and ph[0] == "base"
    assert split_phases(4, "5k")[-1] == "taper"


def _plan(distance="half", weeks=17, days=5, level="intermediate", km=30.0, **kw):
    p = RunnerProfile(level=level, current_weekly_km=km, days_per_week=days, recent_race=RecentRace(distance_m=10000, time_s=50 * 60), **kw)
    g = Goal(distance=distance, race_date=START + timedelta(weeks=weeks - 1, days=6), start_date=START, target_time_s=kw.pop("target", None) if False else None)
    return generate_plan(g, p)


@pytest.mark.parametrize("distance", ["5k", "10k", "half", "marathon"])
@pytest.mark.parametrize("days", [3, 4, 5, 6])
def test_plan_invariants(distance, days):
    plan = _plan(distance, weeks=18, days=days)
    race_day = plan.goal.race_date
    runs_by_week = []
    for wk in plan.weeks:
        runs = [w for w in wk.workouts if w.type != "strength"]
        runs_by_week.append(runs)
        # number of run days respects availability (race week may add shakeout/race)
        if wk.phase != "taper":
            assert len({w.date for w in runs}) <= days
        # quality sessions never on consecutive days
        qd = sorted(w.date for w in runs if w.type in QUALITY_TYPES or w.type == "long")
        for a, b in zip(qd, qd[1:]):
            assert (b - a).days >= 1
        hard = sorted(w.date for w in runs if w.type in QUALITY_TYPES)
        for a, b in zip(hard, hard[1:]):
            assert (b - a).days >= 2, (wk.index, hard)
        assert sum(1 for w in runs if w.type in QUALITY_TYPES) <= 2
    # volume growth <= 10%/week between build weeks (cut-back weeks excluded)
    build_only = [wk.target_km for wk in plan.weeks if not wk.is_cutback and wk.phase != "taper"]
    for a, b in zip(build_only, build_only[1:]):
        assert b <= a * 1.10 + 0.01
    # race is the last workout, on race day
    last = plan.weeks[-1].workouts[-1]
    assert last.type == "race" and last.date == race_day
    # taper weeks lighter than peak
    peak = max(wk.target_km for wk in plan.weeks)
    for wk in plan.weeks:
        if wk.phase == "taper":
            assert wk.target_km < peak


def test_long_run_caps():
    plan = _plan("marathon", weeks=20, days=5, level="advanced", km=60)
    longs = [w.distance_km for w in plan.all_workouts() if w.type == "long"]
    assert max(longs) <= 32
    assert max(longs) >= 26


def test_goal_too_ambitious_warns():
    p = RunnerProfile(current_weekly_km=30, recent_race=RecentRace(distance_m=10000, time_s=60 * 60))
    g = Goal(distance="10k", race_date=START + timedelta(weeks=8), start_date=START, target_time_s=40 * 60)
    plan = generate_plan(g, p)
    assert plan.warnings
    assert plan.goal_vdot - plan.start_vdot <= 2.5


def test_general_plan_no_race():
    p = RunnerProfile(level="beginner", current_weekly_km=10, days_per_week=3)
    plan = generate_plan(Goal(distance="general", start_date=START), p)
    assert len(plan.weeks) == 12
    assert not any(w.type == "race" for w in plan.all_workouts())


def test_mid_week_start_skips_past_days():
    p = RunnerProfile(current_weekly_km=20)
    plan = generate_plan(Goal(distance="10k", race_date=START + timedelta(weeks=10), start_date=START + timedelta(days=3)), p)
    assert all(w.date >= START + timedelta(days=3) for w in plan.all_workouts())


def test_load_and_readiness():
    tss = running_tss(3600, 12000, threshold_pace_s_per_km=300)  # 5:00/km for 1h at T pace
    assert tss == pytest.approx(100, abs=1)
    daily = {START + timedelta(days=i): 50.0 for i in range(28)}
    series = load_series(daily, START, START + timedelta(days=27))
    assert series[-1].ctl > 0 and series[-1].atl > series[-1].ctl
    assert acwr(daily, START + timedelta(days=27)) == pytest.approx(1.0)
    assert readiness(tsb=-30, acwr_value=1.6, sleep_hours=5).score < 45
    assert readiness(tsb=8, acwr_value=1.0, sleep_hours=8).score >= 70


def test_analysis_intervals_with_laps():
    plan = _plan("10k", weeks=12)
    w = next(w for w in plan.all_workouts() if w.type == "intervals")
    rep = w.steps[1]
    target = rep.steps[0].target
    rep_m = rep.steps[0].distance_m
    fast = target.fast_s_per_km - 15
    laps = [Lap(distance_m=2000, duration_s=700)] + [Lap(distance_m=rep_m, duration_s=fast * rep_m / 1000), Lap(distance_m=300, duration_s=120)] * rep.repeats + [Lap(distance_m=1500, duration_s=540)]
    run = ActualRun(distance_m=sum(lap.distance_m for lap in laps), duration_s=sum(lap.duration_s for lap in laps), laps=laps)
    res = analyze(w, run)
    assert res.pace_vs_target == "fast"
    assert len(res.rep_paces) == rep.repeats


def test_analysis_easy_too_fast():
    plan = _plan()
    w = next(w for w in plan.all_workouts() if w.type == "easy")
    run = ActualRun(distance_m=w.distance_km * 1000, duration_s=w.distance_km * 270)  # 4:30/km
    assert analyze(w, run).pace_vs_target == "fast"


def _states(plan):
    return [adapt.WorkoutState(id=i, workout=w) for i, w in enumerate(plan.all_workouts())]


def test_missed_key_workout_moved_or_dropped():
    plan = _plan()
    states = _states(plan)
    week2 = [s for s in states if plan.weeks[2].start_date <= s.workout.date < plan.weeks[2].start_date + timedelta(days=7)]
    key = next(s for s in week2 if s.workout.key and s.workout.type != "long")
    today = key.workout.date + timedelta(days=1)
    # mark earlier workouts completed
    for s in states:
        if s.workout.date < key.workout.date:
            s.status = "completed"
    adjs = adapt.reschedule_missed(states, today)
    assert adjs and adjs[0].actions[0].workout_id == key.id
    assert adjs[0].actions[0].op in ("move", "drop")


def test_pace_insight():
    plan = _plan()
    states = _states(plan)
    q = [s for s in states if s.workout.key and s.workout.type not in ("long", "race")][:4]
    for s in q:
        s.status, s.pace_verdict, s.rpe = "completed", "fast", 6
    adj = adapt.pace_insight(states, 40)
    assert adj and adj.kind == "pace_up" and adj.requires_confirmation


def test_break_and_nf100():
    assert adapt.detect_break(START, START + timedelta(days=3)) is None
    b = adapt.detect_break(START, START + timedelta(days=20))
    assert b and b.actions[0].params["volume_factor"] == 0.6
    plan = _plan()
    states = _states(plan)
    adj = adapt.not_feeling_100(states, START + timedelta(days=14), "sick", 3, pace_zones(40))
    assert all(a.op in ("drop", "replace") for a in adj.actions) and adj.actions


def test_scale_workout():
    plan = _plan()
    w = next(w for w in plan.all_workouts() if w.type == "easy")
    s = adapt.scale_workout(w, 0.5, pace_zones(40))
    assert s.distance_km < w.distance_km


def test_fitness_estimation():
    # runs at easy pace ~6:00/km with HR 140 (rest 50, max 190)
    samples = [RunSample(distance_m=8000, duration_s=2880, avg_hr=140) for _ in range(4)]
    v = estimate_vdot(samples, 50, 190)
    assert v and 35 < v < 60
    assert [p.distance for p in predictions(45)] == ["5k", "10k", "half", "marathon"]
