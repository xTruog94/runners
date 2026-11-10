from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import api, public
from .config import get_settings
from .db import init_db
from .services import sync

log = logging.getLogger("runners")


async def _sync_loop() -> None:
    interval = get_settings().sync_interval_minutes * 60
    await asyncio.sleep(10)
    while True:
        try:
            res = await sync.sync_all()
            log.info("sync: %s", res)
        except Exception:  # noqa: BLE001
            log.exception("sync loop failed")
        await asyncio.sleep(interval)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(_sync_loop()) if get_settings().sync_interval_minutes > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Runners — giáo án chạy bộ cá nhân", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api)
app.include_router(public)
