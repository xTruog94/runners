"""Fitness estimation from everyday runs (no race needed) and race prediction."""

from __future__ import annotations

from statistics import median

from pydantic import BaseModel

from .vdot import RACE_DISTANCES_M, _vo2, predict_race_time


class RunSample(BaseModel):
    distance_m: float
    duration_s: float
    avg_hr: float | None = None


def vdot_from_hr_run(s: RunSample, rest_hr: float, max_hr: float) -> float | None:
    """Swain: %HRR ≈ %VO2R. VO2max ≈ (VO2(v) - 3.5)/%HRR + 3.5."""
    if not s.avg_hr or s.duration_s < 20 * 60 or s.distance_m < 3000:
        return None
    hrr = (s.avg_hr - rest_hr) / (max_hr - rest_hr)
    if not 0.55 <= hrr <= 0.92:
        return None
    v = s.distance_m / (s.duration_s / 60)
    vo2 = _vo2(v)
    return (vo2 - 3.5) / hrr + 3.5


def estimate_vdot(samples: list[RunSample], rest_hr: float | None, max_hr: float | None) -> float | None:
    if not rest_hr or not max_hr:
        return None
    vals = [v for s in samples if (v := vdot_from_hr_run(s, rest_hr, max_hr))]
    if len(vals) < 3:
        return None
    return round(median(vals), 1)


class Prediction(BaseModel):
    distance: str
    time_s: float
    pace_s_per_km: float


def predictions(vdot: float) -> list[Prediction]:
    out = []
    for k in ("5k", "10k", "half", "marathon"):
        d = RACE_DISTANCES_M[k]
        t = predict_race_time(vdot, d)
        out.append(Prediction(distance=k, time_s=round(t), pace_s_per_km=round(t / (d / 1000), 1)))
    return out
