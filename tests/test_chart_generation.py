from __future__ import annotations

import hashlib

from charts import ChartGenerator
from models import BosLevel, ChartSpec, HorizontalLine, PointOfInterest, ZoneSpec


def _candles() -> list[dict[str, float]]:
    candles = []
    price = 100.0
    for index in range(60):
        open_ = price
        close = price + (1.8 if index % 3 else -1.2)
        high = max(open_, close) + 2.0
        low = min(open_, close) - 1.5
        candles.append({"time": index, "open": open_, "high": high, "low": low, "close": close, "volume": 1000 + index})
        price = close
    return candles


def test_chart_generation_is_deterministic_per_style(app_config):
    generator = ChartGenerator(app_config)
    candles = _candles()
    style_a = ChartSpec(
        style="A",
        symbol="BTCUSDT",
        interval="4h",
        candles=candles,
        zones=[ZoneSpec(top=112, bottom=108, x_start=10, x_end=40, kind="supply")],
        bos_levels=[BosLevel(price=109.5, bar=24)],
        horizontal_lines=[HorizontalLine(price=95, color="#555555")],
        prediction_path=[(4, -4), (6, 8), (5, -10)],
        poi_box=PointOfInterest(top=111, bottom=107, x_start=32, x_end=45),
    )
    style_b = ChartSpec(
        style="B",
        symbol="ETHUSDT",
        interval="1h",
        candles=candles,
        zones=[ZoneSpec(top=103, bottom=98, x_start=38, x_end=68, kind="demand")],
        horizontal_lines=[HorizontalLine(price=120, color="#5FD35F"), HorizontalLine(price=92, color="#F45B69")],
        prediction_path=[(3, 7), (4, -4), (7, 12)],
    )

    a_first = generator.render(style_a)
    a_second = generator.render(style_a)
    b_first = generator.render(style_b)
    b_second = generator.render(style_b)

    assert a_first.startswith(b"\x89PNG")
    assert b_first.startswith(b"\x89PNG")
    assert hashlib.sha256(a_first).hexdigest() == hashlib.sha256(a_second).hexdigest()
    assert hashlib.sha256(b_first).hexdigest() == hashlib.sha256(b_second).hexdigest()
    assert hashlib.sha256(a_first).hexdigest() != hashlib.sha256(b_first).hexdigest()
