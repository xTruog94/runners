from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core
    app_token: str = "change-me"  # Bearer token used by the mobile app
    public_url: str = "http://localhost:8000"  # externally reachable base URL (OAuth callbacks, webhooks)
    data_dir: Path = Path("./data")
    timezone: str = "Asia/Ho_Chi_Minh"
    sync_interval_minutes: int = 30

    # --- location for weather / heat adjustment (default: Ho Chi Minh City)
    latitude: float = 10.7769
    longitude: float = 106.7009

    # --- Strava (create your own app at https://www.strava.com/settings/api)
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_webhook_verify_token: str = "runners-verify"
    strava_write_descriptions: bool = False  # append coach notes to Strava activity description

    # --- Garmin Connect (unofficial, personal use)
    garmin_email: str = ""
    garmin_password: str = ""
    garmin_push_workouts: bool = True

    # --- COROS (self-service "Build on COROS" MCP, single-user OAuth)
    coros_mcp_url: str = "https://mcp.coros.com/mcp"
    coros_push_workouts: bool = True
    coros_tool_list_activities: str = ""  # leave empty to auto-detect
    coros_tool_get_activity: str = ""
    coros_tool_create_workout: str = ""

    # --- optional AI coach (Claude)
    anthropic_api_key: str = ""
    coach_model: str = "claude-opus-5-5"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'runners.db'}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
