from __future__ import annotations

from datetime import datetime
import html
import random
from typing import Iterable


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_str, minute_str = value.split(":", 1)
    return int(hour_str), int(minute_str)


def html_escape(text: str) -> str:
    return html.escape(text, quote=False)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_price(value: float) -> float:
    if value >= 1000:
        return round(value, 1)
    if value >= 100:
        return round(value, 2)
    if value >= 1:
        return round(value, 3)
    return round(value, 4)


def format_price(value: float) -> str:
    rounded = round_price(value)
    text = f"{rounded:,.4f}" if rounded < 1 else f"{rounded:,.2f}"
    while "." in text and text.endswith("0"):
        text = text[:-1]
    return text[:-1] if text.endswith(".") else text


def choose_weighted(items: Iterable[tuple[str, float]]) -> str:
    population, weights = zip(*items)
    return random.choices(population, weights=weights, k=1)[0]


def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
