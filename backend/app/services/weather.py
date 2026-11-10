"""Weather from Open-Meteo (free, no API key) for heat/humidity pace adjustment."""

from __future__ import annotations

import datetime as dt
import time

import httpx

from ..config import get_settings
from ..db import get_setting, set_setting
from ..engine.heat import heat_advice_vi, heat_factor, heat_slowdown_pct

URL = "https://api.open-meteo.com/v1/forecast"
CACHE_S = 3600


def forecast() -> dict | None:
    cfg = get_settings()
    lat = get_setting("latitude", cfg.latitude)
    lon = get_setting("longitude", cfg.longitude)
    cached = get_setting("weather_cache")
    if cached and time.time() - cached.get("ts", 0) < CACHE_S and cached.get("loc") == [lat, lon]:
        return cached["data"]
    try:
        r = httpx.get(
            URL,
            params={"latitude": lat, "longitude": lon, "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature", "timezone": cfg.timezone, "forecast_days": 2},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return cached["data"] if cached else None
    set_setting("weather_cache", {"ts": time.time(), "loc": [lat, lon], "data": data})
    return data


def heat_for(day: dt.date, hour: int | None = None) -> dict | None:
    data = forecast()
    if not data or "hourly" not in data:
        return None
    hour = hour if hour is not None else int(get_setting("preferred_run_hour", 5))
    target = f"{day.isoformat()}T{hour:02d}:00"
    h = data["hourly"]
    try:
        i = h["time"].index(target)
    except ValueError:
        return None
    t, rh = h["temperature_2m"][i], h["relative_humidity_2m"][i]
    # best hour of the day for running (lowest slowdown between 4h and 20h)
    best = None
    for j, ts in enumerate(h["time"]):
        if ts.startswith(day.isoformat()) and 4 <= int(ts[11:13]) <= 20:
            pct = heat_slowdown_pct(h["temperature_2m"][j], h["relative_humidity_2m"][j])
            if best is None or pct < best[1]:
                best = (int(ts[11:13]), pct)
    return {
        "hour": hour,
        "temp_c": t,
        "humidity": rh,
        "slowdown_pct": heat_slowdown_pct(t, rh),
        "factor": heat_factor(t, rh),
        "advice": heat_advice_vi(t, rh),
        "best_hour": best[0] if best else None,
        "best_hour_slowdown_pct": best[1] if best else None,
    }
