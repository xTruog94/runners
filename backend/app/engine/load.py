"""Training load, fitness/fatigue (CTL/ATL/TSB), ACWR and readiness."""

from __future__ import annotations

import math
from datetime import date, timedelta

from pydantic import BaseModel


class ActivityLoadInput(BaseModel):
    day: date
    duration_s: float
    distance_m: float | None = None
    avg_hr: float | None = None
    elevation_gain_m: float | None = None


def running_tss(duration_s: float, distance_m: float | None, threshold_pace_s_per_km: float, elevation_gain_m: float | None = None) -> float:
    """rTSS = hours * IF^2 * 100 with IF = threshold speed ratio (grade-adjusted roughly)."""
    if not distance_m or distance_m <= 0 or duration_s <= 0:
        return 0.0
    # ~ +10 m of climb ~ +60 m flat equivalent effort (rough grade adjustment)
    eq_dist = distance_m + 6.0 * (elevation_gain_m or 0.0)
    pace = duration_s / (eq_dist / 1000.0)
    intensity = threshold_pace_s_per_km / pace
    return duration_s / 3600.0 * intensity**2 * 100.0


def hr_trimp(duration_s: float, avg_hr: float, rest_hr: float, max_hr: float, male: bool = True) -> float:
    """Banister TRIMP, scaled so 1 h at threshold ~ 100 (like TSS)."""
    if max_hr <= rest_hr:
        return 0.0
    hrr = max(0.0, min(1.0, (avg_hr - rest_hr) / (max_hr - rest_hr)))
    k = 1.92 if male else 1.67
    trimp = duration_s / 60.0 * hrr * 0.64 * math.exp(k * hrr)
    # 60 min at ~88% HRR ≈ 100
    ref = 60 * 0.88 * 0.64 * math.exp(k * 0.88)
    return trimp / ref * 100.0


def activity_load(a: ActivityLoadInput, threshold_pace: float, rest_hr: float | None, max_hr: float | None) -> float:
    if a.distance_m and a.distance_m > 200:
        return running_tss(a.duration_s, a.distance_m, threshold_pace, a.elevation_gain_m)
    if a.avg_hr and rest_hr and max_hr:
        return hr_trimp(a.duration_s, a.avg_hr, rest_hr, max_hr)
    return a.duration_s / 3600.0 * 50.0  # unknown: assume easy effort


class LoadPoint(BaseModel):
    day: date
    load: float
    ctl: float  # fitness (42 d)
    atl: float  # fatigue (7 d)
    tsb: float  # form


def load_series(daily: dict[date, float], start: date, end: date, ctl0: float = 0.0, atl0: float = 0.0) -> list[LoadPoint]:
    out: list[LoadPoint] = []
    ctl, atl = ctl0, atl0
    d = start
    while d <= end:
        tss = daily.get(d, 0.0)
        tsb = ctl - atl  # form going into the day
        ctl += (tss - ctl) / 42.0
        atl += (tss - atl) / 7.0
        out.append(LoadPoint(day=d, load=round(tss, 1), ctl=round(ctl, 1), atl=round(atl, 1), tsb=round(tsb, 1)))
        d += timedelta(days=1)
    return out


def acwr(daily: dict[date, float], today: date) -> float | None:
    acute = sum(daily.get(today - timedelta(days=i), 0.0) for i in range(7)) / 7.0
    chronic = sum(daily.get(today - timedelta(days=i), 0.0) for i in range(28)) / 28.0
    if chronic < 1e-6:
        return None
    return round(acute / chronic, 2)


class Readiness(BaseModel):
    score: int
    label: str
    factors: list[str]


def readiness(
    tsb: float,
    acwr_value: float | None,
    resting_hr_today: float | None = None,
    resting_hr_baseline: float | None = None,
    hrv_today: float | None = None,
    hrv_baseline: float | None = None,
    sleep_hours: float | None = None,
    recent_rpe: float | None = None,
) -> Readiness:
    score = 70.0
    factors: list[str] = []
    score += max(-25.0, min(15.0, tsb * 0.8))
    if tsb < -20:
        factors.append(f"Mệt tích lũy cao (form {tsb:.0f})")
    elif tsb > 5:
        factors.append("Cơ thể đã hồi phục tốt")
    if acwr_value is not None and acwr_value > 1.5:
        score -= 15
        factors.append(f"Tải tăng đột ngột (ACWR {acwr_value})")
    if resting_hr_today and resting_hr_baseline:
        diff = resting_hr_today - resting_hr_baseline
        if diff >= 5:
            score -= 15
            factors.append(f"Nhịp tim nghỉ cao hơn bình thường {diff:.0f} bpm")
        elif diff <= -2:
            score += 3
    if hrv_today and hrv_baseline:
        ratio = hrv_today / hrv_baseline
        if ratio < 0.85:
            score -= 12
            factors.append("HRV thấp hơn nền")
        elif ratio > 1.05:
            score += 4
    if sleep_hours is not None:
        if sleep_hours < 6:
            score -= 10
            factors.append(f"Ngủ ít ({sleep_hours:.1f} giờ)")
        elif sleep_hours >= 7.5:
            score += 3
    if recent_rpe is not None and recent_rpe >= 8:
        score -= 8
        factors.append("Các buổi gần đây cảm thấy rất nặng (RPE cao)")
    s = int(max(0, min(100, round(score))))
    label = "Sẵn sàng" if s >= 70 else "Bình thường" if s >= 50 else "Cần hồi phục"
    return Readiness(score=s, label=label, factors=factors)
