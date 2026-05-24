from __future__ import annotations

from market.binance_api import BinanceClient
from market.signal_engine import SignalEngine


def _strategy_candles() -> list[dict[str, float]]:
    candles = []
    price = 100.0
    for index in range(90):
        step = 0.9 if index < 70 else (-0.35 if index < 80 else 1.25)
        open_ = price
        close = price + step
        high = max(open_, close) + 0.8
        low = min(open_, close) - 0.7
        candles.append({"time": index, "open": open_, "high": high, "low": low, "close": close, "volume": 1500})
        price = close
    return candles


def _smc_candles() -> list[dict[str, float]]:
    prices = [
        100, 101, 102, 101.5, 103, 102.8, 104, 103.5, 105, 104.3,
        106, 105.7, 108, 107.4, 109, 108.6, 110.5, 109.9, 112, 111.2,
        113, 112.1, 114.6, 113.7, 115.2, 114.9, 116.3, 116.1, 118.8, 118.4,
        118.9, 119.2, 119.4, 118.7, 120.1, 120.5, 121.2, 121.5, 121.9, 122.2,
        123.0, 122.8, 123.7, 123.4, 124.8, 124.2, 126.5, 125.7, 128.8, 129.4,
        130.0, 130.3, 130.7, 129.8, 131.5, 132.1, 133.8, 134.7, 135.2, 135.9,
        136.4, 137.1, 137.8, 138.2, 139.5, 140.4, 141.7, 143.2, 145.0, 146.8,
        146.5, 146.0, 145.8, 145.2, 144.9, 144.6, 147.6, 148.9, 149.8, 150.9,
    ]
    candles = []
    for index, close in enumerate(prices):
        open_ = prices[index - 1] if index else close - 1
        high = max(open_, close) + (0.9 if index % 5 else 1.4)
        low = min(open_, close) - (0.7 if index % 4 else 1.0)
        candles.append({"time": index, "open": open_, "high": high, "low": low, "close": close, "volume": 1900})
    return candles


def test_strategy_signal_heuristic_returns_setup():
    engine = SignalEngine(BinanceClient(), 0.65)
    setup = engine._find_strategy_signal("SOLUSDT", "4h", _strategy_candles())
    assert setup is not None
    assert setup.mode == "strategy"
    assert setup.side in {"long", "short"}
    assert setup.chart_spec is not None


def test_smc_signal_heuristic_returns_setup():
    engine = SignalEngine(BinanceClient(), 0.65)
    setup = engine._find_smc_signal("ETHUSDT", "4h", _smc_candles())
    assert setup is not None
    assert setup.mode == "smc"
    assert setup.side in {"long", "short"}
    assert setup.chart_spec is not None
    assert setup.score >= 0.65
