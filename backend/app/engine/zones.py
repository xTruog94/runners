"""Training pace zones derived from VDOT."""

from __future__ import annotations

from pydantic import BaseModel

from .vdot import RACE_DISTANCES_M, predict_race_time, velocity_for_vo2

# Fraction of VO2max for each zone (lower, upper bound). Daniels-style.
_ZONE_FRACTIONS = {
    "recovery": (0.55, 0.62),
    "easy": (0.62, 0.74),
    "threshold": (0.86, 0.89),
    "interval": (0.97, 1.0),
}

ZONE_LABELS_VI = {
    "recovery": "Hồi phục",
    "easy": "Chạy nhẹ (E)",
    "marathon": "Pace marathon (M)",
    "half": "Pace half marathon",
    "threshold": "Ngưỡng / Tempo (T)",
    "interval": "Interval (I)",
    "repetition": "Tốc độ (R)",
}


class PaceRange(BaseModel):
    zone: str
    fast_s_per_km: float  # lower number = faster
    slow_s_per_km: float

    @property
    def mid(self) -> float:
        return (self.fast_s_per_km + self.slow_s_per_km) / 2


def _pace_for_fraction(vdot: float, fraction: float) -> float:
    v = velocity_for_vo2(vdot * fraction)  # m/min
    return 60000.0 / v  # s/km


def _race_pace(vdot: float, key: str) -> float:
    d = RACE_DISTANCES_M[key]
    return predict_race_time(vdot, d) / (d / 1000.0)


def pace_zones(vdot: float, heat_factor: float = 1.0) -> dict[str, PaceRange]:
    """All zones. heat_factor > 1 slows every pace (e.g. 1.03 = 3% slower)."""
    zones: dict[str, PaceRange] = {}
    for name, (lo, hi) in _ZONE_FRACTIONS.items():
        fast = _pace_for_fraction(vdot, hi)
        slow = _pace_for_fraction(vdot, lo)
        zones[name] = PaceRange(zone=name, fast_s_per_km=fast, slow_s_per_km=slow)
    for name, key, spread in (("marathon", "marathon", 4), ("half", "half", 4)):
        p = _race_pace(vdot, key)
        zones[name] = PaceRange(zone=name, fast_s_per_km=p - spread, slow_s_per_km=p + spread)
    r = _race_pace(vdot, "mile")
    zones["repetition"] = PaceRange(zone="repetition", fast_s_per_km=r - 4, slow_s_per_km=r + 2)
    if heat_factor != 1.0:
        zones = {
            k: PaceRange(zone=k, fast_s_per_km=z.fast_s_per_km * heat_factor, slow_s_per_km=z.slow_s_per_km * heat_factor)
            for k, z in zones.items()
        }
    return zones


def classify_pace(vdot: float, pace_s_per_km: float) -> str:
    """Return the zone whose range is closest to the given pace."""
    zones = pace_zones(vdot)
    best, best_d = "easy", float("inf")
    for name, z in zones.items():
        if z.fast_s_per_km <= pace_s_per_km <= z.slow_s_per_km:
            return name
        d = min(abs(pace_s_per_km - z.fast_s_per_km), abs(pace_s_per_km - z.slow_s_per_km))
        if d < best_d:
            best, best_d = name, d
    return best


def fmt_pace(s_per_km: float) -> str:
    s = int(round(s_per_km))
    return f"{s // 60}:{s % 60:02d}/km"
