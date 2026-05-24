from __future__ import annotations

from dataclasses import dataclass
import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import AppConfig

from .approval_manager import ApprovalManager
from .handlers import BotHandlers


LOGGER = logging.getLogger(__name__)


@dataclass
class TradingBotApplication:
    config: AppConfig
    asset_manager: any
    channel_repository: any
    settings_repository: any
    pending_repository: any
    ledger_repository: any
    schedule_state_repository: any
    post_service: any
    scheduler: any
    handlers: BotHandlers | None = None

    def build(self) -> Application:
        application = Application.builder().token(self.config.telegram_bot_token).build()
        approval_manager = ApprovalManager(
            bot=application.bot,
            admin_chat_id=self.config.admin_chat_id,
            pending_repository=self.pending_repository,
            ledger_repository=self.ledger_repository,
        )
        handlers = BotHandlers(
            config=self.config,
            asset_manager=self.asset_manager,
            channel_repository=self.channel_repository,
            settings_repository=self.settings_repository,
            pending_repository=self.pending_repository,
            ledger_repository=self.ledger_repository,
            schedule_state_repository=self.schedule_state_repository,
            post_service=self.post_service,
            approval_manager=approval_manager,
            scheduler=self.scheduler,
        )
        self.handlers = handlers
        self.scheduler.configure(
            on_schedule_tick=handlers.run_schedule_tick,
            on_news=handlers.generate_news_for_active_channels,
            on_signal_scan=handlers.generate_signal_for_active_channels,
        )
        application.add_handler(CommandHandler("start", handlers.start))
        application.add_handler(CommandHandler("addchannel", handlers.add_channel))
        application.add_handler(CommandHandler("removechannel", handlers.remove_channel))
        application.add_handler(CommandHandler("profile", handlers.profile))
        application.add_handler(CommandHandler("settings", handlers.settings))
        application.add_handler(CommandHandler("morning", handlers.manual_morning))
        application.add_handler(CommandHandler("morningvariant", handlers.morning_variant))
        application.add_handler(CommandHandler("scan", handlers.manual_scan))
        application.add_handler(CommandHandler("status", handlers.status))
        application.add_handler(CommandHandler("style", handlers.toggle_style))
        application.add_handler(CommandHandler("mode", handlers.toggle_mode))
        application.add_handler(CommandHandler("chartstyle", handlers.chart_style))
        application.add_handler(CommandHandler("setstylenote", handlers.set_style_note))
        application.add_handler(CommandHandler("addstyleexample", handlers.add_style_example))
        application.add_handler(CommandHandler("addchartbg", handlers.add_chart_background))
        application.add_handler(CommandHandler("addchartref", handlers.add_chart_reference))
        application.add_handler(CommandHandler("timeframes", handlers.timeframes))
        application.add_handler(CommandHandler("posttimes", handlers.posttimes))
        application.add_handler(CommandHandler("zoom", handlers.zoom))
        application.add_handler(CommandHandler("ad", handlers.ad_command))
        application.add_handler(CallbackQueryHandler(handlers.handle_callback))
        application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handlers.handle_admin_input))
        application.add_error_handler(handlers.on_error)
        return application

    async def startup(self, application: Application) -> None:
        if self.handlers is None:
            raise RuntimeError("Application handlers were not built")
        await self.handlers.capture_bot_identity(application)
        self.scheduler.start()
        LOGGER.info("Scheduler started")
