from __future__ import annotations

import io
import logging

from telegram import Bot

from models import PostDraft

from .keyboards import approval_keyboard


LOGGER = logging.getLogger(__name__)


class ApprovalManager:
    def __init__(self, *, bot: Bot, admin_chat_id: int, pending_repository, ledger_repository) -> None:
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.pending_repository = pending_repository
        self.ledger_repository = ledger_repository
        self.awaiting_edits: dict[int, str] = {}

    async def send_for_approval(self, draft: PostDraft) -> None:
        self.pending_repository.save(draft)
        keyboard = approval_keyboard(draft.id)
        if draft.image_bytes:
            await self.bot.send_photo(
                chat_id=self.admin_chat_id,
                photo=io.BytesIO(draft.image_bytes),
                caption=draft.text[:1024],
                parse_mode=draft.parse_mode,
                reply_markup=keyboard,
            )
            if len(draft.text) > 1000:
                await self.bot.send_message(self.admin_chat_id, draft.text[1024:], parse_mode=draft.parse_mode)
        else:
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=draft.text,
                parse_mode=draft.parse_mode,
                reply_markup=keyboard,
            )

    async def publish(self, draft: PostDraft) -> None:
        for channel_id in draft.channel_ids:
            if draft.image_bytes:
                await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=io.BytesIO(draft.image_bytes),
                    caption=draft.text[:1024],
                    parse_mode=draft.parse_mode,
                )
                if len(draft.text) > 1000:
                    await self.bot.send_message(channel_id, draft.text[1024:], parse_mode=draft.parse_mode)
            else:
                await self.bot.send_message(channel_id, draft.text, parse_mode=draft.parse_mode)

            if draft.kind == "signal":
                self.ledger_repository.mark_published(channel_id)

    def set_edit_mode(self, user_id: int, draft_id: str) -> None:
        self.awaiting_edits[user_id] = draft_id

    def pop_edit_mode(self, user_id: int) -> str | None:
        return self.awaiting_edits.pop(user_id, None)

    def delete_pending(self, draft_id: str, *, release_signal_slot: bool) -> PostDraft | None:
        draft = self.pending_repository.delete(draft_id)
        if draft and draft.kind == "signal" and release_signal_slot:
            for channel_id in draft.channel_ids:
                self.ledger_repository.release(channel_id)
        return draft
