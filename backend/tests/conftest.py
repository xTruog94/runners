import os

import pytest

os.environ.setdefault("APP_TOKEN", "test-token")
os.environ.setdefault("SYNC_INTERVAL_MINUTES", "0")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import config

    config.get_settings.cache_clear()
    from app import db

    db.reset_engine(f"sqlite:///{tmp_path / 't.db'}")
    from app.services import weather

    monkeypatch.setattr(weather, "forecast", lambda: None)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.headers.update({"Authorization": "Bearer test-token"})
        yield c
