from __future__ import annotations

from dataclasses import dataclass
import statistics


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) < period + 1:
        return [50.0] * len(values)
    gains: list[float] = []
    losses: list[float] = []
    result = [50.0] * len(values)
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
        if index < period:
            continue
        avg_gain = sum(gains[index - period:index]) / period
        avg_loss = sum(losses[index - period:index]) / period
        if avg_loss == 0:
            result[index] = 100.0
            continue
        rs = avg_gain / avg_loss
        result[index] = 100 - 100 / (1 + rs)
    return result


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str


def find_swings(candles: list[dict[str, float]], left: int = 2, right: int = 2) -> list[SwingPoint]:
    points: list[SwingPoint] = []
    for index in range(left, len(candles) - right):
        high = candles[index]["high"]
        low = candles[index]["low"]
        if all(high >= candles[index - offset]["high"] for offset in range(1, left + 1)) and all(
            high >= candles[index + offset]["high"] for offset in range(1, right + 1)
        ):
            points.append(SwingPoint(index=index, price=high, kind="high"))
        if all(low <= candles[index - offset]["low"] for offset in range(1, left + 1)) and all(
            low <= candles[index + offset]["low"] for offset in range(1, right + 1)
        ):
            points.append(SwingPoint(index=index, price=low, kind="low"))
    return sorted(points, key=lambda point: point.index)


def recent_support_resistance(candles: list[dict[str, float]], window: int = 30) -> tuple[float, float]:
    slice_ = candles[-window:] if len(candles) >= window else candles
    highs = [candle["high"] for candle in slice_]
    lows = [candle["low"] for candle in slice_]
    return min(lows), max(highs)


def average_body(candles: list[dict[str, float]], window: int = 20) -> float:
    slice_ = candles[-window:] if len(candles) >= window else candles
    bodies = [abs(item["close"] - item["open"]) for item in slice_]
    return statistics.mean(bodies) if bodies else 0.0


def detect_equal_levels(swings: list[SwingPoint], tolerance: float = 0.0015) -> list[SwingPoint]:
    levels: list[SwingPoint] = []
    for previous, current in zip(swings, swings[1:]):
        if previous.kind != current.kind:
            continue
        baseline = previous.price or 1.0
        if abs(previous.price - current.price) / baseline <= tolerance:
            levels.append(current)
    return levels
