from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from models import ChannelRecord, PostDraft

from .json_store import JsonStore


DEFAULT_CHANNEL_SETTINGS = {
    "signal_mode": "smc",
    "morning_chart": "btc_chart",
    "morning_custom_symbol": "",
    "morning_post_variant": "brief",
    "morning_post_time": "09:00",
    "morning_chart_interval": "4h",
    "filler_post_times": ["14:00", "20:00"],
    "post_formatting": "with_bold",
    "language": "ru",
    "active": True,
    "intervals_to_scan": ["4h", "1d"],
    "symbols_whitelist": [],
    "max_signals_per_day": 3,
    "writing_style_notes": "",
    "style_reference_limit": 4,
    "chart_style_signal_preset": "dark_tv",
    "chart_style_smc_preset": "light_classic",
    "chart_style_morning_preset": "dark_tv",
    "chart_zoom_signal": "standard",
    "chart_zoom_smc": "standard",
    "chart_zoom_morning": "standard",
    "chart_style_overrides": {},
    "use_channel_backgrounds": True,
}


class StorageBootstrap:
    def __init__(self, root: Path):
        self.root = root

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "generated").mkdir(parents=True, exist_ok=True)
        (self.root / "channel_assets").mkdir(parents=True, exist_ok=True)
        JsonStore(self.root / "channels.json", list)
        JsonStore(self.root / "settings.json", dict)
        JsonStore(self.root / "pending_approvals.json", dict)
        JsonStore(self.root / "signal_ledger.json", dict)
        JsonStore(self.root / "schedule_state.json", dict)


class ChannelRepository:
    def __init__(self, root: Path):
        self.store = JsonStore(root / "channels.json", list)

    def list_channels(self, active_only: bool = False) -> list[ChannelRecord]:
        records = [ChannelRecord(**item) for item in self.store.read()]
        if active_only:
            return [record for record in records if record.active]
        return records

    def get(self, channel_id: str) -> ChannelRecord | None:
        for record in self.list_channels(active_only=False):
            if record.channel_id == channel_id:
                return record
        return None

    def add(self, record: ChannelRecord) -> None:
        def mutator(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            filtered = [item for item in items if item["channel_id"] != record.channel_id]
            filtered.append(record.to_dict())
            return filtered

        self.store.update(mutator)

    def remove(self, channel_id: str) -> bool:
        removed = False

        def mutator(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            nonlocal removed
            next_items = [item for item in items if item["channel_id"] != channel_id]
            removed = len(next_items) != len(items)
            return next_items

        self.store.update(mutator)
        return removed


class SettingsRepository:
    def __init__(self, root: Path):
        self.store = JsonStore(root / "settings.json", dict)

    def get(self, channel_id: str) -> dict[str, Any]:
        settings = self.store.read().get(channel_id, {})
        merged = dict(DEFAULT_CHANNEL_SETTINGS)
        merged.update(settings)
        return merged

    def update(self, channel_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        def mutator(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
            merged = dict(DEFAULT_CHANNEL_SETTINGS)
            merged.update(payload.get(channel_id, {}))
            merged.update(patch)
            payload[channel_id] = merged
            return payload

        payload = self.store.update(mutator)
        return dict(payload[channel_id])

    def remove(self, channel_id: str) -> None:
        def mutator(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
            payload.pop(channel_id, None)
            return payload

        self.store.update(mutator)


class PendingApprovalRepository:
    def __init__(self, root: Path):
        self.store = JsonStore(root / "pending_approvals.json", dict)

    def save(self, draft: PostDraft) -> None:
        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            payload[draft.id] = draft.to_dict()
            return payload

        self.store.update(mutator)

    def get(self, draft_id: str) -> PostDraft | None:
        payload = self.store.read().get(draft_id)
        if not payload:
            return None
        return PostDraft.from_dict(payload)

    def delete(self, draft_id: str) -> PostDraft | None:
        deleted = None

        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            nonlocal deleted
            deleted = payload.pop(draft_id, None)
            return payload

        self.store.update(mutator)
        return PostDraft.from_dict(deleted) if deleted else None

    def list(self) -> list[PostDraft]:
        return [PostDraft.from_dict(item) for item in self.store.read().values()]


class SignalLedgerRepository:
    def __init__(self, root: Path):
        self.store = JsonStore(root / "signal_ledger.json", dict)

    def _today_key(self, for_date: date | None = None) -> str:
        return (for_date or date.today()).isoformat()

    def _default_day(self) -> dict[str, dict[str, int]]:
        return defaultdict(lambda: {"reserved": 0, "published": 0})  # type: ignore[return-value]

    def get_counts(self, channel_id: str, for_date: date | None = None) -> dict[str, int]:
        payload = self.store.read()
        day_data = payload.get(self._today_key(for_date), {})
        counts = day_data.get(channel_id, {"reserved": 0, "published": 0})
        return {"reserved": int(counts.get("reserved", 0)), "published": int(counts.get("published", 0))}

    def can_queue(self, channel_id: str, limit: int, for_date: date | None = None) -> bool:
        counts = self.get_counts(channel_id, for_date)
        return counts["reserved"] + counts["published"] < limit

    def reserve(self, channel_id: str, for_date: date | None = None) -> None:
        day_key = self._today_key(for_date)

        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            payload.setdefault(day_key, {})
            payload[day_key].setdefault(channel_id, {"reserved": 0, "published": 0})
            payload[day_key][channel_id]["reserved"] += 1
            return payload

        self.store.update(mutator)

    def release(self, channel_id: str, for_date: date | None = None) -> None:
        day_key = self._today_key(for_date)

        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            payload.setdefault(day_key, {})
            payload[day_key].setdefault(channel_id, {"reserved": 0, "published": 0})
            payload[day_key][channel_id]["reserved"] = max(0, payload[day_key][channel_id]["reserved"] - 1)
            return payload

        self.store.update(mutator)


class ScheduleStateRepository:
    def __init__(self, root: Path):
        self.store = JsonStore(root / "schedule_state.json", dict)

    def is_slot_consumed(self, channel_id: str, slot_key: str, today_key: str) -> bool:
        payload = self.store.read()
        return payload.get(channel_id, {}).get(slot_key) == today_key

    def mark_slot(self, channel_id: str, slot_key: str, today_key: str) -> None:
        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            payload.setdefault(channel_id, {})
            payload[channel_id][slot_key] = today_key
            return payload

        self.store.update(mutator)

    def release(self, channel_id: str, for_date: date | None = None) -> None:
        day_key = self._today_key(for_date)

        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            payload.setdefault(day_key, {})
            payload[day_key].setdefault(channel_id, {"reserved": 0, "published": 0})
            payload[day_key][channel_id]["reserved"] = max(0, payload[day_key][channel_id]["reserved"] - 1)
            return payload

        self.store.update(mutator)

    def mark_published(self, channel_id: str, for_date: date | None = None) -> None:
        day_key = self._today_key(for_date)

        def mutator(payload: dict[str, Any]) -> dict[str, Any]:
            payload.setdefault(day_key, {})
            payload[day_key].setdefault(channel_id, {"reserved": 0, "published": 0})
            payload[day_key][channel_id]["published"] += 1
            payload[day_key][channel_id]["reserved"] = max(0, payload[day_key][channel_id]["reserved"] - 1)
            return payload

        self.store.update(mutator)
