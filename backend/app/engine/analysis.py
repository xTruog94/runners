"""Matching actual activities to planned workouts and post-run analysis."""

from __future__ import annotations

from pydantic import BaseModel

from .models import PlannedWorkout, Step
from .zones import fmt_pace


class Lap(BaseModel):
    distance_m: float
    duration_s: float
    avg_hr: float | None = None


class ActualRun(BaseModel):
    distance_m: float
    duration_s: float
    avg_hr: float | None = None
    max_hr: float | None = None
    laps: list[Lap] = []
    rpe: int | None = None


class RunAnalysis(BaseModel):
    compliance: float  # 0..1.5 (actual/planned)
    pace_s_per_km: float
    pace_vs_target: str  # "on" | "fast" | "slow" | "n/a"
    rep_paces: list[float] = []
    hr_drift_pct: float | None = None
    score: int  # 0-100 execution score
    summary: str
    tips: list[str] = []


def _main_target(w: PlannedWorkout):
    """The target range of the 'work' part of a workout."""

    def walk(steps: list[Step]):
        for s in steps:
            if s.kind == "repeat":
                for inner in s.steps or []:
                    if inner.kind == "run" and inner.target and inner.target.fast_s_per_km:
                        return inner.target, s.repeats, inner.distance_m
            elif s.kind == "run" and s.target and s.target.fast_s_per_km:
                return s.target, None, s.distance_m
        return None, None, None

    if w.type == "long":
        runs = [s for s in w.steps if s.kind == "run" and s.target]
        if runs:
            return runs[0].target, None, None
    return walk(w.steps)


def analyze(w: PlannedWorkout, run: ActualRun) -> RunAnalysis:
    planned_m = max(1.0, w.distance_km * 1000)
    compliance = run.distance_m / planned_m
    pace = run.duration_s / max(0.001, run.distance_m / 1000)
    target, reps, rep_m = _main_target(w)
    tips: list[str] = []
    rep_paces: list[float] = []
    verdict = "n/a"

    if target and reps and rep_m and run.laps:
        # find laps that look like work reps (distance close to rep length, fastest)
        cands = [lap for lap in run.laps if abs(lap.distance_m - rep_m) / rep_m < 0.15]
        cands.sort(key=lambda lap: lap.duration_s / lap.distance_m)
        work = cands[:reps]
        rep_paces = [round(lap.duration_s / (lap.distance_m / 1000), 1) for lap in work]
    eval_pace = sum(rep_paces) / len(rep_paces) if rep_paces else pace

    if target and target.fast_s_per_km and target.slow_s_per_km:
        tol = 3.0
        if w.type in ("easy", "recovery", "long") or not rep_paces:
            # for continuous runs use overall pace; workouts with WU/CD -> only judge if laps known
            if w.type in ("easy", "recovery", "long"):
                if pace < target.fast_s_per_km - tol:
                    verdict = "fast"
                elif pace > target.slow_s_per_km + 15:
                    verdict = "slow"
                else:
                    verdict = "on"
        else:
            if eval_pace < target.fast_s_per_km - tol:
                verdict = "fast"
            elif eval_pace > target.slow_s_per_km + tol:
                verdict = "slow"
            else:
                verdict = "on"

    drift = None
    if len(run.laps) >= 4 and all(lap.avg_hr for lap in run.laps):
        half = len(run.laps) // 2
        a = run.laps[:half]
        b = run.laps[half:]

        def eff(ls):  # metres per heartbeat
            return sum(lap.distance_m for lap in ls) / sum(lap.avg_hr * lap.duration_s / 60 for lap in ls)  # type: ignore[operator]

        drift = round((eff(a) / eff(b) - 1) * 100, 1)

    score = 100.0
    score -= min(40.0, abs(1 - min(compliance, 1.2)) * 100 * 0.8)
    if verdict in ("fast", "slow"):
        score -= 15
    if run.rpe and w.type in ("easy", "recovery") and run.rpe >= 7:
        score -= 10
    score = int(max(0, min(100, score)))

    parts = [f"Hoàn thành {run.distance_m / 1000:.2f}/{w.distance_km:g} km ({compliance * 100:.0f}%), pace TB {fmt_pace(pace)}."]
    if rep_paces:
        parts.append("Pace các rep: " + ", ".join(fmt_pace(p) for p in rep_paces) + ".")
    if verdict == "fast":
        if w.type in ("easy", "recovery", "long"):
            tips.append("Bạn chạy nhanh hơn vùng easy. Chạy chậm lại giúp hồi phục và xây nền hiếu khí tốt hơn.")
        else:
            tips.append("Nhanh hơn mục tiêu. Nếu cảm thấy dễ (RPE ≤ 7) nhiều buổi liên tiếp, app sẽ đề xuất tăng pace.")
    elif verdict == "slow":
        tips.append("Chậm hơn mục tiêu. Kiểm tra nhiệt độ/độ ẩm, giấc ngủ; nếu lặp lại app sẽ đề xuất giảm pace.")
    elif verdict == "on":
        tips.append("Đúng vùng pace mục tiêu — rất tốt!")
    if compliance < 0.8:
        tips.append("Buổi tập ngắn hơn kế hoạch khá nhiều.")
    if drift is not None and drift > 5 and w.type in ("easy", "long"):
        tips.append(f"Nhịp tim trôi {drift}% ở nửa sau: cần thêm nước/điện giải hoặc nền hiếu khí còn yếu.")
    return RunAnalysis(
        compliance=round(compliance, 2),
        pace_s_per_km=round(pace, 1),
        pace_vs_target=verdict,
        rep_paces=rep_paces,
        hr_drift_pct=drift,
        score=score,
        summary=" ".join(parts),
        tips=tips,
    )
