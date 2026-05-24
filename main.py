from __future__ import annotations

import asyncio

from ai import GroqChatClient, StyleTextService
from bot import TradingBotApplication
from charts import ChartGenerator
from config import load_config
from logging_setup import configure_logging
from market import BinanceClient, InvestingCalendarClient, SignalEngine
from posts import PostService
from scheduler import TradingScheduler
from storage import AssetManager, ChannelRepository, PendingApprovalRepository, ScheduleStateRepository, SettingsRepository, SignalLedgerRepository, StorageBootstrap
from webapp_server import WebAppServer


async def main() -> None:
    config = load_config()
    configure_logging(config.root_dir)
    StorageBootstrap(config.storage_dir).ensure()
    asset_manager = AssetManager(config.channel_assets_dir)

    channel_repository = ChannelRepository(config.storage_dir)
    settings_repository = SettingsRepository(config.storage_dir)
    pending_repository = PendingApprovalRepository(config.storage_dir)
    ledger_repository = SignalLedgerRepository(config.storage_dir)
    schedule_state_repository = ScheduleStateRepository(config.storage_dir)

    binance_client = BinanceClient()
    news_client = InvestingCalendarClient()
    llm_client = GroqChatClient(config.groq_api_key, config.groq_model) if config.groq_api_key else None
    style_service = StyleTextService(llm_client)
    chart_generator = ChartGenerator(config, asset_manager=asset_manager)
    webapp_server = WebAppServer(
        config=config,
        settings_repository=settings_repository,
        asset_manager=asset_manager,
        chart_generator=chart_generator,
    )
    signal_engine = SignalEngine(binance_client, config.min_signal_quality_score)
    post_service = PostService(
        binance_client=binance_client,
        news_client=news_client,
        signal_engine=signal_engine,
        settings_repository=settings_repository,
        chart_generator=chart_generator,
        style_service=style_service,
        asset_manager=asset_manager,
    )
    scheduler = TradingScheduler(config)
    app_factory = TradingBotApplication(
        config=config,
        asset_manager=asset_manager,
        channel_repository=channel_repository,
        settings_repository=settings_repository,
        pending_repository=pending_repository,
        ledger_repository=ledger_repository,
        schedule_state_repository=schedule_state_repository,
        post_service=post_service,
        scheduler=scheduler,
    )
    application = app_factory.build()
    await application.initialize()
    await app_factory.startup(application)
    await webapp_server.start()
    await application.start()
    await application.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()
        await webapp_server.stop()
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
