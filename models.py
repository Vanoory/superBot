from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import base64
import uuid
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class HorizontalLine:
    price: float
    color: str
    label: str | None = None
    style: str = "solid"


@dataclass
class PriceLabel:
    price: float
    bg_color: str
    text: str | None = None
    text_color: str = "#FFFFFF"


@dataclass
class ZoneSpec:
    top: float
    bottom: float
    x_start: float
    x_end: float
    kind: str
    fill_color: str | None = None
    border_color: str | None = None
    alpha: float = 0.28
    label: str | None = None


@dataclass
class BosLevel:
    price: float
    bar: int
    label: str = "BOS"


@dataclass
class PointOfInterest:
    top: float
    bottom: float
    x_start: float
    x_end: float
    label: str = "POI"


@dataclass
class ChartSpec:
    style: str
    symbol: str
    interval: str
    channel_id: str | None = None
    theme_name: str | None = None
    theme_overrides: dict[str, Any] = field(default_factory=dict)
    candles: list[dict[str, float]] = field(default_factory=list)
    zones: list[ZoneSpec] = field(default_factory=list)
    bos_levels: list[BosLevel] = field(default_factory=list)
    horizontal_lines: list[HorizontalLine] = field(default_factory=list)
    labels: list[PriceLabel] = field(default_factory=list)
    prediction_path: list[tuple[float, float]] = field(default_factory=list)
    poi_box: PointOfInterest | None = None
    background_hint: str | None = None
    header_exchange: str = "Bybit"
    watermark_smart: bool = True
    watermark_tv: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.poi_box is None:
            payload["poi_box"] = None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChartSpec":
        return cls(
            style=payload["style"],
            symbol=payload["symbol"],
            interval=payload["interval"],
            channel_id=payload.get("channel_id"),
            theme_name=payload.get("theme_name"),
            theme_overrides=dict(payload.get("theme_overrides", {})),
            candles=payload.get("candles", []),
            zones=[ZoneSpec(**item) for item in payload.get("zones", [])],
            bos_levels=[BosLevel(**item) for item in payload.get("bos_levels", [])],
            horizontal_lines=[HorizontalLine(**item) for item in payload.get("horizontal_lines", [])],
            labels=[PriceLabel(**item) for item in payload.get("labels", [])],
            prediction_path=[tuple(item) for item in payload.get("prediction_path", [])],
            poi_box=PointOfInterest(**payload["poi_box"]) if payload.get("poi_box") else None,
            background_hint=payload.get("background_hint"),
            header_exchange=payload.get("header_exchange", "Bybit"),
            watermark_smart=payload.get("watermark_smart", True),
            watermark_tv=payload.get("watermark_tv", True),
        )


@dataclass
class SignalSetup:
    mode: str
    side: str
    symbol: str
    interval: str
    entry_zone: tuple[float, float]
    targets: list[float]
    stop: float
    score: float
    confluence: list[str] = field(default_factory=list)
    stop_to_be_rule: str | None = None
    commentary_hint: str | None = None
    chart_spec: ChartSpec | None = None
    leverage: int = 10

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["chart_spec"] = self.chart_spec.to_dict() if self.chart_spec else None
        return data

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SignalSetup":
        return cls(
            mode=payload["mode"],
            side=payload["side"],
            symbol=payload["symbol"],
            interval=payload["interval"],
            entry_zone=tuple(payload["entry_zone"]),
            targets=list(payload["targets"]),
            stop=float(payload["stop"]),
            score=float(payload["score"]),
            confluence=list(payload.get("confluence", [])),
            stop_to_be_rule=payload.get("stop_to_be_rule"),
            commentary_hint=payload.get("commentary_hint"),
            chart_spec=ChartSpec.from_dict(payload["chart_spec"]) if payload.get("chart_spec") else None,
            leverage=int(payload.get("leverage", 10)),
        )


@dataclass
class PostDraft:
    kind: str
    channel_ids: list[str]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    image_bytes: bytes | None = None
    parse_mode: str | None = "HTML"
    created_at: str = field(default_factory=utc_now_iso)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "channel_ids": self.channel_ids,
            "text": self.text,
            "metadata": self.metadata,
            "parse_mode": self.parse_mode,
            "created_at": self.created_at,
            "image_b64": base64.b64encode(self.image_bytes).decode("ascii") if self.image_bytes else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PostDraft":
        image_b64 = payload.get("image_b64")
        return cls(
            id=payload["id"],
            kind=payload["kind"],
            channel_ids=list(payload["channel_ids"]),
            text=payload["text"],
            metadata=dict(payload.get("metadata", {})),
            image_bytes=base64.b64decode(image_b64) if image_b64 else None,
            parse_mode=payload.get("parse_mode"),
            created_at=payload.get("created_at", utc_now_iso()),
        )


@dataclass
class NewsEvent:
    time: str
    currency: str
    title: str
    forecast: str | None = None
    previous: str | None = None
    impact: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChannelRecord:
    channel_id: str
    channel_name: str
    added_at: str = field(default_factory=utc_now_iso)
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
