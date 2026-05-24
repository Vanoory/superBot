from __future__ import annotations

from bot.approval_manager import ApprovalManager
from models import PostDraft
from storage import PendingApprovalRepository, SignalLedgerRepository


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages = []
        self.sent_photos = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent_messages.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
        self.sent_photos.append({"chat_id": chat_id, "caption": caption, "parse_mode": parse_mode, "reply_markup": reply_markup})


def test_signal_ledger_reserve_release_publish(app_config):
    ledger = SignalLedgerRepository(app_config.storage_dir)
    assert ledger.can_queue("-1001", 3)
    ledger.reserve("-1001")
    counts = ledger.get_counts("-1001")
    assert counts == {"reserved": 1, "published": 0}
    ledger.mark_published("-1001")
    counts = ledger.get_counts("-1001")
    assert counts == {"reserved": 0, "published": 1}
    ledger.release("-1001")
    counts = ledger.get_counts("-1001")
    assert counts == {"reserved": 0, "published": 1}


async def test_approval_manager_persists_and_publishes(app_config):
    bot = FakeBot()
    pending = PendingApprovalRepository(app_config.storage_dir)
    ledger = SignalLedgerRepository(app_config.storage_dir)
    manager = ApprovalManager(
        bot=bot,
        admin_chat_id=1,
        pending_repository=pending,
        ledger_repository=ledger,
    )

    draft = PostDraft(kind="signal", channel_ids=["-1005"], text="hello world")
    ledger.reserve("-1005")
    await manager.send_for_approval(draft)
    assert pending.get(draft.id) is not None
    assert len(bot.sent_messages) == 1

    await manager.publish(draft)
    counts = ledger.get_counts("-1005")
    assert counts == {"reserved": 0, "published": 1}

    pending.save(draft)
    deleted = manager.delete_pending(draft.id, release_signal_slot=True)
    assert deleted is not None
