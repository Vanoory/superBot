from __future__ import annotations

from pathlib import Path

import pytest

from config import AppConfig
from storage import StorageBootstrap


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    storage_dir = tmp_path / "storage"
    generated_dir = storage_dir / "generated"
    channel_assets_dir = storage_dir / "channel_assets"
    StorageBootstrap(storage_dir).ensure()
    return AppConfig(
        telegram_bot_token="token",
        admin_chat_id=1,
        groq_api_key="",
        groq_model="openai/gpt-oss-20b",
        timezone="Europe/Kiev",
        morning_post_time="09:00",
        news_check_interval_min=60,
        signal_scan_interval_min=30,
        filler_post_times=("14:00", "20:00"),
        min_signal_quality_score=0.65,
        max_signals_per_day=3,
        webapp_bind_host="127.0.0.1",
        webapp_port=8080,
        webapp_base_url="",
        root_dir=tmp_path,
        storage_dir=storage_dir,
        generated_dir=generated_dir,
        channel_assets_dir=channel_assets_dir,
    )
