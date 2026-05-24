from __future__ import annotations

from utils import format_price


def summarize_market_context(candles: list[dict[str, float]], ticker: dict | None = None) -> str:
    if not candles:
        return "рынок без данных, лучше без лишней агрессии"
    last = candles[-1]
    first = candles[0]
    delta_pct = ((last["close"] - first["open"]) / first["open"]) * 100 if first["open"] else 0
    day_change = None
    if ticker:
        try:
            day_change = float(ticker.get("priceChangePercent", 0.0))
        except (TypeError, ValueError):
            day_change = None
    direction = "в ап-тренде" if delta_pct > 1 else "давят вниз" if delta_pct < -1 else "топчется в боковике"
    extra = f", за 24ч {day_change:+.2f}%" if day_change is not None else ""
    return f"биток сейчас {direction}, цена около {format_price(last['close'])}$, локальная амплитуда сжалась{extra}"


def build_market_snapshot(symbol: str, ticker: dict[str, str]) -> str:
    price = format_price(float(ticker.get("lastPrice", 0) or 0))
    change = float(ticker.get("priceChangePercent", 0) or 0)
    volume = format_price(float(ticker.get("quoteVolume", 0) or 0))
    return f"{symbol}: цена {price}$, изменение за 24ч {change:+.2f}%, объём {volume}"
