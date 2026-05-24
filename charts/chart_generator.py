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
            ax.grid(True, color=theme["grid_color"], linewidth=0.4, alpha=0.4, linestyle="-")
            ax.set_axisbelow(True)
        else:
            ax.grid(True, color=theme["grid_color"], linewidth=0.5, alpha=0.45, linestyle="-")
            ax.set_axisbelow(True)

        for zone in spec.zones:
            self._draw_zone(ax, zone, theme)

        self._draw_candles(ax, candles, theme, spec.style)

        for bos in spec.bos_levels:
            bos_color = theme.get("bos_color", theme["line_color"])
            ax.hlines(
                bos.price,
                xmin=bos.bar,
                xmax=len(candles) + 8,
                colors=bos_color,
                linestyles=(0, (4, 3)),
                linewidth=1.0,
                zorder=4,
                alpha=0.85,
            )
            ax.text(
                bos.bar + 0.4,
                bos.price,
                f" {bos.label} ",
                fontsize=8,
                color=bos_color,
                va="bottom",
                ha="left",
                fontweight="600",
                alpha=0.95,
            )

        for line in spec.horizontal_lines:
            self._draw_horizontal_line(ax, line, len(candles))

        if spec.poi_box:
            poi_face = theme.get("poi_fill", "#9097A8" if spec.style == "A" else "#7B7B7B")
            poi_edge = theme.get("poi_border", theme.get("line_color", "#3E4350"))
            rect = Rectangle(
                (spec.poi_box.x_start, spec.poi_box.bottom),
                spec.poi_box.x_end - spec.poi_box.x_start,
                spec.poi_box.top - spec.poi_box.bottom,
                facecolor=poi_face,
                alpha=0.12 if spec.style == "A" else 0.16,
                edgecolor=poi_edge,
                linewidth=0.6,
                linestyle=(0, (3, 3)),
                zorder=1,
            )
            ax.add_patch(rect)
            ax.text(
                spec.poi_box.x_end - 0.4,
                spec.poi_box.top + (spec.poi_box.top - spec.poi_box.bottom) * 0.08,
                spec.poi_box.label,
                fontsize=8,
                color=poi_edge,
                ha="right",
                va="bottom",
                fontweight="600",
                alpha=0.9,
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
        width = 0.7 if style_name == "A" else 0.62
        wick_lw = 0.9 if style_name == "A" else 0.8
        for index, candle in enumerate(candles):
            open_ = candle["open"]
            close = candle["close"]
            high = candle["high"]
            low = candle["low"]
            bull = close >= open_
            face = theme["bull_face"] if bull else theme["bear_face"]
            edge = theme["bull_edge"] if bull else theme["bear_edge"]
            body_bottom = min(open_, close)
            body_height = max(abs(close - open_), (high - low) * 0.01, 0.0001)
            ax.vlines(index, low, high, colors=theme["wick_color"], linewidth=wick_lw, zorder=3)
            rect = Rectangle(
                (index - width / 2, body_bottom),
                width,
                body_height,
                facecolor=face,
                edgecolor=edge,
                linewidth=0.8,
                zorder=4,
            )
            ax.add_patch(rect)

    def _draw_zone(self, ax, zone: ZoneSpec, theme: dict) -> None:
        fill = zone.fill_color or (theme["zone_demand"] if zone.kind == "demand" else theme["zone_supply"])
        default_border = theme.get(
            "zone_border_demand" if zone.kind == "demand" else "zone_border_supply"
        )
        border = zone.border_color or default_border
        rect = Rectangle(
            (zone.x_start, zone.bottom),
            zone.x_end - zone.x_start,
            zone.top - zone.bottom,
            facecolor=fill,
            edgecolor=border or "none",
            alpha=zone.alpha or theme["zone_alpha"],
            linewidth=0.8 if border else 0.0,
            zorder=1,
        )
        ax.add_patch(rect)

    def _draw_horizontal_line(self, ax, line: HorizontalLine, candle_count: int) -> None:
        linestyle = (0, (4, 3)) if line.style == "dashed" else "-"
        ax.hlines(
            line.price,
            xmin=0,
            xmax=candle_count + 8,
            colors=line.color,
            linestyles=linestyle,
            linewidth=0.9,
            zorder=2,
            alpha=0.9,
        )
        if line.label:
            text = format_price(line.price) if line.label.startswith("T") else line.label
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
            x_points[:-1],
            y_points[:-1],
            color=color,
            linewidth=1.6 if style_name == "B" else 1.4,
            linestyle=(0, (2, 3)) if style_name == "A" else "-",
            zorder=5,
            solid_capstyle="round",
            alpha=0.95,
        )
        ax.annotate(
            "",
            xy=(x_points[-1], y_points[-1]),
            xytext=(x_points[-2], y_points[-2]),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=1.6 if style_name == "B" else 1.4,
                mutation_scale=12,
                shrinkA=0,
                shrinkB=0,
            ),
            zorder=6,
        )

    def _draw_price_label(self, ax, x: float, y: float, text: str, bg: str, fg: str) -> None:
        ax.text(
            x,
            y,
            f" {text} ",
            fontsize=9,
            color=fg,
            va="center",
            ha="left",
            fontweight="600",
            bbox={"boxstyle": "round,pad=0.22", "facecolor": bg, "edgecolor": "none"},
            zorder=7,
        )

    def _draw_header_and_watermarks(self, ax, spec: ChartSpec, theme: dict) -> None:
        header_color = theme.get("header_color", "#EFEFEF" if spec.style == "B" else "#2B2F39")
        if spec.style == "B":
            last = spec.candles[-1]
            change = last["close"] - spec.candles[0]["close"]
            change_pct = (change / spec.candles[0]["close"]) * 100 if spec.candles[0]["close"] else 0
            header = (
                f"{spec.symbol}  ·  {spec.interval}  ·  {spec.header_exchange}     "
                f"O {format_price(last['open'])}   H {format_price(last['high'])}   "
                f"L {format_price(last['low'])}   C {format_price(last['close'])}   "
                f"{change_pct:+.2f}%"
            )
            ax.set_title(header, color=header_color, fontsize=10, loc="left", pad=8, fontweight="500")
            if spec.watermark_tv:
                ax.text(
                    0.01, 0.04, "TradingView",
                    transform=ax.transAxes, fontsize=14, color=header_color,
                    alpha=0.35, fontweight="600",
                )
            if spec.watermark_smart:
                ax.text(
                    0.99, 0.04, "SMART",
                    transform=ax.transAxes, fontsize=16, color=header_color,
                    alpha=0.4, ha="right", fontweight="700",
                )
        else:
            ax.set_title(
                f"{spec.symbol}  ·  {spec.interval}  ·  Binance",
                color=header_color,
                fontsize=10,
                loc="left",
                pad=8,
                fontweight="500",
            )
