"""Training plan generator.

Rules (evidence-informed, conservative by design):
* weekly volume grows ~8%/week, never >10%; every 4th week is a cut-back (-25%)
* long run <= ~30-40% of weekly volume and capped per goal distance
* ~80/20 easy/hard: max 2 quality sessions per week, never on consecutive days
* quality volume caps: T <= 10% weekly km, I <= 8% (max 10 km), R <= 5%
* VDOT progresses from current fitness towards the goal by <= 1 point / 4 weeks
* taper 1-3 weeks depending on race distance
"""

from __future__ import annotations

from datetime import date, timedelta

from . import library as L
from .models import Goal, Plan, PlannedWeek, PlannedWorkout, RunnerProfile
from .vdot import RACE_DISTANCES_M, predict_race_time, vdot_from_easy_pace, vdot_from_race
from .zones import pace_zones

GOAL_KM = {"5k": 5.0, "10k": 10.0, "half": 21.0975, "marathon": 42.195, "general": 0.0}

PEAK_KM = {  # peak weekly km by goal & level
    "5k": {"beginner": 25, "intermediate": 40, "advanced": 60},
    "10k": {"beginner": 30, "intermediate": 45, "advanced": 70},
    "half": {"beginner": 35, "intermediate": 55, "advanced": 80},
    "marathon": {"beginner": 45, "intermediate": 65, "advanced": 95},
    "general": {"beginner": 20, "intermediate": 35, "advanced": 55},
}
LONG_CAP_KM = {"5k": 14, "10k": 18, "half": 22, "marathon": 32, "general": 16}
TAPER_WEEKS = {"5k": 1, "10k": 1, "half": 2, "marathon": 3, "general": 0}
TAPER_FACTORS = {1: [0.6], 2: [0.7, 0.45], 3: [0.75, 0.6, 0.4]}
MIN_WEEKS = 4
MAX_WEEKS = 30
GENERAL_BLOCK_WEEKS = 12


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def current_vdot(profile: RunnerProfile) -> float:
    if profile.recent_race:
        return vdot_from_race(profile.recent_race.distance_m, profile.recent_race.time_s)
    if profile.easy_pace_s_per_km:
        return vdot_from_easy_pace(profile.easy_pace_s_per_km)
    return {"beginner": 30.0, "intermediate": 40.0, "advanced": 50.0}[profile.level]


def split_phases(n_weeks: int, distance: str) -> list[str]:
    if distance == "general":
        base = n_weeks // 2
        return ["base"] * base + ["maintain"] * (n_weeks - base)
    taper = TAPER_WEEKS[distance]
    if n_weeks < 8:
        taper = min(taper, 1)
    rest = n_weeks - taper
    peak = max(1, round(rest * 0.2))
    build = max(1, round(rest * 0.4))
    base = max(1, rest - peak - build)
    while base + build + peak > rest:  # tiny plans
        if build > 1:
            build -= 1
        elif peak > 1:
            peak -= 1
        else:
            base -= 1
    return ["base"] * base + ["build"] * build + ["peak"] * peak + ["taper"] * taper


def volume_curve(phases: list[str], start_km: float, peak_km: float, distance: str) -> tuple[list[float], list[bool]]:
    vols: list[float] = []
    cut: list[bool] = []
    last_build = start_km
    taper_seen = 0
    n_taper = phases.count("taper")
    for i, ph in enumerate(phases):
        if ph == "taper":
            f = TAPER_FACTORS[n_taper][taper_seen]
            taper_seen += 1
            vols.append(round(last_build * f, 1))
            cut.append(False)
            continue
        is_cut = i > 0 and (i + 1) % 4 == 0
        if is_cut:
            vols.append(round(last_build * 0.75, 1))
            cut.append(True)
            continue
        target = start_km if i == 0 else min(peak_km, last_build * 1.08)
        last_build = max(last_build, target) if i else target
        vols.append(round(last_build, 1))
        cut.append(False)
    return vols, cut


