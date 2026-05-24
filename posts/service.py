from __future__ import annotations

from ai.prompts import build_ad_prompt, build_filler_prompt, build_morning_prompt, build_news_prompt, build_signal_prompt
from charts.styles import infer_style_mode
from market.analysis import build_market_snapshot, summarize_market_context
from models import ChartSpec, NewsEvent, PostDraft, SignalSetup

from .ad_post import AdPostGenerator
from .filler_post import FillerPostGenerator
from .morning_post import MorningPostGenerator
from .news_post import NewsPostGenerator
from .signal_post import SignalPostGenerator


class PostService:
    def __init__(
        self,
        *,
        binance_client,
        news_client,
        signal_engine,
        settings_repository,
        chart_generator,
        style_service,
        asset_manager,
    ) -> None:
        self.binance_client = binance_client
        self.news_client = news_client
        self.signal_engine = signal_engine
        self.settings_repository = settings_repository
        self.chart_generator = chart_generator
        self.style_service = style_service
        self.asset_manager = asset_manager
        self.morning_generator = MorningPostGenerator(style_service, binance_client, chart_generator)
        self.signal_generator = SignalPostGenerator(style_service, chart_generator)
        self.news_generator = NewsPostGenerator(style_service)
        self.filler_generator = FillerPostGenerator(style_service)
        self.ad_generator = AdPostGenerator(style_service)

    def _style_context(self, channel_id: str, settings: dict) -> dict:
        limit = int(settings.get("style_reference_limit", 4) or 4)
        return {
            "notes": settings.get("writing_style_notes", "").strip(),
            "examples": self.asset_manager.list_text_samples(channel_id, limit=limit, kinds={"general", "analysis", "short", "signal", "morning_brief", "morning_analysis", "news", "ad"}),
        }

    def _style_context_for_kind(self, channel_id: str, settings: dict, kind: str) -> dict:
        limit = int(settings.get("style_reference_limit", 4) or 4)
        kinds_map = {
            "morning_brief": {"morning_brief", "short", "general"},
            "morning_analysis": {"morning_analysis", "analysis", "general"},
            "signal": {"signal", "analysis", "general"},
            "news": {"news", "general"},
            "filler": {"short", "general"},
            "ad": {"ad", "general"},
        }
        return {
            "notes": settings.get("writing_style_notes", "").strip(),
            "examples": self.asset_manager.list_text_samples(channel_id, limit=limit, kinds=kinds_map.get(kind, {"general"})),
        }

    def _apply_zoom(self, candles: list[dict], zoom_value: str) -> list[dict]:
        window_map = {"tight": 50, "standard": 80, "wide": 120}
        window = window_map.get(zoom_value, 80)
        return candles[-window:] if len(candles) > window else candles

    def _apply_chart_profile(self, channel_id: str, settings: dict, setup: SignalSetup) -> SignalSetup:
        if not setup.chart_spec:
            return setup
        preset_key = "chart_style_smc_preset" if setup.mode == "smc" else "chart_style_signal_preset"
        zoom_key = "chart_zoom_smc" if setup.mode == "smc" else "chart_zoom_signal"
        preset = settings.get(preset_key, "light_classic" if setup.mode == "smc" else "dark_tv")
        setup.chart_spec.channel_id = channel_id
        setup.chart_spec.theme_name = preset
        setup.chart_spec.theme_overrides = dict(settings.get("chart_style_overrides", {}))
        setup.chart_spec.style = infer_style_mode(preset, setup.chart_spec.style)
        setup.chart_spec.candles = self._apply_zoom(setup.chart_spec.candles, settings.get(zoom_key, "standard"))
        return setup

    async def generate_morning_post(self, channel_id: str, variant: str | None = None) -> PostDraft:
        settings = self.settings_repository.get(channel_id)
        variant = variant or settings.get("morning_post_variant", "brief")
        symbol = settings.get("morning_custom_symbol") or "BTCUSDT"
        if settings.get("morning_chart") == "btc_chart":
            symbol = "BTCUSDT"
        candles = await self.binance_client.get_klines(symbol, "1d", 40)
        ticker = await self.binance_client.get_ticker_24h(symbol)
        context = summarize_market_context(candles, ticker)
        watchlist = "смотрю за реакцией у ключевых уровней и за тем, будет ли импульс после американской сессии"
        prompt = build_morning_prompt(context, symbol, build_market_snapshot(symbol, ticker), watchlist, variant)
        return await self.morning_generator.generate(
            channel_id,
            settings,
            context=context,
            prompt=prompt,
            variant=variant,
            style_context=self._style_context_for_kind(channel_id, settings, "morning_analysis" if variant == "analysis" else "morning_brief"),
        )

    async def generate_signal_post(self, channel_id: str, setup: SignalSetup | None = None) -> PostDraft | None:
        settings = self.settings_repository.get(channel_id)
        if setup is None:
            setup = await self.signal_engine.scan_channel(settings)
        if setup is None:
            return None
        setup = self._apply_chart_profile(channel_id, settings, setup)
        confluence = ", ".join(setup.confluence) if setup.confluence else "сетап по структуре"
        prompt = build_signal_prompt(
            setup.symbol,
            setup.side,
            setup.interval,
            f"{setup.entry_zone[0]}-{setup.entry_zone[1]}$",
            ", ".join(f"{target}$" for target in setup.targets),
            f"{setup.stop}$",
            confluence,
            setup.commentary_hint,
        )
        return await self.signal_generator.generate(
            channel_id,
            settings,
            setup,
            prompt=prompt,
            style_context=self._style_context_for_kind(channel_id, settings, "signal"),
        )

    async def generate_news_post(self, channel_id: str, events: list[NewsEvent] | None = None) -> PostDraft | None:
        settings = self.settings_repository.get(channel_id)
        events = events or await self.news_client.get_high_impact_news()
        if not events:
            return None
        summary = "; ".join(f"{event.time} {event.title}" for event in events)
        prompt = build_news_prompt(summary)
        return await self.news_generator.generate(
            channel_id,
            settings,
            events,
            prompt=prompt,
            style_context=self._style_context_for_kind(channel_id, settings, "news"),
        )

    async def generate_filler_post(self, channel_id: str) -> PostDraft:
        settings = self.settings_repository.get(channel_id)
        ticker = await self.binance_client.get_ticker_24h("BTCUSDT")
        snapshot = build_market_snapshot("BTCUSDT", ticker)
        prompt = build_filler_prompt(snapshot)
        return await self.filler_generator.generate(
            channel_id,
            settings,
            snapshot=snapshot,
            prompt=prompt,
            style_context=self._style_context_for_kind(channel_id, settings, "filler"),
        )

    async def generate_ad_post(self, channel_id: str, payload: dict, image_bytes: bytes | None = None) -> PostDraft:
        settings = self.settings_repository.get(channel_id)
        prompt = build_ad_prompt(payload["exchange_name"], payload["promo_text"], payload.get("bonus"), payload["link"])
        return await self.ad_generator.generate(
            channel_id,
            settings,
            payload,
            prompt=prompt,
            style_context=self._style_context_for_kind(channel_id, settings, "ad"),
            image_bytes=image_bytes,
        )

    async def regenerate_post(self, draft: PostDraft) -> PostDraft | None:
        kind = draft.metadata.get("kind", draft.kind)
        channel_id = draft.metadata.get("channel_id", draft.channel_ids[0])
        settings = self.settings_repository.get(channel_id)
        style_context = draft.metadata.get("style_context") or self._style_context(channel_id, settings)

        if kind == "signal":
            setup = SignalSetup.from_dict(draft.metadata["setup"])
            setup = self._apply_chart_profile(channel_id, settings, setup)
            prompt = draft.metadata["prompt"]
            return await self.signal_generator.generate(channel_id, settings, setup, prompt=prompt, style_context=style_context)

        if kind == "morning":
            return await self.morning_generator.generate(
                channel_id,
                settings,
                context=draft.metadata.get("context", ""),
                prompt=draft.metadata.get("prompt", ""),
                variant=draft.metadata.get("variant", settings.get("morning_post_variant", "brief")),
                style_context=style_context,
            )

        if kind == "news":
            events = [NewsEvent(**item) for item in draft.metadata.get("events", [])]
            return await self.news_generator.generate(channel_id, settings, events, prompt=draft.metadata.get("prompt", ""), style_context=style_context)

        if kind == "filler":
            return await self.filler_generator.generate(
                channel_id,
                settings,
                snapshot=draft.metadata.get("snapshot", ""),
                prompt=draft.metadata.get("prompt", ""),
                style_context=style_context,
            )

        if kind == "ad":
            return await self.ad_generator.generate(
                channel_id,
                settings,
                draft.metadata["payload"],
                prompt=draft.metadata.get("prompt", ""),
                style_context=style_context,
                image_bytes=draft.image_bytes,
            )
        return None
