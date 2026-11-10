"""Workout builders. Each returns a PlannedWorkout with structured steps.

Paces come from the zones of the week's VDOT. Distances are estimated so the
weekly volume can be balanced.
"""

from __future__ import annotations

from datetime import date

from .models import PlannedWorkout, Step, Target
from .zones import PaceRange, fmt_pace

WU_M = 2000.0  # default warm-up
CD_M = 1500.0


def _t(z: PaceRange) -> Target:
    return Target(zone=z.zone, fast_s_per_km=round(z.fast_s_per_km, 1), slow_s_per_km=round(z.slow_s_per_km, 1))


def _steps_distance_m(steps: list[Step], zones: dict[str, PaceRange]) -> float:
    total = 0.0
    for s in steps:
        if s.kind == "repeat":
            total += (s.repeats or 1) * _steps_distance_m(s.steps or [], zones)
            continue
        if s.distance_m:
            total += s.distance_m
        elif s.duration_s:
            pace = (s.target.fast_s_per_km + s.target.slow_s_per_km) / 2 if s.target and s.target.fast_s_per_km else zones["easy"].mid
            if s.kind == "recovery" and s.target is None:
                pace = zones["recovery"].slow_s_per_km
            total += s.duration_s / pace * 1000.0
    return total


def _steps_duration_s(steps: list[Step], zones: dict[str, PaceRange]) -> float:
    total = 0.0
    for s in steps:
        if s.kind == "repeat":
            total += (s.repeats or 1) * _steps_duration_s(s.steps or [], zones)
            continue
        if s.duration_s:
            total += s.duration_s
        elif s.distance_m:
            pace = (s.target.fast_s_per_km + s.target.slow_s_per_km) / 2 if s.target and s.target.fast_s_per_km else zones["easy"].mid
            total += s.distance_m / 1000.0 * pace
    return total


def finalize(w: PlannedWorkout, zones: dict[str, PaceRange]) -> PlannedWorkout:
    if w.steps:
        w.distance_km = round(_steps_distance_m(w.steps, zones) / 1000.0, 1)
        w.duration_min = round(_steps_duration_s(w.steps, zones) / 60.0)
    return w


def _wu(zones):
    return Step(kind="warmup", distance_m=WU_M, target=_t(zones["easy"]), note="Khởi động chạy nhẹ + động tác bổ trợ")


def _cd(zones):
    return Step(kind="cooldown", distance_m=CD_M, target=_t(zones["easy"]), note="Thả lỏng")


def easy(d: date, km: float, zones, strides: int = 0, recovery: bool = False) -> PlannedWorkout:
    z = zones["recovery" if recovery else "easy"]
    steps = [Step(kind="run", distance_m=km * 1000, target=_t(z))]
    desc = f"Chạy thoải mái, nói chuyện được. Pace {fmt_pace(z.fast_s_per_km)}–{fmt_pace(z.slow_s_per_km)}."
    if strides:
        steps.append(
            Step(
                kind="repeat",
                repeats=strides,
                steps=[
                    Step(kind="run", duration_s=20, target=_t(zones["repetition"]), note="Strides: tăng tốc mượt, thả lỏng"),
                    Step(kind="recovery", duration_s=60, note="Đi bộ/chạy rất nhẹ"),
                ],
            )
        )
        desc += f" Kết thúc bằng {strides} x 20s strides."
    w = PlannedWorkout(
        date=d,
        type="recovery" if recovery else "easy",
        title=("Chạy hồi phục" if recovery else "Chạy nhẹ") + f" {km:g} km",
        description=desc,
        steps=steps,
    )
    return finalize(w, zones)


def long_run(d: date, km: float, zones, finish_zone: str | None = None, finish_km: float = 0) -> PlannedWorkout:
    if finish_zone and finish_km > 0:
        steps = [
            Step(kind="run", distance_m=(km - finish_km) * 1000, target=_t(zones["easy"])),
            Step(kind="run", distance_m=finish_km * 1000, target=_t(zones[finish_zone]), note="Phần cuối ở pace mục tiêu"),
        ]
        title = f"Long run {km:g} km ({finish_km:g} km cuối pace {'M' if finish_zone == 'marathon' else 'HM'})"
        desc = "Chạy dài, phần cuối tập pace thi đấu. Tập tiếp nước/gel như ngày thi."
    else:
        steps = [Step(kind="run", distance_m=km * 1000, target=_t(zones["easy"]))]
        title = f"Long run {km:g} km"
        desc = "Chạy dài nhẹ nhàng, xây sức bền. Mang nước nếu trên 75 phút."
    w = PlannedWorkout(date=d, type="long", title=title, description=desc, steps=steps, key=True)
    return finalize(w, zones)


