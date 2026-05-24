from __future__ import annotations

from pathlib import Path
import json
import shutil
import uuid

from models import utc_now_iso


class AssetManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _channel_dir(self, channel_id: str) -> Path:
        safe = channel_id.replace("@", "").replace("/", "_").replace("\\", "_")
        return self.root / safe

    def ensure_channel_dirs(self, channel_id: str) -> None:
        channel_dir = self._channel_dir(channel_id)
        (channel_dir / "text_samples").mkdir(parents=True, exist_ok=True)
        (channel_dir / "chart_refs").mkdir(parents=True, exist_ok=True)
        (channel_dir / "backgrounds").mkdir(parents=True, exist_ok=True)

    def remove_channel_assets(self, channel_id: str) -> None:
        channel_dir = self._channel_dir(channel_id)
        if channel_dir.exists():
            shutil.rmtree(channel_dir)

    def classify_text_sample(self, text: str) -> str:
        compact = " ".join(text.lower().split())
        if any(token in compact for token in ["зона набора", "стоп", "цели", "лонг", "шорт", "entry"]):
            return "signal"
        if any(token in compact for token in ["доброе утро", "утро", "сегодня смотрю", "на сегодня"]):
            return "morning_analysis" if len(compact) > 420 else "morning_brief"
        if any(token in compact for token in ["fomc", "cpi", "новости", "usd", "безработиц"]):
            return "news"
        if any(token in compact for token in ["биржа", "бонус", "регистрация", "рефка", "ссылка"]):
            return "ad"
        if len(compact) > 500:
            return "analysis"
        if len(compact) < 180:
            return "short"
        return "general"

    def save_text_sample(self, channel_id: str, text: str, sample_kind: str = "auto") -> Path:
        self.ensure_channel_dirs(channel_id)
        kind = self.classify_text_sample(text) if sample_kind == "auto" else sample_kind
        filename = f"{uuid.uuid4().hex}.json"
        path = self._channel_dir(channel_id) / "text_samples" / filename
        path.write_text(
            json.dumps(
                {
                    "kind": kind,
                    "text": text.strip(),
                    "created_at": utc_now_iso(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def list_text_samples(self, channel_id: str, limit: int | None = None, kinds: set[str] | None = None) -> list[str]:
        self.ensure_channel_dirs(channel_id)
        json_files = sorted(
            (self._channel_dir(channel_id) / "text_samples").glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        legacy_txt = sorted(
            (self._channel_dir(channel_id) / "text_samples").glob("*.txt"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        samples: list[str] = []

        for file in json_files:
            payload = json.loads(file.read_text(encoding="utf-8"))
            text = str(payload.get("text", "")).strip()
            kind = str(payload.get("kind", "general"))
            if not text:
                continue
            if kinds and kind not in kinds and "general" not in kinds:
                continue
            samples.append(text)
            if limit is not None and len(samples) >= limit:
                return samples

        for file in legacy_txt:
            text = file.read_text(encoding="utf-8").strip()
            if not text:
                continue
            samples.append(text)
            if limit is not None and len(samples) >= limit:
                return samples
        return samples

    def save_image(self, channel_id: str, image_bytes: bytes, *, bucket: str, suffix: str = ".jpg") -> Path:
        self.ensure_channel_dirs(channel_id)
        filename = f"{uuid.uuid4().hex}{suffix}"
        path = self._channel_dir(channel_id) / bucket / filename
        path.write_bytes(image_bytes)
        return path

    def list_backgrounds(self, channel_id: str) -> list[Path]:
        self.ensure_channel_dirs(channel_id)
        return sorted((self._channel_dir(channel_id) / "backgrounds").glob("*"))

    def list_chart_refs(self, channel_id: str) -> list[Path]:
        self.ensure_channel_dirs(channel_id)
        return sorted((self._channel_dir(channel_id) / "chart_refs").glob("*"))

    def profile_summary(self, channel_id: str) -> dict[str, int]:
        self.ensure_channel_dirs(channel_id)
        return {
            "text_samples": len(list((self._channel_dir(channel_id) / "text_samples").glob("*.json")))
            + len(list((self._channel_dir(channel_id) / "text_samples").glob("*.txt"))),
            "chart_refs": len(self.list_chart_refs(channel_id)),
            "backgrounds": len(self.list_backgrounds(channel_id)),
        }
