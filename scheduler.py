from __future__ import annotations

import logging
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import AppConfig
from utils import parse_hhmm


LOGGER = logging.getLogger(__name__)


AsyncJob = Callable[[], Awaitable[int]]


class TradingScheduler:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.scheduler = AsyncIOScheduler(timezone=config.timezone)
        self._configured = False

    def configure(self, *, on_schedule_tick: AsyncJob, on_news: AsyncJob, on_signal_scan: AsyncJob) -> None:
        if self._configured:
            return
        self.scheduler.add_job(on_schedule_tick, "interval", minutes=1, id="schedule_tick")
        self.scheduler.add_job(on_news, "interval", minutes=self.config.news_check_interval_min, id="news")
        self.scheduler.add_job(on_signal_scan, "interval", minutes=self.config.signal_scan_interval_min, id="signal_scan")
        self._configured = True

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def describe_jobs(self) -> list[str]:
        return [f"{job.id}: next={job.next_run_time}" for job in self.scheduler.get_jobs()]
