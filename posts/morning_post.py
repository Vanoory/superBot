from __future__ import annotations

from charts.styles import infer_style_mode
from models import ChartSpec, HorizontalLine, PostDraft
from utils import format_price

from .formatting import render_simple_text


class MorningPostGenerator:
    def __init__(self, style_service, binance_client, chart_generator) -> None:
        self.style_service = style_service
        self.binance_client = binance_client
        self.chart_generator = chart_generator

    async def generate(
        self,
        channel_id: str,
        settings: dict,
        *,
        context: str,
        prompt: str,
        variant: str,
        style_context: dict,
    ) -> PostDraft:
        symbol = settings.get("morning_custom_symbol") or "BTCUSDT"
        if settings.get("morning_chart") == "btc_chart":
            symbol = "BTCUSDT"

        interval = settings.get("morning_chart_interval", "4h")
        candles = await self.binance_client.get_klines(symbol, interval, 140)
        ticker = await self.binance_client.get_ticker_24h(symbol)
        watchlist = (
            f"ключевая реакция около {format_price(min(candle['low'] for candle in candles[-18:]))}$ "
            f"и сопротивление {format_price(max(candle['high'] for candle in candles[-18:]))}$"
        )
        if variant == "analysis":
            fallback = (
                "Доброе утро!\n\n"
                f"по {symbol.replace('USDT', '')} сейчас цена около {format_price(candles[-1]['close'])}$, "
                "ночью рынок особой скорости не показал.\n"
                f"За 24ч изменение {float(ticker.get('priceChangePercent', 0) or 0):+.2f}%, так что пока без лишней эйфории.\n"
                f"Из важных зон сегодня смотрю {watchlist}.\n"
                "Если реакция у уровня будет внятная, уже после этого можно будет собирать сетап, а не лезть заранее.\n"
                "Пока сценарий простой: жду либо нормальный импульс, либо спокойный откат в интересную зону."
            )
        else:
            fallback = (
                "Доброе утро!\n\n"
                f"по {symbol.replace('USDT', '')} сейчас цена около {format_price(candles[-1]['close'])}$, "
                "ночью рынок особо не разогнали.\n"
                f"Сегодня смотрю {watchlist}.\n"
                "Если дадут спокойный откат, уже после него можно будет собирать нормальные сетапы."
            )

        text = await self.style_service.generate(
            prompt,
            fallback,
            style_notes=style_context.get("notes"),
            reference_examples=style_context.get("examples"),
            temperature=0.6,
            max_tokens=420 if variant == "analysis" else 280,
        )
        formatted = render_simple_text(None, text, settings.get("post_formatting") == "with_bold")

        image_bytes = None
        chart_spec = None
        if settings.get("morning_chart") != "none":
            support = min(candle["low"] for candle in candles[-20:])
            resistance = max(candle["high"] for candle in candles[-20:])
            preset = settings.get("chart_style_morning_preset", "dark_tv")
            chart_spec = ChartSpec(
                style=infer_style_mode(preset, "B"),
                symbol=symbol,
                interval=interval,
                channel_id=channel_id,
                theme_name=preset,
                theme_overrides=settings.get("chart_style_overrides", {}),
                candles=candles,
                horizontal_lines=[
                    HorizontalLine(price=support, color="#FF5A6B"),
                    HorizontalLine(price=resistance, color="#7BE27B"),
                ],
            )
            zoom_map = {"tight": 50, "standard": 80, "wide": 120}
            zoom = settings.get("chart_zoom_morning", "standard")
            window = zoom_map.get(zoom, 80)
            chart_spec.candles = chart_spec.candles[-window:] if len(chart_spec.candles) > window else chart_spec.candles
            image_bytes = self.chart_generator.render(chart_spec)

        return PostDraft(
            kind="morning",
            channel_ids=[channel_id],
            text=formatted,
            image_bytes=image_bytes,
            metadata={
                "kind": "morning",
                "channel_id": channel_id,
                "context": context,
                "prompt": prompt,
                "variant": variant,
                "style_context": style_context,
                "chart_spec": chart_spec.to_dict() if chart_spec else None,
            },
        )
