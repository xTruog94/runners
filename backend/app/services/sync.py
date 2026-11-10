"""Sync orchestration across all providers."""

from __future__ import annotations

import asyncio
import logging

from ..integrations import coros, garmin, strava
from . import activities

log = logging.getLogger("runners.sync")


async def sync_all(push: bool = True) -> dict:
    out: dict = {}
    for name, fn in (("strava", strava.sync), ("garmin", garmin.sync)):
        try:
            out[name] = await asyncio.to_thread(fn)
        except Exception as e:  # noqa: BLE001
            out[name] = f"error: {e}"
    try:
        out["coros"] = await coros.sync()
    except Exception as e:  # noqa: BLE001
        out["coros"] = f"error: {e}"
    try:
        out["adjustments"] = await asyncio.to_thread(activities.daily_maintenance)
    except Exception as e:  # noqa: BLE001
        log.exception("maintenance failed")
        out["adjustments"] = f"error: {e}"
    if push:
        out["push"] = await push_all()
    return out


async def push_all() -> dict:
    out: dict = {}
    try:
        out["garmin"] = await asyncio.to_thread(garmin.push_upcoming)
    except Exception as e:  # noqa: BLE001
        out["garmin"] = f"error: {e}"
    try:
        out["coros"] = await coros.push_upcoming()
    except Exception as e:  # noqa: BLE001
        out["coros"] = f"error: {e}"
    return out