def tempo(d: date, minutes: float, zones) -> PlannedWorkout:
    z = zones["threshold"]
    steps = [_wu(zones), Step(kind="run", duration_s=minutes * 60, target=_t(z)), _cd(zones)]
    w = PlannedWorkout(
        date=d,
        type="tempo",
        title=f"Tempo {minutes:g} phút",
        description=f"Chạy liên tục ở ngưỡng ({fmt_pace(z.fast_s_per_km)}–{fmt_pace(z.slow_s_per_km)}): 'khó nhưng kiểm soát được'.",
        steps=steps,
        key=True,
    )
    return finalize(w, zones)


def cruise_intervals(d: date, reps: int, rep_m: float, zones) -> PlannedWorkout:
    z = zones["threshold"]
    steps = [
        _wu(zones),
        Step(kind="repeat", repeats=reps, steps=[Step(kind="run", distance_m=rep_m, target=_t(z)), Step(kind="recovery", duration_s=60)]),
        _cd(zones),
    ]
    w = PlannedWorkout(
        date=d,
        type="tempo",
        title=f"Cruise intervals {reps} x {rep_m / 1000:g} km",
        description=f"{reps} lần {rep_m / 1000:g} km ở pace ngưỡng, nghỉ 60s chạy nhẹ.",
        steps=steps,
        key=True,
    )
    return finalize(w, zones)


def intervals(d: date, reps: int, rep_m: float, zones, zone: str = "interval", rest_s: float | None = None) -> PlannedWorkout:
    z = zones[zone]
    rest = rest_s if rest_s is not None else max(60.0, rep_m / 1000 * z.mid * 0.8)
    steps = [
        _wu(zones),
        Step(kind="repeat", repeats=reps, steps=[Step(kind="run", distance_m=rep_m, target=_t(z)), Step(kind="recovery", duration_s=round(rest))]),
        _cd(zones),
    ]
    label = {"interval": "VO2max", "repetition": "tốc độ", "half": "pace HM", "marathon": "pace M"}.get(zone, zone)
    w = PlannedWorkout(
        date=d,
        type="intervals" if zone in ("interval", "repetition") else "race_pace",
        title=f"Interval {reps} x {rep_m:g} m ({label})",
        description=f"{reps} lần {rep_m:g} m ở {fmt_pace(z.fast_s_per_km)}–{fmt_pace(z.slow_s_per_km)}, nghỉ {round(rest)}s chạy rất nhẹ.",
        steps=steps,
        key=True,
    )
    return finalize(w, zones)


def fartlek(d: date, reps: int, zones, on_s: int = 60, off_s: int = 60) -> PlannedWorkout:
    steps = [
        _wu(zones),
        Step(
            kind="repeat",
            repeats=reps,
            steps=[Step(kind="run", duration_s=on_s, target=_t(zones["interval"])), Step(kind="recovery", duration_s=off_s, target=_t(zones["easy"]))],
        ),
        _cd(zones),
    ]
    w = PlannedWorkout(
        date=d,
        type="fartlek",
        title=f"Fartlek {reps} x {on_s}s/{off_s}s",
        description="Đổi tốc độ theo cảm giác: phần nhanh mạnh nhưng không hết sức.",
        steps=steps,
        key=True,
    )
    return finalize(w, zones)


