from __future__ import annotations
from pathlib import Path

from aiohttp import web

from charts.styles import CHART_THEME_PRESETS, infer_style_mode
from models import ChartSpec, HorizontalLine, ZoneSpec


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

    def _sample_candles(self) -> list[dict[str, float]]:
        candles = []
        price = 100.0
        for index in range(120):
            step = 1.6 if index % 7 in {1, 2, 3} else -1.1 if index % 9 in {4, 5} else 0.5
            open_ = price
            close = price + step
            high = max(open_, close) + 1.5
            low = min(open_, close) - 1.3
            candles.append({"time": index, "open": open_, "high": high, "low": low, "close": close, "volume": 1000 + index})
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

    async def preview_image(self, request: web.Request) -> web.Response:
        preset = request.match_info["preset"]
        if preset not in CHART_THEME_PRESETS:
            raise web.HTTPNotFound()
        path = PREVIEW_DIR / f"{preset}.png"
        if path.exists():
            return web.Response(body=path.read_bytes(), content_type="image/png")
        style_mode = infer_style_mode(preset, "B")
        candles = self._sample_candles()
        close_up = candles[-25:]
        last_price = close_up[-1]["close"]
        spec = ChartSpec(
            style=style_mode,
            symbol="BTCUSDT",
            interval="4h",
            theme_name=preset,
            candles=close_up,
            horizontal_lines=[
                HorizontalLine(price=round(last_price * 1.015, 1), color="#7BE27B", label="Resistance"),
                HorizontalLine(price=round(last_price * 0.985, 1), color="#FF5A6B", label="Support"),
            ],
            zones=[
                ZoneSpec(kind="demand", x_start=2, x_end=8, bottom=round(last_price * 0.96, 1), top=round(last_price * 0.99, 1)),
                ZoneSpec(kind="supply", x_start=14, x_end=20, bottom=round(last_price * 1.005, 1), top=round(last_price * 1.03, 1)),
            ],
            prediction_path=[(3, 4), (4, -2), (5, 8)] if style_mode == "B" else [(2, -3), (4, 4), (5, -7)],
            watermark_tv=True,
            watermark_smart=(style_mode == "B"),
            header_exchange="Binance",
        )
        data = self.chart_generator.render(spec)
        return web.Response(body=data, content_type="image/png")

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
        if channel_id and slot in field_map and preset in CHART_THEME_PRESETS:
            self.settings_repository.update(channel_id, {field_map[slot]: preset})
        raise web.HTTPFound(f"/style-gallery/{channel_id}")

    async def apply_zoom(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        channel_id = str(form.get("channel_id", "")).strip()
        slot = str(form.get("slot", "")).strip()
        zoom = str(form.get("zoom", "")).strip()
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

        cards = []
        for preset in sorted(CHART_THEME_PRESETS):
            is_signal = preset == current_signal
            is_smc = preset == current_smc
            is_morning = preset == current_morning
            name_ru = self._preset_name_ru(preset)
            cards.append(
                f"""
                <div class="card{' active' if is_signal or is_smc or is_morning else ''}">
                  <img src="/preview/{preset}" alt="{preset}" loading="lazy">
                  <div class="name">
                    {name_ru}
                    {'<span class="badge signal">SIG</span>' if is_signal else ''}
                    {'<span class="badge smc">SMC</span>' if is_smc else ''}
                    {'<span class="badge morning">MOR</span>' if is_morning else ''}
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
            zoom_names = {"tight": "Впритык", "standard": "Стандарт", "wide": "Отдалённый"}
            zoom_forms.append(
                f"""
                <form method="post" action="/apply-zoom" class="zoom-form">
                  <input type="hidden" name="channel_id" value="{channel_id}">
                  <input type="hidden" name="slot" value="{slot}">
                  <span class="zoom-label">{label}:</span>
                  <select name="zoom">
                    <option value="tight" {'selected' if current == 'tight' else ''}>Впритык (50)</option>
                    <option value="standard" {'selected' if current == 'standard' else ''}>Стандарт (80)</option>
                    <option value="wide" {'selected' if current == 'wide' else ''}>Отдалённый (120)</option>
                  </select>
                  <button>Применить</button>
                </form>
                """
            )
        html = f"""
        <html>
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Style Gallery</title>
          <style>
            * {{ box-sizing:border-box; }}
            body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0f1115; color:#fff; margin:0; padding:16px; }}
            .top {{ margin-bottom:16px; }}
            .grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px; }}
            .card {{ background:#171a21; border:2px solid #2a3040; border-radius:14px; overflow:hidden; transition:border-color .2s; }}
            .card.active {{ border-color:#2b7cff; }}
            .card img {{ width:100%; display:block; aspect-ratio:16/9; object-fit:cover; background:#000; }}
            .name {{ padding:12px 12px 0; font-weight:700; display:flex; align-items:center; gap:6px; flex-wrap:wrap; }}
            .badge {{ font-size:10px; padding:2px 6px; border-radius:4px; font-weight:700; }}
            .badge.signal {{ background:#2b7cff; color:#fff; }}
            .badge.smc {{ background:#e8a838; color:#000; }}
            .badge.morning {{ background:#50c878; color:#000; }}
            .actions {{ display:flex; gap:6px; padding:10px 12px 12px; flex-wrap:wrap; }}
            .actions form {{ margin:0; }}
            button {{ border:none; border-radius:8px; padding:8px 12px; cursor:pointer; font-size:13px; font-weight:600; transition:opacity .2s; }}
            button:active {{ opacity:.6; }}
            .btn-signal {{ background:#1a4a8a; color:#8ab8ff; }}
            .btn-signal.active {{ background:#2b7cff; color:#fff; }}
            .btn-smc {{ background:#6a4a10; color:#e8b848; }}
            .btn-smc.active {{ background:#e8a838; color:#000; }}
            .btn-morning {{ background:#1a5a30; color:#68d890; }}
            .btn-morning.active {{ background:#50c878; color:#000; }}
            .panel {{ background:#171a21; border:1px solid #2a3040; border-radius:14px; padding:16px; margin-bottom:16px; }}
            .panel h2 {{ margin:0 0 12px; font-size:20px; }}
            .zoom-form {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:6px 0; padding:8px; background:#12141c; border-radius:10px; }}
            .zoom-label {{ min-width:60px; font-weight:600; font-size:14px; }}
            select {{ padding:8px; border-radius:8px; border:1px solid #384158; background:#0f1115; color:#fff; font-size:13px; }}
            select:focus {{ outline:none; border-color:#2b7cff; }}
            .current-info {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:12px; }}
            .current-info span {{ background:#12141c; padding:6px 12px; border-radius:8px; font-size:13px; }}
          </style>
        </head>
        <body>
          <div class="top panel">
            <h2>Галерея стилей графиков</h2>
            <div class="current-info">
              <span style="border-left:3px solid #2b7cff;">Сигнал: <b>{self._preset_name_ru(current_signal)}</b></span>
              <span style="border-left:3px solid #e8a838;">SMC: <b>{self._preset_name_ru(current_smc)}</b></span>
              <span style="border-left:3px solid #50c878;">Утро: <b>{self._preset_name_ru(current_morning)}</b></span>
            </div>
            <h3 style="margin:12px 0 8px; font-size:15px;">Приближение графика (Zoom)</h3>
            {''.join(zoom_forms)}
          </div>
          <div class="grid">
            {''.join(cards)}
          </div>
        </body>
        </html>
        """
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