def _space_days(available: list[int], n: int, long_day: int) -> list[int]:
    """Choose n training days from available, always including long_day, spread out."""
    avail = sorted(set(available))
    if long_day not in avail:
        long_day = avail[-1]
    n = max(1, min(n, len(avail)))
    chosen = [long_day]
    while len(chosen) < n:
        best, best_score = None, -1.0
        for d in avail:
            if d in chosen:
                continue
            score = min(min(abs(d - c), 7 - abs(d - c)) for c in chosen)
            if score > best_score:
                best, best_score = d, score
        chosen.append(best)  # type: ignore[arg-type]
    return sorted(chosen)


def _pick_quality_days(days: list[int], long_day: int, q: int) -> list[int]:
    """Quality days: not adjacent to the long run or each other when possible."""

    def cyc(a, b):
        return min(abs(a - b), 7 - abs(a - b))

    candidates = [d for d in days if d != long_day]
    picked: list[int] = []
    # prefer days >= 2 apart from long run and each other, then relax
    for min_gap in (2, 1):
        for d in sorted(candidates, key=lambda x: -cyc(x, long_day)):
            if len(picked) >= q:
                break
            if d in picked:
                continue
            if cyc(d, long_day) >= min_gap and all(cyc(d, p) >= min_gap for p in picked):
                picked.append(d)
    return sorted(picked[:q])


def _quality_for(distance: str, phase: str, slot: int, wk_in_phase: int, weekly_km: float, zones, d: date, level: str) -> PlannedWorkout:
    """slot 0 = primary session (threshold-ish), slot 1 = secondary (speed / race pace)."""
    t_cap = weekly_km * 0.10
    i_cap = min(10.0, weekly_km * 0.08)
    prog = wk_in_phase  # progression inside the phase
    beginner = level == "beginner"

    if phase in ("base", "maintain"):
        if slot == 0:
            if beginner:
                return L.fartlek(d, min(6 + prog, 10), zones, on_s=45, off_s=90)
            return L.hills(d, min(6 + prog, 10), zones)
        return L.fartlek(d, min(8 + prog, 12), zones)

    if phase == "build":
        if slot == 0:
            if prog % 2 == 0:
                minutes = min(15 + 5 * prog, 30, t_cap * zones["threshold"].mid / 60)
                return L.tempo(d, max(12, round(minutes)), zones)
            reps = max(2, min(5, int(t_cap / 1.6)))
            return L.cruise_intervals(d, reps, 1600, zones)
        if distance in ("5k", "10k"):
            rep_m = 1000 if prog % 2 == 0 else 800
            reps = max(3, min(int(i_cap * 1000 / rep_m), 6 + prog))
            return L.intervals(d, reps, rep_m, zones)
        if distance == "half":
            return L.intervals(d, max(4, min(6, int(i_cap))), 1000, zones)
        return L.progression(d, min(10 + 2 * prog, 16), zones)

    if phase == "peak":
        if distance == "5k":
            if slot == 0:
                return L.intervals(d, max(4, min(6, int(i_cap))), 1000, zones)
            return L.intervals(d, max(6, min(10, int(weekly_km * 0.05 / 0.4))), 400, zones, zone="repetition")
        if distance == "10k":
            if slot == 0:
                return L.cruise_intervals(d, 3, 3000, zones)
            return L.intervals(d, max(4, min(6, int(i_cap))), 1000, zones)
        if distance == "half":
            if slot == 0:
                reps, rep_m = [(3, 3000), (2, 5000), (4, 2000)][prog % 3]
                return L.race_pace_block(d, reps, rep_m, "half", zones)
            return L.cruise_intervals(d, max(3, min(5, int(t_cap / 1.6))), 1600, zones)
        # marathon
        if slot == 0:
            return L.tempo(d, min(30, max(20, round(t_cap * zones["threshold"].mid / 60))), zones)
        return L.race_pace_block(d, 2 + min(prog, 2), 3000, "marathon", zones, rest_s=60)

    # taper: short sharpener at race pace
    zone = {"5k": "interval", "10k": "threshold", "half": "half", "marathon": "marathon"}.get(distance, "threshold")
    return L.race_pace_block(d, 4, 1000, zone, zones, rest_s=90)