def hills(d: date, reps: int, zones, rep_s: int = 60) -> PlannedWorkout:
    steps = [
        _wu(zones),
        Step(
            kind="repeat",
            repeats=reps,
            steps=[Step(kind="run", duration_s=rep_s, note="Chạy lên dốc mạnh, giữ dáng chạy"), Step(kind="recovery", duration_s=rep_s * 1.5, note="Chạy/đi bộ xuống dốc")],
        ),
        _cd(zones),
    ]
    w = PlannedWorkout(
        date=d,
        type="hills",
        title=f"Chạy dốc {reps} x {rep_s}s",
        description="Tìm dốc 4–8%. Lên dốc với nỗ lực ~ pace 5K, xuống dốc hồi phục. Không có dốc: dùng máy chạy độ dốc 5%.",
        steps=steps,
        key=True,
    )
    w = finalize(w, zones)
    return w


def progression(d: date, km: float, zones) -> PlannedWorkout:
    a, b = km * 0.5, km * 0.3
    c = km - a - b
    steps = [
        Step(kind="run", distance_m=a * 1000, target=_t(zones["easy"])),
        Step(kind="run", distance_m=b * 1000, target=_t(zones["marathon"])),
        Step(kind="run", distance_m=c * 1000, target=_t(zones["threshold"])),
    ]
    w = PlannedWorkout(
        date=d,
        type="progression",
        title=f"Progression run {km:g} km",
        description="Tăng dần tốc độ: nhẹ → pace marathon → ngưỡng.",
        steps=steps,
        key=True,
    )
    return finalize(w, zones)


def race_pace_block(d: date, reps: int, rep_m: float, zone: str, zones, rest_s: float = 90) -> PlannedWorkout:
    return intervals(d, reps, rep_m, zones, zone=zone, rest_s=rest_s)


def race(d: date, distance_key: str, distance_km: float, target_time_s: float | None, zones) -> PlannedWorkout:
    desc = "Ngày thi! Khởi động 10 phút, xuất phát chậm hơn mục tiêu 2–3s/km trong 2 km đầu."
    if target_time_s:
        pace = target_time_s / distance_km
        h, rem = divmod(int(target_time_s), 3600)
        desc += f" Mục tiêu {h}:{rem // 60:02d}:{rem % 60:02d} (~{fmt_pace(pace)})."
    return PlannedWorkout(
        date=d,
        type="race",
        title=f"RACE {distance_key.upper()}",
        description=desc,
        distance_km=round(distance_km, 1),
        duration_min=round((target_time_s or distance_km * zones["easy"].fast_s_per_km) / 60),
        steps=[Step(kind="run", distance_m=distance_km * 1000)],
        key=True,
    )


def shakeout(d: date, zones) -> PlannedWorkout:
    return easy(d, 3, zones, strides=4).model_copy(update={"type": "shakeout", "title": "Shakeout 3 km + strides"})


STRENGTH_A = [
    {"name": "Squat (tạ đơn / bodyweight)", "sets": 3, "reps": "10"},
    {"name": "Lunge lùi", "sets": 3, "reps": "8/chân"},
    {"name": "Single-leg deadlift", "sets": 3, "reps": "8/chân"},
    {"name": "Calf raise 1 chân", "sets": 3, "reps": "12/chân"},
    {"name": "Plank", "sets": 3, "reps": "40s"},
    {"name": "Side plank", "sets": 2, "reps": "30s/bên"},
]
STRENGTH_B = [
    {"name": "Step-up lên bục", "sets": 3, "reps": "10/chân"},
    {"name": "Glute bridge 1 chân", "sets": 3, "reps": "10/chân"},
    {"name": "Bulgarian split squat", "sets": 3, "reps": "8/chân"},
    {"name": "Nordic curl (hỗ trợ)", "sets": 2, "reps": "5"},
    {"name": "Dead bug", "sets": 3, "reps": "10"},
    {"name": "Bật nhảy pogo", "sets": 3, "reps": "20"},
]


def strength(d: date, variant: str = "A", light: bool = False) -> PlannedWorkout:
    ex = STRENGTH_A if variant == "A" else STRENGTH_B
    if light:
        ex = [{**e, "sets": max(1, e["sets"] - 1)} for e in ex]
    return PlannedWorkout(
        date=d,
        type="strength",
        title=f"Sức mạnh cho runner ({variant})",
        description="25–35 phút. Làm sau buổi chạy nhẹ hoặc ngày không chạy. Không làm trước ngày bài nặng.",
        duration_min=25 if light else 35,
        exercises=ex,
    )
