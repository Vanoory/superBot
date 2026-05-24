from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp


LOGGER = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self) -> None:
        self.base_url = "https://api.binance.com/api/v3"

    async def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        timeout = aiohttp.ClientTimeout(total=20)
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params) as response:
                        if response.status in {429, 500, 502, 503, 504}:
                            body = await response.text()
                            raise RuntimeError(f"Binance temporary error {response.status}: {body[:120]}")
                        response.raise_for_status()
                        return await response.json()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Binance request failed on attempt %s: %s", attempt + 1, exc)
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)

    async def get_klines(self, symbol: str, interval: str, limit: int = 120) -> list[dict[str, float]]:
        data = await self._request_json(
            "/klines",
            {"symbol": symbol.upper(), "interval": interval, "limit": limit},
        )
        return [
            {
                "time": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
            for item in data
        ]

    async def get_ticker_24h(self, symbol: str) -> dict[str, Any]:
        return await self._request_json("/ticker/24hr", {"symbol": symbol.upper()})

    async def get_all_usdt_pairs(self) -> list[str]:
        payload = await self._request_json("/exchangeInfo")
        return [
            item["symbol"]
            for item in payload["symbols"]
            if item.get("quoteAsset") == "USDT"
            and item.get("status") == "TRADING"
            and item.get("isSpotTradingAllowed", True)
        ]