def build_week(
    index: int,
    start: date,
    phase: str,
    target_km: float,
    is_cut: bool,
    vdot: float,
    wk_in_phase: int,
    goal: Goal,
    profile: RunnerProfile,
    race_day: date | None,
    heat: float = 1.0,
) -> PlannedWeek:
    zones = pace_zones(vdot, heat)
    distance = goal.distance
    days = _space_days(profile.available_days, profile.days_per_week, profile.long_run_day)
    long_day = profile.long_run_day if profile.long_run_day in days else days[-1]
    n = len(days)
    q = 1 if n <= 3 else 2
    if is_cut or phase == "taper":
        q = 1
    if profile.level == "beginner" and phase == "base":
        q = 1 if n <= 4 else q
    quality_days = _pick_quality_days(days, long_day, q)

    week = PlannedWeek(index=index, start_date=start, phase=phase, target_km=target_km, is_cutback=is_cut, vdot=round(vdot, 1))
    workouts: dict[int, PlannedWorkout] = {}

    is_race_week = race_day is not None and start <= race_day < start + timedelta(days=7)

    # --- long run
    long_frac = {2: 0.45, 3: 0.4, 4: 0.35, 5: 0.32}.get(n, 0.28)
    long_km = min(LONG_CAP_KM[distance], max(5.0, target_km * long_frac))
    if profile.longest_recent_run_km and index < 3:
        long_km = min(long_km, profile.longest_recent_run_km + 2 * (index + 1))
    long_km = round(long_km)
    if not is_race_week:
        d = start + timedelta(days=long_day)
        if phase == "peak" and distance == "marathon" and not is_cut:
            workouts[long_day] = L.long_run(d, long_km, zones, "marathon", min(12, 6 + 3 * wk_in_phase))
        elif phase == "peak" and distance == "half" and not is_cut:
            workouts[long_day] = L.long_run(d, long_km, zones, "half", 4)
        else:
            workouts[long_day] = L.long_run(d, long_km, zones)
    else:
        rd = race_day.weekday()  # type: ignore[union-attr]
        workouts[rd] = L.race(race_day, distance, GOAL_KM[distance], goal.target_time_s, zones)  # type: ignore[arg-type]
        days = sorted(set(days) | {rd})
        if rd - 1 >= 0:
            workouts[rd - 1] = L.shakeout(start + timedelta(days=rd - 1), zones)
            days = sorted(set(days) | {rd - 1})
        # one sharpener early in the week, far from race day
        quality_days = [d for d in quality_days if d <= rd - 3][:1]

    # --- quality sessions
    for slot, qd in enumerate(quality_days):
        if qd in workouts:
            continue
        workouts[qd] = _quality_for(distance, phase, slot, wk_in_phase, target_km, zones, start + timedelta(days=qd), profile.level)

    # --- easy runs fill the remaining volume
    easy_days = [d for d in days if d not in workouts]
    used = sum(w.distance_km for w in workouts.values())
    remaining = max(0.0, target_km - used)
    if easy_days:
        per = remaining / len(easy_days)
        for i, ed in enumerate(easy_days):
            km = round(max(3.0, min(per, long_km * 0.75)))
            nxt, prv = (ed + 1) % 7, (ed - 1) % 7
            next_is_quality = nxt in quality_days or nxt == long_day
            recovery = prv == long_day or (prv in quality_days and per < 6)
            strides = 0
            if profile.strides and not recovery and phase != "taper" and not next_is_quality and i == 0:
                strides = 4 if phase == "base" else 6
            workouts[ed] = L.easy(start + timedelta(days=ed), km, zones, strides=strides, recovery=recovery)

    # --- strength
    if profile.include_strength and phase != "taper" and not is_race_week:
        n_str = 1 if (phase == "peak" or is_cut) else 2
        # "keep hard days hard": strength after quality sessions or on easy days,
        # never on the long-run day or the day before a key session
        key_days = set(quality_days) | {long_day}
        candidates = [d for d in range(7) if d != long_day and (d + 1) % 7 not in key_days]
        candidates.sort(key=lambda d: (d not in quality_days, d not in workouts, d))
        picked_str: list[int] = []
        for d in candidates:
            if all(min(abs(d - p), 7 - abs(d - p)) >= 2 for p in picked_str):
                picked_str.append(d)
        candidates = picked_str
        for j, sd in enumerate(candidates[:n_str]):
            strength = L.strength(start + timedelta(days=sd), "A" if j == 0 else "B", light=is_cut)
            week.workouts.append(strength)

    week.workouts.extend(sorted(workouts.values(), key=lambda w: w.date))
    week.workouts.sort(key=lambda w: (w.date, w.type == "strength"))
    if race_day:
        week.workouts = [w for w in week.workouts if w.date <= race_day]
    if goal.start_date > start:
        week.workouts = [w for w in week.workouts if w.date >= goal.start_date]
    return week


