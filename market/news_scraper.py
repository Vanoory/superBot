from __future__ import annotations

from datetime import date
import logging
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from models import NewsEvent


LOGGER = logging.getLogger(__name__)


class InvestingCalendarClient:
    def __init__(self) -> None:
        self.page_url = "https://www.investing.com/economic-calendar/"
        self.ajax_url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.page_url,
        }

    async def get_high_impact_news(self) -> list[NewsEvent]:
        html = await self._fetch_events_html()
        if not html:
            return []
        events = self.parse_events(html)
        filtered = [event for event in events if event.currency.upper() == "USD" and event.impact >= 3]
        return filtered if len(filtered) >= 3 else []

    async def _fetch_events_html(self) -> str:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            today = date.today().strftime("%Y-%m-%d")
            try:
                payload = {
                    "country[]": "5",
                    "importance[]": "3",
                    "timeZone": "55",
                    "timeFilter": "timeRemain",
                    "currentTab": "today",
                    "limit_from": "0",
                    "dateFrom": today,
                    "dateTo": today,
                }
                async with session.post(self.ajax_url, data=payload, headers=self.headers) as response:
                    if response.status == 200:
                        data: dict[str, Any] = await response.json(content_type=None)
                        html = str(data.get("data") or "")
                        if html.strip():
                            return html
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Investing AJAX fetch failed, falling back to HTML page: %s", exc)

            async with session.get(self.page_url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                response.raise_for_status()
                return await response.text()

    @staticmethod
    def parse_events(html: str) -> list[NewsEvent]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("tr.js-event-item, tr[data-event-datetime], div.js-event-item")
        events: list[NewsEvent] = []
        for row in rows:
            text = row.get_text(" ", strip=True)
            currency = (
                (row.get("data-event-currency") or "")
                or InvestingCalendarClient._extract_text(row, [".flagCur", ".left.flagCur.noWrap"])
            ).strip()
            if not currency and "USD" not in text:
                continue
            currency = currency or "USD"
            title = InvestingCalendarClient._extract_text(
                row,
                [".event", ".event-name", ".left.event", ".eventName"],
            )
            if not title:
                title = InvestingCalendarClient._fallback_title(text)
            if not title:
                continue
            time_value = (
                row.get("data-event-datetime")
                or InvestingCalendarClient._extract_text(row, [".time", ".first.left.time", ".time js-time"])
            )
            if "USD" not in currency.upper() and " USD " not in f" {text} ":
                continue
            impact = InvestingCalendarClient._extract_impact(row)
            forecast = InvestingCalendarClient._extract_text(row, [".forecast", ".fore", "td.fore"])
            previous = InvestingCalendarClient._extract_text(row, [".previous", ".prev", "td.prev"])
            events.append(
                NewsEvent(
                    time=InvestingCalendarClient._normalize_time(time_value),
                    currency=currency.upper(),
                    title=title,
                    forecast=forecast or None,
                    previous=previous or None,
                    impact=impact,
                )
            )
        return events

    @staticmethod
    def _extract_text(row, selectors: list[str]) -> str:
        for selector in selectors:
            node = row.select_one(selector)
            if node and node.get_text(strip=True):
                return node.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _extract_impact(row) -> int:
        bulls = row.select(".grayFullBullishIcon, .bullishIcon, i.grayFullBullishIcon")
        if bulls:
            return len(bulls)
        text = row.get_text(" ", strip=True)
        return 3 if "bull" in text.lower() or "high" in text.lower() else 0

    @staticmethod
    def _normalize_time(value: str) -> str:
        if not value:
            return "00:00"
        match = re.search(r"(\d{1,2}:\d{2})", value)
        return match.group(1) if match else value.strip()

    @staticmethod
    def _fallback_title(text: str) -> str:
        normalized = " ".join(text.split())
        for chunk in ("Forecast", "Previous", "Actual", "USD"):
            normalized = normalized.replace(chunk, " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized[:160]
