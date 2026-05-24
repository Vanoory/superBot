from __future__ import annotations
import hashlib
import math
from pathlib import Path

from aiohttp import web

from charts.styles import CHART_THEME_PRESETS, infer_style_mode
from models import BosLevel, ChartSpec, HorizontalLine, PointOfInterest, ZoneSpec


PREVIEW_DIR = Path(__file__).resolve().parent / "style_previews"


class WebAppServer:
    def __init__(self, *, config, settings_repository, asset_manager, chart_generator) -> None:
        self.config = config
        self.settings_repository = settings_repository
        self.asset_manager = asset_manager
        self.chart_generator = chart_generator
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/style-gallery/{channel_id}", self.style_gallery)
        self.app.router.add_get("/content-studio/{channel_id}", self.content_studio)
        self.app.router.add_get("/preview/{preset}", self.preview_image)
        self.app.router.add_get("/preview-file/{preset}", self.preview_file)
        self.app.router.add_post("/apply-style", self.apply_style)
        self.app.router.add_post("/apply-zoom", self.apply_zoom)
        self.app.router.add_post("/save-example", self.save_example)
        self.app.router.add_post("/save-notes", self.save_notes)

    async def start(self) -> None:
        if self.runner is not None:
            return
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.config.webapp_bind_host, self.config.webapp_port)
        await site.start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

    async def health(self, request: web.Request) -> web.Response:
        return web.Response(text="ok")

    def _sample_candles(self, seed: str = "preview", count: int = 72) -> list[dict[str, float]]:
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        state = int.from_bytes(digest[:8], "big") or 1

        def _next_rand() -> float:
            nonlocal state
            state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
            return ((state >> 33) & 0xFFFFFFFF) / float(1 << 32)

        candles: list[dict[str, float]] = []
        price = 100.0 + _next_rand() * 8.0
        trend = (_next_rand() - 0.5) * 0.12
        volatility = 0.9 + _next_rand() * 0.6
        for index in range(count):
            if index in {count // 4, count // 2, (count * 3) // 4}:
                trend = (_next_rand() - 0.5) * 0.18
                volatility = 0.7 + _next_rand() * 0.9
            shock = (_next_rand() - 0.5) * volatility * 2.6
            wave = math.sin(index / 6.2) * 0.45 + math.cos(index / 9.7) * 0.3
            step = trend + shock + wave
            open_ = price
            close = max(1.0, price + step)
            wick_up = abs(_next_rand()) * volatility * 0.9 + 0.15
            wick_dn = abs(_next_rand()) * volatility * 0.9 + 0.15
            high = max(open_, close) + wick_up
            low = max(0.5, min(open_, close) - wick_dn)
            candles.append(
                {
                    "time": index,
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": 1000.0 + index,
                }
            )
            price = close
        return candles

    async def preview_file(self, request: web.Request) -> web.Response:
        preset = request.match_info["preset"]
        if preset not in CHART_THEME_PRESETS:
            raise web.HTTPNotFound()
        path = PREVIEW_DIR / f"{preset}.png"
        if path.exists():
            return web.Response(body=path.read_bytes(), content_type="image/png")
        raise web.HTTPNotFound()

    def _build_preview_spec(self, preset: str) -> ChartSpec:
        style_mode = infer_style_mode(preset, "B")
        candles = self._sample_candles(seed=preset, count=72)
        recent = candles[-58:]
        last = recent[-1]
        last_price = last["close"]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]
        swing_high = max(highs[-30:-6]) if len(recent) > 30 else max(highs)
        swing_low = min(lows[-30:-6]) if len(recent) > 30 else min(lows)
        bull_bias = last_price >= recent[-15]["close"]

        if style_mode == "A":
            poi_top = last_price * (1.018 if bull_bias else 0.985)
            poi_bottom = last_price * (1.002 if bull_bias else 0.965)
            target = swing_high * 1.012 if bull_bias else swing_low * 0.985
            stop = swing_low * 0.992 if bull_bias else swing_high * 1.012
            zones = [
                ZoneSpec(
                    kind="demand" if bull_bias else "supply",
                    x_start=len(recent) - 18,
                    x_end=len(recent) + 4,
                    bottom=min(poi_top, poi_bottom),
                    top=max(poi_top, poi_bottom),
                    label="POI",
                ),
            ]
            bos_levels = [
                BosLevel(
                    price=swing_high if bull_bias else swing_low,
                    bar=max(0, len(recent) - 22),
                    label="BOS",
                )
            ]
            poi_box = PointOfInterest(
                top=max(poi_top, poi_bottom),
                bottom=min(poi_top, poi_bottom),
                x_start=len(recent) - 18,
                x_end=len(recent) + 4,
                label="POI 4H FVG",
            )
            horizontal_lines = [
                HorizontalLine(price=target, color="#4B4F59", label="T1"),
                HorizontalLine(price=stop, color="#C65966", label="SL"),
            ]
            prediction = [
                (3, (poi_top - last_price) * 0.6),
                (5, (target - last_price) * 0.45),
                (8, (target - last_price) * 0.95),
            ] if bull_bias else [
                (3, (poi_bottom - last_price) * 0.7),
                (5, (target - last_price) * 0.5),
                (8, (target - last_price) * 0.95),
            ]
            return ChartSpec(
                style="A",
                symbol="BTCUSDT",
                interval="4h",
                theme_name=preset,
                candles=recent,
                zones=zones,
                bos_levels=bos_levels,
                horizontal_lines=horizontal_lines,
                prediction_path=prediction,
                poi_box=poi_box,
                watermark_tv=False,
                watermark_smart=False,
                header_exchange="Binance",
            )

        # style B (dark) — signal-style preview
        entry_top = last_price * (1.012 if not bull_bias else 0.992)
        entry_bottom = last_price * (1.032 if not bull_bias else 0.972)
        if bull_bias:
            entry_top, entry_bottom = max(entry_top, entry_bottom), min(entry_top, entry_bottom)
            target_1 = swing_high * 1.005
            target_2 = swing_high * 1.025
            stop = entry_bottom * 0.985
        else:
            entry_top, entry_bottom = max(entry_top, entry_bottom), min(entry_top, entry_bottom)
            target_1 = swing_low * 0.985
            target_2 = swing_low * 0.965
            stop = entry_top * 1.015

        zones = [
            ZoneSpec(
                kind="demand" if bull_bias else "supply",
                x_start=len(recent) - 16,
                x_end=len(recent) + 6,
                bottom=entry_bottom,
                top=entry_top,
                label="Entry",
            )
        ]
        horizontal_lines = [
            HorizontalLine(price=target_1, color="#5FD35F", label="T1"),
            HorizontalLine(price=target_2, color="#5FD35F", label="T2"),
            HorizontalLine(price=stop, color="#F45B69", label="SL"),
        ]
        if bull_bias:
            prediction = [
                (3, (entry_top - last_price) * 0.5),
                (5, (target_1 - last_price) * 0.55),
                (9, (target_2 - last_price) * 0.95),
            ]
        else:
            prediction = [
                (3, (entry_top - last_price) * 0.5),
                (5, (target_1 - last_price) * 0.45),
                (9, (target_2 - last_price) * 0.95),
            ]
        return ChartSpec(
            style="B",
            symbol="BTCUSDT",
            interval="4h",
            theme_name=preset,
            candles=recent,
            zones=zones,
            horizontal_lines=horizontal_lines,
            prediction_path=prediction,
            watermark_tv=True,
            watermark_smart=True,
            header_exchange="Bybit",
        )

    async def preview_image(self, request: web.Request) -> web.Response:
        preset = request.match_info["preset"]
        if preset not in CHART_THEME_PRESETS:
            raise web.HTTPNotFound()
        path = PREVIEW_DIR / f"{preset}.png"
        if path.exists():
            return web.Response(body=path.read_bytes(), content_type="image/png")
        spec = self._build_preview_spec(preset)
        data = self.chart_generator.render(spec)
        return web.Response(
            body=data,
            content_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    async def apply_style(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        channel_id = str(form.get("channel_id", "")).strip()
        slot = str(form.get("slot", "")).strip()
        preset = str(form.get("preset", "")).strip()
        field_map = {
            "signal": "chart_style_signal_preset",
            "smc": "chart_style_smc_preset",
            "morning": "chart_style_morning_preset",
        }
        if not channel_id:
            raise web.HTTPBadRequest(text="channel_id is required")
        if slot in field_map and preset in CHART_THEME_PRESETS:
            self.settings_repository.update(channel_id, {field_map[slot]: preset})
        raise web.HTTPFound(f"/style-gallery/{channel_id}")

    async def apply_zoom(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        channel_id = str(form.get("channel_id", "")).strip()
        slot = str(form.get("slot", "")).strip()
        zoom = str(form.get("zoom", "")).strip()
        if not channel_id:
            raise web.HTTPBadRequest(text="channel_id is required")
        if slot in {"signal", "smc", "morning"} and zoom in {"tight", "standard", "wide"}:
            self.settings_repository.update(channel_id, {f"chart_zoom_{slot}": zoom})
        raise web.HTTPFound(f"/style-gallery/{channel_id}")

    async def save_example(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        channel_id = str(form.get("channel_id", "")).strip()
        text = str(form.get("text", "")).strip()
        sample_kind = str(form.get("sample_kind", "auto")).strip() or "auto"
        if channel_id and text:
            self.asset_manager.save_text_sample(channel_id, text, sample_kind=sample_kind)
        raise web.HTTPFound(f"/content-studio/{channel_id}")

    async def save_notes(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        channel_id = str(form.get("channel_id", "")).strip()
        notes = str(form.get("notes", "")).strip()
        if channel_id:
            self.settings_repository.update(channel_id, {"writing_style_notes": notes})
        raise web.HTTPFound(f"/content-studio/{channel_id}")

    def _preset_name_ru(self, preset: str) -> str:
        names = {
            "light_classic": "Классический светлый",
            "light_minimal": "Минималистичный",
            "light_blueprint": "Чертеж",
            "light_paper": "Бумага",
            "light_terminal": "Терминал",
            "light_pastel": "Пастельный",
            "light_sky": "Небесный",
            "light_sand": "Песочный",
            "light_lavender": "Лаванда",
            "light_mint": "Мятный",
            "light_coral": "Коралловый",
            "light_spring": "Весенний",
            "light_rose": "Розовый",
            "light_slate": "Сланцевый",
            "dark_tv": "TradingView",
            "dark_clean": "Чистый тёмный",
            "dark_neon": "Неоновый",
            "dark_gold": "Золотой",
            "dark_crimson": "Багровый",
            "dark_ocean": "Океан",
            "dark_matrix": "Матрица",
            "dark_amber": "Янтарный",
            "dark_plasma": "Плазма",
            "dark_cyber": "Киберпанк",
            "dark_steel": "Стальной",
            "dark_graphite": "Графит",
            "dark_blood": "Кровавый",
            "dark_royal": "Королевский",
            "dark_emerald": "Изумруд",
            "dark_obsidian": "Обсидиан",
            "dark_rust": "Ржавый",
            "dark_arctic": "Арктика",
            "dark_lava": "Лава",
            "dark_purple": "Пурпурный",
            "dark_marine": "Морской",
            "dark_copper": "Медный",
            "dark_shadow": "Тень",
            "dark_candy": "Конфетный",
            "dark_azure": "Лазурный",
            "dark_mocha": "Мокко",
            "dark_mint": "Тёмно-мятный",
            "dark_oil": "Нефть",
        }
        return names.get(preset, preset)

    async def style_gallery(self, request: web.Request) -> web.Response:
        channel_id = request.match_info["channel_id"]
        settings = self.settings_repository.get(channel_id)
        current_signal = settings.get("chart_style_signal_preset", "dark_tv")
        current_smc = settings.get("chart_style_smc_preset", "light_classic")
        current_morning = settings.get("chart_style_morning_preset", "dark_tv")

        def _group(preset: str) -> str:
            return "light" if CHART_THEME_PRESETS[preset].get("style_mode") == "A" else "dark"

        cards = []
        for preset in sorted(CHART_THEME_PRESETS, key=lambda key: (_group(key), key)):
            is_signal = preset == current_signal
            is_smc = preset == current_smc
            is_morning = preset == current_morning
            name_ru = self._preset_name_ru(preset)
            badges = []
            if is_signal:
                badges.append('<span class="badge signal">SIG</span>')
            if is_smc:
                badges.append('<span class="badge smc">SMC</span>')
            if is_morning:
                badges.append('<span class="badge morning">MOR</span>')
            mode_label = "Light" if _group(preset) == "light" else "Dark"
            cards.append(
                f"""
                <div class="card{' active' if (is_signal or is_smc or is_morning) else ''}" data-group="{_group(preset)}">
                  <div class="preview-wrap">
                    <img src="/preview/{preset}" alt="{name_ru}" loading="lazy">
                    <span class="mode-chip">{mode_label}</span>
                  </div>
                  <div class="name">
                    <span class="title">{name_ru}</span>
                    <span class="badges">{''.join(badges)}</span>
                  </div>
                  <div class="actions">
                    <form method="post" action="/apply-style">
                      <input type="hidden" name="channel_id" value="{channel_id}">
                      <input type="hidden" name="slot" value="signal">
                      <input type="hidden" name="preset" value="{preset}">
                      <button class="btn-signal{' active' if is_signal else ''}">Сигнал</button>
                    </form>
                    <form method="post" action="/apply-style">
                      <input type="hidden" name="channel_id" value="{channel_id}">
                      <input type="hidden" name="slot" value="smc">
                      <input type="hidden" name="preset" value="{preset}">
                      <button class="btn-smc{' active' if is_smc else ''}">SMC</button>
                    </form>
                    <form method="post" action="/apply-style">
                      <input type="hidden" name="channel_id" value="{channel_id}">
                      <input type="hidden" name="slot" value="morning">
                      <input type="hidden" name="preset" value="{preset}">
                      <button class="btn-morning{' active' if is_morning else ''}">Утро</button>
                    </form>
                  </div>
                </div>
                """
            )
        zoom_forms = []
        for slot, label in [("signal", "Сигнал"), ("smc", "SMC"), ("morning", "Утро")]:
            current = settings.get(f"chart_zoom_{slot}", "standard")
            zoom_forms.append(
                f"""
                <form method="post" action="/apply-zoom" class="zoom-form">
                  <input type="hidden" name="channel_id" value="{channel_id}">
                  <input type="hidden" name="slot" value="{slot}">
                  <span class="zoom-label">{label}</span>
                  <select name="zoom">
                    <option value="tight" {'selected' if current == 'tight' else ''}>Впритык · 50 свечей</option>
                    <option value="standard" {'selected' if current == 'standard' else ''}>Стандарт · 80 свечей</option>
                    <option value="wide" {'selected' if current == 'wide' else ''}>Отдалённый · 120 свечей</option>
                  </select>
                  <button class="apply-btn">Применить</button>
                </form>
                """
            )
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Галерея стилей · {channel_id}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    :root {{
      --bg-1: #05070d;
      --bg-2: #0b1020;
      --panel: rgba(20, 24, 38, 0.78);
      --panel-border: rgba(120, 140, 200, 0.18);
      --text: #f1f3fb;
      --muted: #8a93b2;
      --accent: #7aa7ff;
      --accent-2: #b388ff;
      --signal: #4f8cff;
      --smc: #ffb84d;
      --morning: #5fd989;
    }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Display', sans-serif;
      color: var(--text);
      background:
        radial-gradient(1100px 700px at 8% -10%, rgba(125, 86, 255, 0.22), transparent 60%),
        radial-gradient(1300px 800px at 95% 0%, rgba(60, 130, 255, 0.20), transparent 65%),
        radial-gradient(900px 600px at 50% 110%, rgba(255, 160, 80, 0.10), transparent 60%),
        linear-gradient(180deg, var(--bg-1) 0%, var(--bg-2) 100%);
      min-height: 100vh;
      padding: 24px clamp(16px, 4vw, 48px) 64px;
      overflow-x: hidden;
    }}
    body::before {{
      content: "";
      position: fixed; inset: 0;
      background-image:
        radial-gradient(1px 1px at 20% 30%, rgba(255,255,255,0.65) 0, transparent 50%),
        radial-gradient(1.4px 1.4px at 78% 18%, rgba(255,255,255,0.55) 0, transparent 50%),
        radial-gradient(1px 1px at 55% 70%, rgba(255,255,255,0.45) 0, transparent 50%),
        radial-gradient(1.6px 1.6px at 12% 82%, rgba(255,255,255,0.5) 0, transparent 50%),
        radial-gradient(1px 1px at 88% 92%, rgba(255,255,255,0.4) 0, transparent 50%),
        radial-gradient(1.2px 1.2px at 33% 60%, rgba(255,255,255,0.5) 0, transparent 50%);
      pointer-events: none;
      opacity: 0.55;
      z-index: 0;
    }}
    .wrap {{ position: relative; z-index: 1; max-width: 1500px; margin: 0 auto; }}
    .hero {{
      background: var(--panel);
      backdrop-filter: blur(18px) saturate(140%);
      -webkit-backdrop-filter: blur(18px) saturate(140%);
      border: 1px solid var(--panel-border);
      border-radius: 22px;
      padding: 24px 26px;
      margin-bottom: 22px;
      box-shadow: 0 30px 60px -30px rgba(0, 0, 0, 0.6);
    }}
    .hero h1 {{
      margin: 0 0 4px;
      font-size: clamp(22px, 3vw, 30px);
      font-weight: 700;
      letter-spacing: -0.02em;
      background: linear-gradient(120deg, #ffffff 0%, #cdd6ff 55%, #b39bff 100%);
      -webkit-background-clip: text; background-clip: text; color: transparent;
    }}
    .hero p {{ margin: 0; color: var(--muted); font-size: 14px; }}
    .current {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }}
    .pill {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 14px; border-radius: 999px;
      font-size: 13px; font-weight: 600;
      background: rgba(20, 28, 50, 0.7);
      border: 1px solid rgba(255,255,255,0.06);
    }}
    .pill .dot {{ width: 8px; height: 8px; border-radius: 50%; }}
    .pill.signal .dot {{ background: var(--signal); box-shadow: 0 0 12px var(--signal); }}
    .pill.smc .dot {{ background: var(--smc); box-shadow: 0 0 12px var(--smc); }}
    .pill.morning .dot {{ background: var(--morning); box-shadow: 0 0 12px var(--morning); }}
    .pill b {{ color: #fff; font-weight: 700; }}
    .pill span.role {{ color: var(--muted); margin-right: 2px; }}

    .panel {{
      background: var(--panel);
      backdrop-filter: blur(14px) saturate(140%);
      -webkit-backdrop-filter: blur(14px) saturate(140%);
      border: 1px solid var(--panel-border);
      border-radius: 18px;
      padding: 18px 22px;
      margin-bottom: 22px;
    }}
    .panel h3 {{ margin: 0 0 12px; font-size: 15px; font-weight: 700; letter-spacing: 0.02em; color: var(--text); }}
    .zoom-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .zoom-form {{
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px; border-radius: 14px;
      background: rgba(11, 14, 28, 0.75);
      border: 1px solid rgba(120, 140, 200, 0.12);
      flex: 1 1 280px;
    }}
    .zoom-label {{ min-width: 70px; font-weight: 700; font-size: 13px; color: var(--text); letter-spacing: 0.04em; text-transform: uppercase; }}
    select {{
      flex: 1; padding: 8px 10px;
      border: 1px solid rgba(120, 140, 200, 0.18);
      background: rgba(7, 10, 22, 0.9);
      color: var(--text); font-size: 13px;
      border-radius: 10px; appearance: none;
    }}
    select:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(122,167,255,0.18); }}
    .apply-btn {{
      padding: 8px 14px; border-radius: 10px; border: none; cursor: pointer;
      font-weight: 700; font-size: 13px;
      color: #0a0e1a;
      background: linear-gradient(135deg, #cfd9ff 0%, #8aa6ff 100%);
      transition: transform .15s ease, box-shadow .15s ease, opacity .15s ease;
    }}
    .apply-btn:hover {{ transform: translateY(-1px); box-shadow: 0 10px 24px -10px rgba(122,167,255,0.6); }}

    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 18px; }}
    .filter-btn {{
      padding: 8px 14px; border-radius: 999px; border: 1px solid rgba(120, 140, 200, 0.18);
      background: rgba(20, 28, 50, 0.5); color: var(--text); font-weight: 600; font-size: 13px;
      cursor: pointer; transition: background .15s ease, border-color .15s ease;
    }}
    .filter-btn.active {{ background: rgba(122, 167, 255, 0.18); border-color: var(--accent); color: #fff; }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 18px;
      overflow: hidden;
      transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
      display: flex; flex-direction: column;
    }}
    .card:hover {{ transform: translateY(-2px); box-shadow: 0 20px 50px -25px rgba(0, 0, 0, 0.7); border-color: rgba(122,167,255,0.4); }}
    .card.active {{ border-color: rgba(122,167,255,0.6); box-shadow: 0 0 0 1px rgba(122,167,255,0.35), 0 24px 50px -25px rgba(122,167,255,0.45); }}
    .preview-wrap {{
      position: relative; width: 100%; aspect-ratio: 16/9; overflow: hidden;
      background: linear-gradient(135deg, #0a0d18 0%, #11162a 100%);
    }}
    .preview-wrap img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .mode-chip {{
      position: absolute; top: 10px; right: 10px;
      font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
      padding: 4px 10px; border-radius: 999px;
      background: rgba(5, 8, 18, 0.75); border: 1px solid rgba(255,255,255,0.12); color: #d6dcf5;
      text-transform: uppercase; backdrop-filter: blur(6px);
    }}
    .name {{ padding: 14px 16px 4px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
    .name .title {{ font-weight: 700; font-size: 15px; letter-spacing: -0.01em; }}
    .badges {{ display: inline-flex; gap: 4px; }}
    .badge {{
      font-size: 10px; font-weight: 800; letter-spacing: 0.06em;
      padding: 3px 7px; border-radius: 6px; color: #0a0e1a;
    }}
    .badge.signal {{ background: var(--signal); color: #fff; }}
    .badge.smc {{ background: var(--smc); }}
    .badge.morning {{ background: var(--morning); }}
    .actions {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; padding: 12px 14px 14px; }}
    .actions form {{ margin: 0; }}
    .actions button {{
      width: 100%; padding: 8px 6px; border-radius: 10px; border: 1px solid rgba(120,140,200,0.18);
      font-size: 12px; font-weight: 700; cursor: pointer;
      background: rgba(11, 14, 28, 0.6); color: var(--muted);
      transition: transform .15s ease, background .15s ease, color .15s ease;
    }}
    .actions button:hover {{ transform: translateY(-1px); color: #fff; }}
    .actions .btn-signal.active {{ background: linear-gradient(135deg, #4f8cff, #6f7bff); color: #fff; border-color: transparent; }}
    .actions .btn-smc.active {{ background: linear-gradient(135deg, #ffb84d, #ffd084); color: #1a1208; border-color: transparent; }}
    .actions .btn-morning.active {{ background: linear-gradient(135deg, #5fd989, #79e5a8); color: #06160c; border-color: transparent; }}

    @media (max-width: 540px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>Галерея стилей графиков</h1>
      <p>Канал {channel_id} · Выбери стиль для каждого типа постов и прокликай Zoom — превью обновится автоматически.</p>
      <div class="current">
        <span class="pill signal"><span class="dot"></span><span class="role">Сигнал:</span><b>{self._preset_name_ru(current_signal)}</b></span>
        <span class="pill smc"><span class="dot"></span><span class="role">SMC:</span><b>{self._preset_name_ru(current_smc)}</b></span>
        <span class="pill morning"><span class="dot"></span><span class="role">Утро:</span><b>{self._preset_name_ru(current_morning)}</b></span>
      </div>
    </div>

    <div class="panel">
      <h3>Приближение графиков (Zoom)</h3>
      <div class="zoom-row">
        {''.join(zoom_forms)}
      </div>
    </div>

    <div class="filters">
      <button class="filter-btn active" data-filter="all">Все стили</button>
      <button class="filter-btn" data-filter="dark">Тёмные</button>
      <button class="filter-btn" data-filter="light">Светлые</button>
    </div>

    <div class="grid" id="grid">
      {''.join(cards)}
    </div>
  </div>

  <script>
    (function() {{
      const buttons = document.querySelectorAll('.filter-btn');
      const cards = document.querySelectorAll('.card');
      buttons.forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          buttons.forEach(function(b) {{ b.classList.remove('active'); }});
          btn.classList.add('active');
          const filter = btn.getAttribute('data-filter');
          cards.forEach(function(card) {{
            const group = card.getAttribute('data-group');
            card.style.display = (filter === 'all' || filter === group) ? '' : 'none';
          }});
        }});
      }});
    }})();
  </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def content_studio(self, request: web.Request) -> web.Response:
        channel_id = request.match_info["channel_id"]
        settings = self.settings_repository.get(channel_id)
        sample_count = self.asset_manager.profile_summary(channel_id)["text_samples"]

        kind_options = [
            ("auto", "Авто (бот определит сам)"),
            ("morning_brief", "Утро — короткий"),
            ("morning_analysis", "Утро — с разбором"),
            ("signal", "Сигнал / сетап"),
            ("news", "Новости"),
            ("ad", "Реклама"),
            ("general", "Обычный пост"),
        ]
        kind_select = "".join(
            f'<option value="{v}">{l}</option>' for v, l in kind_options
        )

        html = f"""
        <html>
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Content Studio</title>
          <style>
            * {{ box-sizing:border-box; }}
            body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#101317; color:#fff; margin:0; padding:16px; }}
            .panel {{ background:#171a21; border:1px solid #2a3040; border-radius:14px; padding:16px; margin-bottom:16px; }}
            .panel h2 {{ margin:0 0 8px; font-size:20px; }}
            .panel h3 {{ margin:0 0 12px; font-size:16px; color:#aab; }}
            textarea {{ width:100%; min-height:160px; padding:12px; border-radius:10px; border:1px solid #384158; background:#0f1115; color:#fff; font-size:14px; font-family:inherit; resize:vertical; }}
            textarea:focus {{ outline:none; border-color:#2b7cff; }}
            select, button {{ padding:10px 14px; border-radius:10px; font-size:14px; }}
            select {{ border:1px solid #384158; background:#0f1115; color:#fff; }}
            select:focus {{ outline:none; border-color:#2b7cff; }}
            button {{ background:#2b7cff; color:#fff; border:none; cursor:pointer; font-weight:600; }}
            button:active {{ opacity:.7; }}
            .row {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:12px; align-items:center; }}
            .stat {{ display:inline-block; background:#12141c; padding:6px 14px; border-radius:20px; font-size:13px; color:#889; }}
            .hint {{ font-size:13px; color:#667; margin:8px 0 0; }}
          </style>
        </head>
        <body>
          <div class="panel">
            <h2>Content Studio</h2>
            <p style="color:#889; margin:4px 0;">
              Канал: {channel_id}
              <span class="stat">Примеров: {sample_count}</span>
            </p>
            <p>Загружай примеры постов, а бот будет использовать их как референс для стиля. Если оставить категорию «Авто», бот сам определит тип поста.</p>
          </div>
          <div class="panel">
            <h3>Заметки по стилю</h3>
            <p class="hint">Опиши словами, в каком стиле должны быть посты (тон, сленг, эмодзи, структура)</p>
            <form method="post" action="/save-notes">
              <input type="hidden" name="channel_id" value="{channel_id}">
              <textarea name="notes" placeholder="Пиши свободно, например: «используй сленг трейдеров, добавляй эмодзи, пиши кратко и по делу»">{settings.get('writing_style_notes', '')}</textarea>
              <div class="row"><button>Сохранить заметки</button></div>
            </form>
          </div>
          <div class="panel">
            <h3>Добавить пример поста</h3>
            <p class="hint">Вставь текст поста, который тебе нравится. Бот будет использовать похожий стиль.</p>
            <form method="post" action="/save-example">
              <input type="hidden" name="channel_id" value="{channel_id}">
              <textarea name="text" placeholder="Вставь сюда пример поста..."></textarea>
              <div class="row">
                <select name="sample_kind">{kind_select}</select>
                <button>Сохранить пример</button>
              </div>
            </form>
          </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")
