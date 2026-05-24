from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
STORAGE_DIR = ROOT_DIR / "storage"
GENERATED_DIR = STORAGE_DIR / "generated"
CHANNEL_ASSETS_DIR = STORAGE_DIR / "channel_assets"


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    admin_chat_id: int
    groq_api_key: str
    groq_model: str
    timezone: str
    morning_post_time: str
    news_check_interval_min: int
    signal_scan_interval_min: int
    filler_post_times: tuple[str, ...]
    min_signal_quality_score: float
    max_signals_per_day: int
    webapp_bind_host: str
    webapp_port: int
    webapp_base_url: str
    root_dir: Path = ROOT_DIR
    storage_dir: Path = STORAGE_DIR
    generated_dir: Path = GENERATED_DIR
    channel_assets_dir: Path = CHANNEL_ASSETS_DIR

    @property
    def background_candidates(self) -> list[Path]:
        candidates = list((self.root_dir / "charts" / "backgrounds").glob("*"))
        if candidates:
            return [p for p in candidates if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        return [
            p
            for p in self.root_dir.glob("photo_*")
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config() -> AppConfig:
    load_dotenv()

    filler_post_times = tuple(
        time.strip()
        for time in os.getenv("FILLER_POST_TIMES", "14:00,20:00").split(",")
        if time.strip()
    )

    return AppConfig(
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
        admin_chat_id=int(_require_env("ADMIN_CHAT_ID")),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        timezone=os.getenv("TIMEZONE", "Europe/Kiev").strip(),
        morning_post_time=os.getenv("MORNING_POST_TIME", "09:00").strip(),
        news_check_interval_min=int(os.getenv("NEWS_CHECK_INTERVAL_MIN", "60")),
        signal_scan_interval_min=int(os.getenv("SIGNAL_SCAN_INTERVAL_MIN", "30")),
        filler_post_times=filler_post_times or ("14:00", "20:00"),
        min_signal_quality_score=float(os.getenv("MIN_SIGNAL_QUALITY_SCORE", "0.65")),
        max_signals_per_day=int(os.getenv("MAX_SIGNALS_PER_DAY", "3")),
        webapp_bind_host=os.getenv("WEBAPP_BIND_HOST", "127.0.0.1").strip(),
        webapp_port=int(os.getenv("WEBAPP_PORT", "8080")),
        webapp_base_url=os.getenv("WEBAPP_BASE_URL", "").strip(),
    )
