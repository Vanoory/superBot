from __future__ import annotations

import hashlib
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image

from config import AppConfig
from models import ChartSpec, HorizontalLine, ZoneSpec
from utils import format_price

from .styles import infer_style_mode, resolve_theme


class ChartGenerator:
    def __init__(self, config: AppConfig, asset_manager=None) -> None:
        self.config = config
        self.asset_manager = asset_manager

    def render(self, spec: ChartSpec) -> bytes:
        theme = resolve_theme(spec.style, spec.theme_name, spec.theme_overrides)
        candles = spec.candles
        if not candles:
            raise ValueError("ChartSpec.candles cannot be empty")

        fig, ax = plt.subplots(figsize=theme["figure_size"], dpi=120)
        fig.patch.set_facecolor(theme["facecolor"])
        ax.set_facecolor(theme["axes_facecolor"])

        price_min = min(item["low"] for item in candles)
        price_max = max(item["high"] for item in candles)
        padding = max((price_max - price_min) * 0.1, price_max * 0.003)

        if spec.style == "B":
            self._draw_background(ax, spec, len(candles), price_min - padding, price_max + padding, theme)
            ax.grid(False)
        else:
            ax.grid(True, color=theme["grid_color"], linewidth=0.7, alpha=0.6, linestyle="-")

        for zone in spec.zones:
            self._draw_zone(ax, zone, theme)

        self._draw_candles(ax, candles, theme, spec.style)

        for bos in spec.bos_levels:
            ax.hlines(
                bos.price,
                xmin=bos.bar,
                xmax=len(candles) + 10,
                colors=theme.get("bos_color", theme["line_color"]),
                linestyles="dashed",
                linewidth=1.2,
                zorder=4,
            )
            ax.text(
                bos.bar + 0.6,
                bos.price,
                bos.label,
                fontsize=9,
                color=theme.get("bos_color", theme["line_color"]),
                va="bottom",
            )

        for line in spec.horizontal_lines:
            self._draw_horizontal_line(ax, line, len(candles))

        if spec.poi_box:
            rect = Rectangle(
                (spec.poi_box.x_start, spec.poi_box.bottom),
                spec.poi_box.x_end - spec.poi_box.x_start,
                spec.poi_box.top - spec.poi_box.bottom,
                facecolor="#9097A8" if spec.style == "A" else "#7B7B7B",
                alpha=0.15 if spec.style == "A" else 0.18,
                edgecolor="none",
                zorder=1,
            )
            ax.add_patch(rect)
            ax.text(
                spec.poi_box.x_end + 0.3,
                (spec.poi_box.top + spec.poi_box.bottom) / 2,
                spec.poi_box.label,
                fontsize=9,
                color=theme.get("line_color", "#3E4350"),
            )

        if spec.prediction_path:
            self._draw_prediction(ax, candles, spec.prediction_path, theme, spec.style)

        last_close = candles[-1]["close"]
        self._draw_price_label(
            ax,
            x=len(candles) + 1,
            y=last_close,
            text=f"{format_price(last_close)}",
            bg=theme["price_label_bg"],
            fg=theme["price_label_fg"],
        )

        for label in spec.labels:
            self._draw_price_label(
                ax,
                x=len(candles) + 1,
                y=label.price,
                text=label.text or format_price(label.price),
                bg=label.bg_color,
                fg=label.text_color,
            )

        self._draw_header_and_watermarks(ax, spec, theme)

        ax.set_xlim(-1, len(candles) + 12)
        ax.set_ylim(price_min - padding, price_max + padding)
        ax.yaxis.tick_right()
        ax.spines["top"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.spines["right"].set_visible(False if spec.style == "A" else True)
        ax.tick_params(axis="y", colors=theme["axis_color"], labelsize=10, length=0)
        ax.tick_params(axis="x", colors=theme["axis_color"], labelsize=9, length=0)
        ax.set_xticklabels([])
        plt.tight_layout(pad=0.5)

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        buffer.seek(0)
        return buffer.read()

    def _draw_background(self, ax, spec: ChartSpec, candle_count: int, low: float, high: float, theme: dict) -> None:
        background = self._pick_background(spec)
        if background:
            image = Image.open(background).convert("RGB")
            image = image.resize((1800, 1100))
            array = np.array(image)
            ax.imshow(array, extent=[-2, candle_count + 12, low, high], aspect="auto", alpha=0.35, zorder=0)
        overlay = Rectangle(
            (-2, low),
            candle_count + 16,
            high - low,
            facecolor="#000000",
            alpha=theme.get("background_overlay_alpha", 0.42),
            zorder=0,
        )
        ax.add_patch(overlay)

    def _background_candidates(self, spec: ChartSpec) -> list[Path]:
        candidates: list[Path] = []
        if spec.channel_id and self.asset_manager:
            candidates = self.asset_manager.list_backgrounds(spec.channel_id)
        return candidates if candidates else self.config.background_candidates

    def _pick_background(self, spec: ChartSpec) -> Path | None:
        candidates = self._background_candidates(spec)
        if not candidates:
            return None
        key = f"{spec.channel_id or 'global'}:{spec.symbol}:{spec.interval}:{spec.theme_name or spec.style}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % len(candidates)
        return sorted(candidates)[index]

    def _draw_candles(self, ax, candles: list[dict[str, float]], theme: dict, style_name: str) -> None:
        width = 0.68 if style_name == "A" else 0.55
        for index, candle in enumerate(candles):
            open_ = candle["open"]
            close = candle["close"]
            high = candle["high"]
            low = candle["low"]
            bull = close >= open_
            face = theme["bull_face"] if bull else theme["bear_face"]
            edge = theme["bull_edge"] if bull else theme["bear_edge"]
            body_bottom = min(open_, close)
            body_height = max(abs(close - open_), 0.0001)
            ax.vlines(index, low, high, colors=theme["wick_color"], linewidth=0.7, zorder=3)
            rect = Rectangle(
                (index - width / 2, body_bottom),
                width,
                body_height,
                facecolor=face,
                edgecolor=edge,
                linewidth=0.9,
                zorder=4,
            )
            ax.add_patch(rect)

    def _draw_zone(self, ax, zone: ZoneSpec, theme: dict) -> None:
        fill = zone.fill_color or (theme["zone_demand"] if zone.kind == "demand" else theme["zone_supply"])
        rect = Rectangle(
            (zone.x_start, zone.bottom),
            zone.x_end - zone.x_start,
            zone.top - zone.bottom,
            facecolor=fill,
            edgecolor=zone.border_color or "none",
            alpha=zone.alpha or theme["zone_alpha"],
            linewidth=1.0 if zone.border_color else 0.0,
            zorder=1,
        )
        ax.add_patch(rect)

    def _draw_horizontal_line(self, ax, line: HorizontalLine, candle_count: int) -> None:
        linestyle = "--" if line.style == "dashed" else "-"
        ax.hlines(line.price, xmin=0, xmax=candle_count + 10, colors=line.color, linestyles=linestyle, linewidth=1.0, zorder=2)
        if line.label:
            text = line.label if not line.label.startswith("T") else format_price(line.price)
            self._draw_price_label(ax, candle_count + 1, line.price, text, line.color, "#FFFFFF")

    def _draw_prediction(self, ax, candles: list[dict[str, float]], offsets: list[tuple[float, float]], theme: dict, style_name: str) -> None:
        color = theme["dotted_color"] if style_name == "A" else theme["prediction_color"]
        x_points = [len(candles) - 1]
        y_points = [candles[-1]["close"]]
        current_x = x_points[0]
        current_y = y_points[0]
        for dx, dy in offsets:
            current_x += dx
            current_y += dy
            x_points.append(current_x)
            y_points.append(current_y)
        ax.plot(
            x_points,
            y_points,
            color=color,
            linewidth=1.4,
            linestyle=":" if style_name == "A" else "-",
            zorder=5,
        )
        ax.annotate(
            "",
            xy=(x_points[-1], y_points[-1]),
            xytext=(x_points[-2], y_points[-2]),
            arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
        )

    def _draw_price_label(self, ax, x: float, y: float, text: str, bg: str, fg: str) -> None:
        ax.text(
            x,
            y,
            f" {text} ",
            fontsize=10,
            color=fg,
            va="center",
            ha="left",
            bbox={"boxstyle": "round,pad=0.18", "facecolor": bg, "edgecolor": "none"},
            zorder=6,
        )

    def _draw_header_and_watermarks(self, ax, spec: ChartSpec, theme: dict) -> None:
        if spec.style == "B":
            last = spec.candles[-1]
            header = (
                f"{spec.symbol} Perpetual Contract · {spec.interval} · {spec.header_exchange}   "
                f"ОТКР{format_price(last['open'])} МАКС{format_price(last['high'])} "
                f"МИН{format_price(last['low'])} ЗАКР{format_price(last['close'])}"
            )
            ax.set_title(header, color=theme.get("header_color", "#EFEFEF"), fontsize=12, loc="left", pad=10)
            if spec.watermark_tv:
                ax.text(0.01, 0.03, "TradingView", transform=ax.transAxes, fontsize=22, color="#FFFFFF", alpha=0.9, fontweight="bold")
            if spec.watermark_smart:
                ax.text(0.985, 0.03, "SMART", transform=ax.transAxes, fontsize=24, color="#FFFFFF", alpha=0.95, ha="right", fontweight="bold")
        else:
            ax.set_title(
                f"{spec.symbol} / TetherUS · {spec.interval} · Binance",
                color=theme.get("header_color", "#2B2F39"),
                fontsize=12,
                loc="left",
                pad=10,
            )
