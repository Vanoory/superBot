from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from models import BosLevel, ChartSpec, HorizontalLine, PointOfInterest, SignalSetup, ZoneSpec
from utils import clamp

from .binance_api import BinanceClient
from .indicators import average_body, detect_equal_levels, ema, find_swings, recent_support_resistance, rsi


LOGGER = logging.getLogger(__name__)


@dataclass
class ScanCandidate:
    signal: SignalSetup
    interval: str


class SignalEngine:
    def __init__(self, binance_client: BinanceClient, min_quality_score: float) -> None:
        self.binance_client = binance_client
        self.min_quality_score = min_quality_score

    async def scan_channel(self, settings: dict[str, Any]) -> SignalSetup | None:
        symbols = settings.get("symbols_whitelist") or await self.binance_client.get_all_usdt_pairs()
        symbols = [symbol for symbol in symbols if symbol.endswith("USDT")][:40]
        intervals = settings.get("intervals_to_scan") or ["4h", "1d"]
        mode = settings.get("signal_mode", "smc")
        best: SignalSetup | None = None

        for symbol in symbols:
            try:
                for interval in intervals:
                    candles = await self.binance_client.get_klines(symbol, interval, 140)
                    candidate = self._find_signal(mode=mode, symbol=symbol, interval=interval, candles=candles)
                    if candidate and (best is None or candidate.score > best.score):
                        best = candidate
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Failed scanning %s: %s", symbol, exc)
                continue

        if best and best.score >= self.min_quality_score:
            return best
        return None

    def _find_signal(self, mode: str, symbol: str, interval: str, candles: list[dict[str, float]]) -> SignalSetup | None:
        if len(candles) < 60:
            return None
        if mode == "strategy":
            return self._find_strategy_signal(symbol, interval, candles)
        return self._find_smc_signal(symbol, interval, candles)

    def _find_strategy_signal(self, symbol: str, interval: str, candles: list[dict[str, float]]) -> SignalSetup | None:
        closes = [item["close"] for item in candles]
        ema_fast = ema(closes, 9)
        ema_slow = ema(closes, 21)
        rsi_values = rsi(closes, 14)
        support, resistance = recent_support_resistance(candles, window=36)
        last = candles[-1]
        prev = candles[-2]
        trend_up = ema_fast[-1] > ema_slow[-1] and closes[-1] > ema_fast[-1]
        trend_down = ema_fast[-1] < ema_slow[-1] and closes[-1] < ema_fast[-1]
        pullback_pct = abs(closes[-1] - ema_fast[-1]) / closes[-1]
        breakout_up = closes[-1] > prev["high"]
        breakout_down = closes[-1] < prev["low"]
        score = 0.35
        confluence: list[str] = []

        side = None
        entry_zone = None
        targets = None
        stop = None
        commentary = None
        if trend_up and rsi_values[-1] > 52 and (
            (pullback_pct < 0.02 and last["low"] <= ema_fast[-1] * 1.01) or breakout_up
        ):
            side = "long"
            entry_zone = (min(last["low"], ema_fast[-1] * 0.998), max(last["close"], ema_fast[-1] * 1.002))
            targets = [resistance, resistance * 1.01]
            stop = min(support, prev["low"]) * 0.997
            score += 0.2
            confluence.extend(["EMA 9/21 bullish", "pullback in trend"])
            if breakout_up:
                score += 0.07
                confluence.append("momentum breakout")
            if rsi_values[-1] > rsi_values[-4]:
                score += 0.1
                confluence.append("RSI strength")
            commentary = "биток и альта держатся бодро, хочется брать после локального отката"
        elif trend_down and rsi_values[-1] < 48 and (
            (pullback_pct < 0.02 and last["high"] >= ema_fast[-1] * 0.99) or breakout_down
        ):
            side = "short"
            entry_zone = (min(last["close"], ema_fast[-1] * 0.998), max(last["high"], ema_fast[-1] * 1.002))
            targets = [support, support * 0.99]
            stop = max(resistance, prev["high"]) * 1.003
            score += 0.2
            confluence.extend(["EMA 9/21 bearish", "pullback to resistance"])
            if breakout_down:
                score += 0.07
                confluence.append("momentum breakout")
            if rsi_values[-1] < rsi_values[-4]:
                score += 0.1
                confluence.append("RSI weakness")
            commentary = "рынок слабый, поэтому интереснее искать шорт повыше"

        if not side or not entry_zone or not targets or stop is None:
            return None

        chart_spec = self._build_strategy_chart_spec(symbol, interval, candles, side, entry_zone, targets, stop)
        return SignalSetup(
            mode="strategy",
            side=side,
            symbol=symbol,
            interval=interval,
            entry_zone=(float(entry_zone[0]), float(entry_zone[1])),
            targets=[float(targets[0]), float(targets[1])],
            stop=float(stop),
            score=clamp(score, 0.0, 0.99),
            confluence=confluence,
            stop_to_be_rule="переносим в бу после первой цели",
            commentary_hint=commentary,
            chart_spec=chart_spec,
            leverage=10 if interval == "4h" else 5,
        )

    def _find_smc_signal(self, symbol: str, interval: str, candles: list[dict[str, float]]) -> SignalSetup | None:
        swings = find_swings(candles, left=2, right=2)
        if len(swings) < 4:
            return None
        highs = [point for point in swings if point.kind == "high"]
        lows = [point for point in swings if point.kind == "low"]
        if len(highs) < 2 or len(lows) < 2:
            return None

        last = candles[-1]
        avg_body = average_body(candles, 24) or 1.0
        latest_high = highs[-1]
        latest_low = lows[-1]
        prior_high = highs[-2]
        prior_low = lows[-2]
        equal_levels = detect_equal_levels(swings)

        bullish_bos = last["close"] > prior_high.price
        bearish_bos = last["close"] < prior_low.price
        if not bullish_bos and not bearish_bos:
            return None

        side = "long" if bullish_bos else "short"
        fvg = self._find_recent_fvg(candles, bullish=side == "long")
        if not fvg:
            return None

        if side == "long":
            entry_zone = (fvg["bottom"], fvg["top"])
            target = max(latest_high.price, last["close"] + avg_body * 6)
            stop = min(prior_low.price, entry_zone[0] - avg_body * 1.5)
            commentary = "смотрю именно смарт-мани сценарий, если дадут возврат в имбаланс - можно подбирать"
        else:
            entry_zone = (fvg["bottom"], fvg["top"])
            target = min(latest_low.price, last["close"] - avg_body * 6)
            stop = max(prior_high.price, entry_zone[1] + avg_body * 1.5)
            commentary = "пока структура слабая, интереснее дождаться возврата в зону и уже оттуда смотреть шорт"

        score = 0.52
        confluence = ["FVG", "structure break"]
        if equal_levels:
            score += 0.08
            confluence.append("liquidity pool")
        if abs(entry_zone[1] - entry_zone[0]) > avg_body:
            score += 0.06
            confluence.append("wide POI")
        score += 0.08

        chart_spec = self._build_smc_chart_spec(
            symbol=symbol,
            interval=interval,
            candles=candles,
            side=side,
            entry_zone=entry_zone,
            target=target,
            stop=stop,
            bos_bar=prior_high.index if side == "long" else prior_low.index,
            bos_price=prior_high.price if side == "long" else prior_low.price,
        )
        return SignalSetup(
            mode="smc",
            side=side,
            symbol=symbol,
            interval=interval,
            entry_zone=(float(entry_zone[0]), float(entry_zone[1])),
            targets=[float(target)],
            stop=float(stop),
            score=clamp(score, 0.0, 0.99),
            confluence=confluence,
            stop_to_be_rule="после реакции и первого импульса смотрим перевод в бу",
            commentary_hint=commentary,
            chart_spec=chart_spec,
            leverage=10 if interval == "4h" else 5,
        )

    def _find_recent_fvg(self, candles: list[dict[str, float]], *, bullish: bool) -> dict[str, float] | None:
        for index in range(len(candles) - 3, 1, -1):
            previous_candle = candles[index - 1]
            next_candle = candles[index + 1]
            if bullish and previous_candle["high"] < next_candle["low"]:
                return {"top": next_candle["low"], "bottom": previous_candle["high"], "index": index}
            if not bullish and previous_candle["low"] > next_candle["high"]:
                return {"top": previous_candle["low"], "bottom": next_candle["high"], "index": index}
        return None

    def _build_strategy_chart_spec(
        self,
        symbol: str,
        interval: str,
        candles: list[dict[str, float]],
        side: str,
        entry_zone: tuple[float, float],
        targets: list[float],
        stop: float,
    ) -> ChartSpec:
        zone_kind = "demand" if side == "long" else "supply"
        zone = ZoneSpec(
            top=max(entry_zone),
            bottom=min(entry_zone),
            x_start=len(candles) - 14,
            x_end=len(candles) + 18,
            kind=zone_kind,
            label="Entry",
        )
        target_lines = [
            HorizontalLine(price=target, color="#5FD35F", label=f"T{index + 1}")
            for index, target in enumerate(targets)
        ]
        stop_line = HorizontalLine(price=stop, color="#F45B69", label="SL")
        last_close = candles[-1]["close"]
        projection = (
            [(3, (targets[0] - last_close) * 0.35), (5, -(targets[0] - stop) * 0.18), (8, (targets[-1] - last_close) * 0.78)]
            if side == "long"
            else [(3, (targets[0] - last_close) * 0.3), (5, abs(stop - last_close) * 0.18), (8, (targets[-1] - last_close) * 0.9)]
        )
        return ChartSpec(
            style="B",
            symbol=symbol,
            interval=interval,
            candles=candles[-80:],
            zones=[zone],
            horizontal_lines=target_lines + [stop_line],
            prediction_path=projection,
        )

    def _build_smc_chart_spec(
        self,
        *,
        symbol: str,
        interval: str,
        candles: list[dict[str, float]],
        side: str,
        entry_zone: tuple[float, float],
        target: float,
        stop: float,
        bos_bar: int,
        bos_price: float,
    ) -> ChartSpec:
        recent = candles[-80:]
        shift = max(0, len(candles) - len(recent))
        poi_top = max(entry_zone)
        poi_bottom = min(entry_zone)
        poi = PointOfInterest(
            top=poi_top,
            bottom=poi_bottom,
            x_start=max(0, len(recent) - 22),
            x_end=len(recent) + 4,
        )
        zone = ZoneSpec(
            top=poi_top,
            bottom=poi_bottom,
            x_start=max(0, len(recent) - 22),
            x_end=len(recent) + 3,
            kind="demand" if side == "long" else "supply",
            label="POI",
        )
        secondary_zone = ZoneSpec(
            top=max(target, poi_top) if side == "long" else max(stop, poi_top),
            bottom=min(stop, poi_bottom) if side == "long" else min(target, poi_bottom),
            x_start=max(0, len(recent) - 45),
            x_end=max(6, len(recent) - 12),
            kind="supply" if side == "long" else "demand",
            alpha=0.36,
        )
        prediction = (
            [(4, (poi_bottom - recent[-1]["close"]) * 0.8), (7, (target - recent[-1]["close"]) * 0.45), (11, (stop - recent[-1]["close"]) * 0.95)]
            if side == "short"
            else [(4, (poi_top - recent[-1]["close"]) * 0.6), (7, (target - recent[-1]["close"]) * 0.55), (11, (target - recent[-1]["close"]) * 0.95)]
        )
        return ChartSpec(
            style="A",
            symbol=symbol,
            interval=interval,
            candles=recent,
            zones=[secondary_zone, zone],
            bos_levels=[BosLevel(price=bos_price, bar=max(0, bos_bar - shift))],
            horizontal_lines=[
                HorizontalLine(price=target, color="#4B4F59", style="solid"),
                HorizontalLine(price=stop, color="#C65966", style="solid"),
            ],
            prediction_path=prediction,
            poi_box=poi,
        )
