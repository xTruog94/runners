"""VDOT model (Daniels & Gilbert) and race-time prediction.

All speeds are in metres/minute inside the formulas, times in minutes.
Public helpers use seconds and metres.
"""

from __future__ import annotations

import math

RACE_DISTANCES_M = {
    "1500m": 1500.0,
    "mile": 1609.344,
    "3k": 3000.0,
    "5k": 5000.0,
    "10k": 10000.0,
    "15k": 15000.0,
    "half": 21097.5,
    "marathon": 42195.0,
}


def _vo2(v_m_min: float) -> float:
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min**2


def _pct_max(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_race(distance_m: float, time_s: float) -> float:
    """VDOT from a race (or all-out time trial) result."""
    if distance_m <= 0 or time_s <= 0:
        raise ValueError("distance and time must be positive")
    t = time_s / 60.0
    v = distance_m / t
    return _vo2(v) / _pct_max(t)


def velocity_for_vo2(vo2: float) -> float:
    """Inverse of _vo2: returns m/min for a given oxygen cost."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def predict_race_time(vdot: float, distance_m: float) -> float:
    """Equivalent race time (seconds) for a distance at a given VDOT (bisection)."""
    lo, hi = 60.0, 60.0 * 60 * 10  # 1 min .. 10 h
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot_from_race(distance_m, mid) > vdot:
            lo = mid  # too fast -> needs more time
        else:
            hi = mid
    return (lo + hi) / 2


def riegel(time_s: float, d1_m: float, d2_m: float, exponent: float = 1.06) -> float:
    return time_s * (d2_m / d1_m) ** exponent


def vdot_from_easy_pace(easy_pace_s_per_km: float) -> float:
    """Rough VDOT estimate for runners without a recent race.

    Assumes the comfortable conversational pace is ~65% of VO2max.
    """
    v = 1000.0 / (easy_pace_s_per_km / 60.0)
    return _vo2(v) / 0.65
