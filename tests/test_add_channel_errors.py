from __future__ import annotations

from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from bot.handlers import BotHandlers
from storage import AssetManager, ChannelRepository, PendingApprovalRepository, ScheduleStateRepository, SettingsRepository, SignalLedgerRepository


class DummyMessage:
    def __init__(self) -> None:
        self.replies: list[dict] = []

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": text, "kwargs": kwargs})


class DummyBot:
    async def get_chat(self, chat_id):
        raise BadRequest("Chat not found")

    async def get_me(self):
        return SimpleNamespace(id=999)


@pytest.mark.asyncio
async def test_add_channel_handles_chat_not_found_gracefully(app_config):
    message = DummyMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=app_config.admin_chat_id),
        effective_message=message,
    )
    context = SimpleNamespace(args=["-1003733603815"], bot=DummyBot())
    handlers = BotHandlers(
        config=app_config,
        asset_manager=AssetManager(app_config.channel_assets_dir),
        channel_repository=ChannelRepository(app_config.storage_dir),
        settings_repository=SettingsRepository(app_config.storage_dir),
        pending_repository=PendingApprovalRepository(app_config.storage_dir),
        ledger_repository=SignalLedgerRepository(app_config.storage_dir),
        schedule_state_repository=ScheduleStateRepository(app_config.storage_dir),
        post_service=None,
        approval_manager=None,
        scheduler=None,
    )

    await handlers.add_channel(update, context)

    assert message.replies
    assert "Не удалось найти канал" in message.replies[0]["text"]
