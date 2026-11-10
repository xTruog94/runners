"""Heat & humidity pace adjustment (temperature + dew point rule of thumb).

Uses the widely used "temp °F + dew point °F" table. Useful for hot, humid
climates such as Vietnam.
"""

from __future__ import annotations

import math


def dew_point_c(temp_c: float, rel_humidity: float) -> float:
    a, b = 17.27, 237.7
    rh = max(1.0, min(100.0, rel_humidity))
    gamma = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
    return (b * gamma) / (a - gamma)


def _c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


_TABLE = [  # (upper bound of temp+dew °F, slowdown %)
    (100, 0.0),
    (110, 0.5),
    (120, 1.0),
    (130, 2.0),
    (140, 3.0),
    (150, 4.5),
    (160, 6.0),
    (170, 8.0),
    (180, 10.0),
]


def heat_slowdown_pct(temp_c: float, rel_humidity: float) -> float:
    total = _c_to_f(temp_c) + _c_to_f(dew_point_c(temp_c, rel_humidity))
    for bound, pct in _TABLE:
        if total <= bound:
            return pct
    return 12.0  # >180: hard running not recommended


def heat_factor(temp_c: float | None, rel_humidity: float | None) -> float:
    if temp_c is None or rel_humidity is None:
        return 1.0
    return 1.0 + heat_slowdown_pct(temp_c, rel_humidity) / 100.0


def heat_advice_vi(temp_c: float, rel_humidity: float) -> str:
    pct = heat_slowdown_pct(temp_c, rel_humidity)
    if pct == 0:
        return "Thời tiết tốt, chạy theo pace bình thường."
    if pct <= 2:
        return f"Hơi nóng ẩm: chậm lại khoảng {pct:g}%. Mang nước nếu chạy trên 60 phút."
    if pct <= 6:
        return f"Nóng ẩm: chậm lại khoảng {pct:g}%, ưu tiên chạy theo cảm giác/nhịp tim, chạy sáng sớm."
    if pct < 12:
        return f"Rất nóng ẩm: chậm lại {pct:g}%. Nên đổi bài nặng thành chạy nhẹ hoặc chạy trong nhà."
    return "Nguy hiểm: không nên chạy bài nặng. Chạy nhẹ trong nhà hoặc nghỉ."