def generate_plan(goal: Goal, profile: RunnerProfile, heat: float = 1.0, vdot_override: float | None = None) -> Plan:
    warnings: list[str] = []
    start = monday(goal.start_date)
    if goal.distance == "general" or goal.race_date is None:
        n_weeks = GENERAL_BLOCK_WEEKS
        race_day = None
        if goal.distance != "general":
            warnings.append("Chưa có ngày thi: tạo chu kỳ 12 tuần không taper.")
    else:
        race_day = goal.race_date
        n_weeks = (monday(race_day) - start).days // 7 + 1
        if n_weeks < MIN_WEEKS:
            warnings.append(f"Chỉ còn {n_weeks} tuần tới ngày thi — giáo án rút gọn, ưu tiên giữ sức.")
            n_weeks = max(n_weeks, 1)
        if n_weeks > MAX_WEEKS:
            warnings.append(f"Còn {n_weeks} tuần: các tuần đầu là giai đoạn duy trì, giáo án chính {MAX_WEEKS} tuần.")
            start = monday(race_day) - timedelta(weeks=MAX_WEEKS - 1)
            n_weeks = MAX_WEEKS

    phases = split_phases(n_weeks, goal.distance)

    v0 = vdot_override if vdot_override else current_vdot(profile)
    goal_v = v0
    if goal.target_time_s and goal.distance in RACE_DISTANCES_M:
        goal_v = vdot_from_race(RACE_DISTANCES_M[goal.distance], goal.target_time_s)
        max_gain = max(1.0, n_weeks / 4.0)
        if goal_v - v0 > max_gain:
            realistic = predict_race_time(v0 + max_gain, RACE_DISTANCES_M[goal.distance])
            h, r = divmod(int(realistic), 3600)
            warnings.append(
                f"Mục tiêu khá tham vọng so với thể lực hiện tại (VDOT {v0:.1f} → {goal_v:.1f}). "
                f"Mục tiêu thực tế hơn: ~{h}:{r // 60:02d}:{r % 60:02d}. Pace sẽ tăng dần, đánh giá lại sau mỗi 4 tuần."
            )
            goal_v = v0 + max_gain
        goal_v = max(goal_v, v0)

    start_km = max(profile.current_weekly_km, 3.0 * min(profile.days_per_week, len(profile.available_days)))
    peak_km = PEAK_KM[goal.distance][profile.level]
    peak_km = max(peak_km if start_km < peak_km else start_km, start_km)
    if profile.current_weekly_km < peak_km * 0.5 and n_weeks < 12:
        warnings.append("Khối lượng hiện tại thấp so với cự ly mục tiêu; giáo án tăng chậm để tránh chấn thương.")
    vols, cuts = volume_curve(phases, start_km, peak_km, goal.distance)

    weeks: list[PlannedWeek] = []
    phase_counter: dict[str, int] = {}
    build_weeks = sum(1 for p in phases if p != "taper")
    for i, (ph, vol, cut) in enumerate(zip(phases, vols, cuts)):
        frac = min(1.0, i / max(1, build_weeks - 1))
        vdot = v0 + (goal_v - v0) * frac
        wk_in_phase = phase_counter.get(ph, 0)
        phase_counter[ph] = wk_in_phase + 1
        weeks.append(
            build_week(i, start + timedelta(weeks=i), ph, vol, cut, vdot, wk_in_phase, goal, profile, race_day, heat)
        )

    return Plan(goal=goal, profile=profile, start_vdot=round(v0, 1), goal_vdot=round(goal_v, 1), weeks=weeks, warnings=warnings)
