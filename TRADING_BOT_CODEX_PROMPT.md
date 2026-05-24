# 🤖 TRADING CHANNEL BOT — FULL TECHNICAL SPECIFICATION FOR CODEX

## PROJECT OVERVIEW

Build a **Python Telegram bot** that fully automates a **crypto trading channel** in Russian.
The bot uses **free APIs only** (Binance public API, Claude/OpenAI API via free tier, investing.com scraping).
It mimics the author's unique writing style, generates **pixel-perfect charts** matching example images, and sends every post for admin approval before publishing.

---

## ARCHITECTURE

```
trading_bot/
├── main.py                  # Entry point, polling loop
├── config.py                # All settings, tokens, keys
├── scheduler.py             # APScheduler jobs (morning post, analysis, news)
├── admin_bot.py             # Admin approval/edit bot (separate bot token)
├── channel_bot.py           # Sends approved posts to channel
├── market/
│   ├── binance_api.py       # Fetch OHLCV data via Binance public REST API (no key needed)
│   ├── signal_engine.py     # Smart Money + strategy signal detection
│   └── analysis.py         # Market narrative generator (calls AI API)
├── charts/
│   ├── chart_generator.py   # MAIN chart renderer — see CHART SECTION below
│   ├── styles.py            # All visual constants (colors, fonts, sizes)
│   └── backgrounds/         # Folder with background images (dark car/city style)
├── posts/
│   ├── morning_post.py      # Morning post generator
│   ├── signal_post.py       # Signal post generator
│   ├── news_post.py         # Economic calendar news post
│   ├── filler_post.py       # Casual "filler" posts
│   └── ad_post.py           # Advertising integration posts
├── ai/
│   └── claude_client.py     # Anthropic Claude API client (style mimicking)
├── storage/
│   ├── channels.json        # Registered channel IDs
│   └── settings.json        # Per-channel user settings
└── requirements.txt
```

---

## CHANNEL REGISTRATION

- Admin sends channel ID (e.g. `-100123456789` or `@channelname`) to the admin bot
- Bot verifies it's an admin in that channel via `getChatMember`
- Stores channel ID in `channels.json`
- Supports both **private** (by ID) and **public** (by @username) channels
- One bot instance can manage multiple channels

---

## 1. CHART GENERATION (CRITICAL — MUST MATCH EXAMPLES PIXEL-PERFECTLY)

### Visual Style Reference (from uploaded example images prim1.PNG–prim4.PNG and channel screenshots)

Two chart styles are used:

#### STYLE A — Clean White Background (prim1–prim4 style)
Used for: Smart Money analysis posts (BOS, FVG zones, structure)

```python
STYLE_A = {
    "bg_color": "#FFFFFF",
    "candle_bull": "#26A69A",        # Teal/green fill
    "candle_bear": "#FFFFFF",        # White body, dark border
    "candle_border_bull": "#26A69A",
    "candle_border_bear": "#555555",
    "wick_color": "#555555",
    "zone_bull_fill": "#B2DFDB",     # Light teal for demand zones
    "zone_bear_fill": "#D3D3D3",     # Gray for supply/resistance zones
    "zone_alpha": 0.45,
    "arrow_bull_color": "#555555",   # Dark gray arrow pointing up
    "arrow_bear_color": "#888888",   # Gray arrow pointing down
    "bos_line_color": "#00BCD4",     # Cyan dashed line
    "bos_label_color": "#00BCD4",
    "price_label_bg": "#000000",     # Black box for current price
    "price_label_color": "#FFFFFF",
    "alt_price_label_bg": "#26A69A", # Green box for target price
    "dashed_line_color": "#999999",
    "horizontal_line_color": "#CCCCCC",
    "grid_color": "#F0F0F0",
    "font": "Arial",
    "price_font_size": 11,
    "axis_color": "#999999",
    "image_size": (900, 600),        # px
    "dpi": 100,
    "candle_width_ratio": 0.6,       # relative to spacing
}
```

#### STYLE B — Dark Background with Car/City (channel post style)
Used for: Signal posts, morning BTC posts (images 10, 11 style)

```python
STYLE_B = {
    "bg_image_folder": "charts/backgrounds/",   # Dark Mercedes/city JPG images
    "bg_overlay_alpha": 0.55,                   # Darken background image
    "candle_bull": "#FFFFFF",        # White candles on dark bg
    "candle_bear": "#FFFFFF",
    "candle_bull_filled": False,     # Hollow
    "candle_bear_filled": True,      # Filled black
    "candle_border_color": "#FFFFFF",
    "wick_color": "#FFFFFF",
    "zone_bull_fill": "#1B5E20",     # Dark green rectangle
    "zone_bear_fill": "#B71C1C",     # Dark red rectangle
    "zone_alpha": 0.35,
    "zone_border_bull": "#4CAF50",   # Green border
    "zone_border_bear": "#F44336",   # Red border
    "target_line_color": "#4CAF50",  # Green horizontal target lines
    "stop_line_color": "#F44336",    # Red horizontal stop line
    "target_label_bg": "#4CAF50",
    "stop_label_bg": "#F44336",
    "prediction_arrow_color": "#FFFFFF",  # White zigzag prediction line
    "prediction_arrow_width": 2,
    "price_label_bg": "#333333",
    "watermark_tv": True,            # "TradingView" bottom left
    "watermark_smart": True,         # "SMART" bottom right
    "header_text": True,             # "BTCUSDT Perpetual Contract · 1ч · Bybit"
    "header_color": "#CCCCCC",
    "buy_sell_labels": True,         # ПРОДАТЬ/КУПИТЬ buttons style top left
    "image_size": (1280, 720),
    "dpi": 100,
}
```

### Chart Components to Render (matplotlib + mplfinance or pure matplotlib)

```python
def generate_chart(
    symbol: str,           # e.g. "BTCUSDT"
    interval: str,         # e.g. "4h", "1d", "1h"
    candles: int = 60,     # number of candles to show
    style: str = "A",      # "A" or "B"
    zones: list = None,    # [{"type": "demand"|"supply", "top": float, "bottom": float}]
    bos_levels: list = None, # [{"price": float, "label": "BOS", "direction": "up"|"down"}]
    horizontal_lines: list = None,  # [{"price": float, "color": str, "style": "solid"|"dashed", "label": str}]
    prediction_path: list = None,   # [(bar_offset, price), ...] — zigzag arrow from last candle
    arrows: list = None,  # [{"bar": int, "price": float, "direction": "up"|"down"}]
    current_price_label: bool = True,
    extra_labels: list = None,  # [{"price": float, "text": str, "bg_color": str}]
    poi_box: dict = None,       # {"top": float, "bottom": float, "label": "POI 4H FVG"}
    weak_high_label: float = None,
) -> bytes:  # returns PNG bytes
```

### Prediction Line (CRITICAL)
The white zigzag arrow showing predicted price movement must be rendered as a **polyline with an arrowhead at the end**:
- Line width: 1.5–2px
- Color: white (Style B) or dark gray (Style A)
- Arrowhead: solid filled triangle, size ~12px
- The line goes from the last visible candle rightward into empty space
- No candles drawn in the prediction area — only the line

### Zone Rendering
- Zones are **filled rectangles** spanning the full width of the zone area
- Use `ax.axhspan(bottom, top, alpha=alpha, color=color, zorder=1)`
- Draw a thin border line on top and bottom of zone
- Zones rendered BEHIND candles (low zorder)

### BOS (Break of Structure) Lines
- Dashed horizontal line extending from the BOS candle to the right edge
- Cyan color (#00BCD4) with label "BOS" above the line
- Arrow marker showing direction of break

### Background Images (Style B)
- Load a random dark background image from `charts/backgrounds/`
- Resize to chart size (1280x720)
- Apply dark overlay: `plt.imshow(bg, aspect='auto', alpha=0.55, zorder=0)`
- All chart elements drawn on top with high zorder

---

## 2. MARKET DATA — BINANCE PUBLIC API (FREE, NO KEY)

```python
import requests

BASE = "https://api.binance.com/api/v3"

def get_klines(symbol: str, interval: str, limit: int = 100) -> list:
    """Returns OHLCV candles. interval: 1m,5m,15m,1h,4h,1d,1w"""
    r = requests.get(f"{BASE}/klines", params={
        "symbol": symbol, "interval": interval, "limit": limit
    })
    data = r.json()
    # Returns: [[open_time, open, high, low, close, volume, ...], ...]
    return [{
        "time": d[0], "open": float(d[1]), "high": float(d[2]),
        "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])
    } for d in data]

def get_all_usdt_pairs() -> list:
    """Get all USDT trading pairs for scanning"""
    r = requests.get(f"{BASE}/exchangeInfo")
    return [s["symbol"] for s in r.json()["symbols"]
            if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"]

def get_ticker_24h(symbol: str) -> dict:
    r = requests.get(f"{BASE}/ticker/24hr", params={"symbol": symbol})
    return r.json()
```

---

## 3. SIGNAL ENGINE

### Mode 1: Smart Money (SMC)
Detect automatically:
- **BOS (Break of Structure)**: price closes above last swing high (bullish BOS) or below last swing low (bearish BOS)
- **FVG (Fair Value Gap)**: three-candle pattern where candle[i-1].high < candle[i+1].low (bullish) or candle[i-1].low > candle[i+1].high (bearish)
- **Demand/Supply Zones**: consolidation areas before strong impulse moves
- **Liquidity Pools**: previous swing highs/lows (equal highs/lows = liquidity)
- **POI (Point of Interest)**: confluence of FVG + structure level

```python
def find_smc_signal(candles: list, symbol: str) -> dict | None:
    """
    Returns signal dict or None if no clear setup found.
    {
        "type": "long"|"short",
        "entry_zone": (low, high),
        "target": float,
        "stop": float,
        "confluence": ["BOS", "FVG 4H", "Demand Zone"],
        "description_ru": str,  # AI-generated Russian text
        "chart_elements": {...}  # zone, bos, poi data for chart
    }
    """
```

### Mode 2: Strategy Signals
Simple rule-based: EMA crossover, RSI divergence, support/resistance bounce
Configurable per channel in settings.

---

## 4. AI TEXT GENERATION — STYLE MIMICKING

Use **Anthropic Claude API** (`claude-haiku-3-5` for cost efficiency).

### Writing Style Reference (from channel screenshots — BULLDOG TRADE style):

Casual Russian crypto trader tone. Key characteristics:
- Starts morning posts with "Доброе утро!" 
- Uses 🐂💰🎯📊 emojis naturally but not excessively
- Lowercase sometimes even for proper nouns ("биток", "солана", "эфир")
- Uses slang: "биток" (BTC), "солана" (SOL), "альта" (altcoins), "лонг", "шорт", "снял пул ликвидности", "лою", "сетап"
- Writes like texting, not a formal report
- Comments on his own trades casually: "у меня открытый лонг и шорт"
- Adds commentary like: "и кстати вчерашняя аналитика по битку отработала идеально"
- Signs off with: "всем спокойной ночи", "идите в зал", "p.s..."
- Adds humor: "))) логично"

### System Prompt for Claude (store in `ai/prompts.py`):

```python
STYLE_SYSTEM_PROMPT = """
Ты — автор Telegram-канала по крипто-трейдингу. Пишешь на русском языке в неформальном стиле.

СТИЛЬ НАПИСАНИЯ:
- Пиши как живой человек в мессенджере, не как аналитик
- Используй сленг: "биток", "солана", "альта", "лонг", "шорт", "пул ликвидности", "сетап", "набирать", "скинуть"  
- Добавляй личные комментарии и мнения от первого лица
- Иногда пиши с маленькой буквы (casual)
- Используй эмодзи умеренно: 🐂 🎯 💰 📊 🔥 — только по месту
- Добавляй разговорные фразы: "ну пока рынок стоит на месте", "в принципе логично))", "пусть немного успокоится"
- После сигналов добавляй ремарки: "позицию рекомендую открывать на 1-3% от депозита"
- Подписывай посты ссылками на чат или ВИП
- НЕ ИСПОЛЬЗУЙ: "данный", "следует отметить", "в целом", канцелярит
- Форматирование — только если нужно, можно жирный текст и буллеты для сигналов

ФОРМАТ СИГНАЛА (если нужен):
🎯 SYMBOL/USDT - Long/Short

• Зона набора: X-Y$
• Плечо: Nx  
• Цели: Z1, Z2$
• Стоп: W$

Текст описания 1-3 предложения.
"""
```

---

## 5. POST TYPES

### 5.1 Morning Post (`morning_post.py`)
**Schedule**: 9:00 UTC+3 daily

**Configurable options (per user in settings)**:
- `no_chart` — only text
- `btc_chart` — BTC daily/4h chart attached
- `custom_chart` — chart of configured coin

**Content**:
1. Greeting + brief market overview (3-5 sentences)
2. Key levels for the day
3. What to watch (upcoming news, key resistance/support)
4. Optional reminder about VIP/chat

**Generation**:
```python
async def generate_morning_post(settings: dict) -> dict:
    btc_data = get_klines("BTCUSDT", "1d", 30)
    market_context = analyze_market_context(btc_data)
    
    text = await claude_generate(
        system=STYLE_SYSTEM_PROMPT,
        user=f"Напиши утренний пост для крипто-канала. Контекст рынка: {market_context}. "
             f"Биткоин сейчас: {btc_data[-1]['close']}$. "
             f"Стиль: неформальный, как обычно пишу я. Начни с 'Доброе утро!'"
    )
    
    chart = None
    if settings.get("morning_chart") == "btc_chart":
        chart = generate_chart("BTCUSDT", "4h", style="B", ...)
    
    return {"text": text, "chart": chart}
```

### 5.2 Signal Post (`signal_post.py`)
**Trigger**: When signal_engine finds a setup (checked every 30 min)

**Two modes** (set per channel):
- **SMC Mode**: Full Smart Money breakdown with chart markings (zones, BOS, POI)
- **Strategy Mode**: Simple chart + signal text only

**Post format (Strategy mode)**:
```
🎯 SOLUSDT - Short

• Зона набора: 91.41-94.25$
• Плечо: 10x
• Цели: 87.60$, 83.24$  
• Стоп: 96.50$
• Стоп в БУ: переносим после достижения первой цели

Солянку смотрю в шорт от выделенного имба (91.41-94.25), 
планирую набирать после снятия локального пула ликвидности (92.02).

Позицию рекомендую открывать на 1-3% от депозита 🎯
```

**Chart for signal post**: Style B (dark background), showing:
- Entry zone rectangle (green for long, red for short)
- Stop line (red horizontal)
- Target lines (green horizontal, one per target)
- Prediction arrow showing expected price path
- Current price label

### 5.3 News Post (`news_post.py`)
**Schedule**: Check every hour, post if 3+ star USD news found for today

**Source**: Scrape `https://www.investing.com/economic-calendar`

```python
import requests
from bs4 import BeautifulSoup
from datetime import date

def get_high_impact_news() -> list:
    """
    Fetches today's USD news with 3 stars (high impact) from investing.com
    Returns list of {time, currency, title, forecast, previous}
    Only returns USD events with 3-star impact.
    If result has 0, 1, or 2 events — return empty list (do NOT post)
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest"
    }
    # Use investing.com economic calendar API endpoint
    today = date.today().strftime("%Y-%m-%d")
    url = f"https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
    # POST request with date filter and importance=3, currency=USD
    # Parse response and filter: importance == 3 (bulls = 3), currency = "USD"
    ...
```

**Post format** (only if 3+ events):
```
Новости на сегодня 📊

15:30 USD ▶️ Индекс производственной активности от ФРБ Филадельфии (май)
           Прогноз: 17.6 | Пред.: 26.7

15:30 USD ▶️ Число первичных заявок на получение пособий по безработице  
           Прогноз: 210К | Пред.: 211К

21:00 USD ▶️ Публикация протоколов FOMC

Сделаю один сетап через час и один после выхода новостей 🎯
```

### 5.4 Filler Posts (`filler_post.py`)
**Schedule**: 1-2 per day, afternoon/evening, random time

Generate casual market commentary like:
- Reaction to recent price move
- Personal trading update  
- Market sentiment observation

**Examples from channel**:
```
Ну пока рынок стоит на месте, реакция к битку была слабенькая, поэтому 
даже если выйдем выше 78к я очень сомневаюсь что альта локально покажет 
какой-то хороший результат.

У меня открытый и лонг и шорт, если лонг короткий, то шорт более длинный, 
в принципе логично))
```

**Generation**:
```python
async def generate_filler_post(market_data: dict) -> str:
    return await claude_generate(
        system=STYLE_SYSTEM_PROMPT,
        user=f"Напиши короткий разбавляющий пост (2-4 предложения) для крипто-канала. "
             f"Текущая ситуация: BTC={market_data['btc_price']}$, "
             f"изменение за 24ч: {market_data['change_24h']}%. "
             f"Пиши как будто делишься мыслями между сетапами. Без заголовков."
    )
```

### 5.5 Ad/Promo Post (`ad_post.py`)
**Manual trigger only** via admin bot command `/ad`

**Features**:
- Admin sends `/ad` → bot shows template selector
- Admin fills in: exchange name, promo text, link, bonus amount
- Optional: attach image
- AI reformats in channel style
- Goes through approval flow like all other posts

---

## 6. ADMIN APPROVAL FLOW (CRITICAL)

Every post — **before sending to channel** — must go to admin bot for approval.

```python
# Flow:
# 1. Bot generates post (text + optional image)
# 2. Sends to ADMIN_CHAT_ID via admin bot
# 3. Shows inline keyboard:
#    [✅ Отправить] [✏️ Редактировать] [🔄 Перегенерировать] [❌ Удалить]
# 4. If "✏️ Редактировать" → admin sends new text → bot updates post → re-shows buttons
# 5. If "🔄 Перегенерировать" → generate new version → re-shows
# 6. If "✅ Отправить" → send to channel(s)
# 7. If "❌ Удалить" → discard

class ApprovalManager:
    pending: dict  # {message_id: PostObject}
    
    async def send_for_approval(self, post: PostObject):
        # Send preview to admin
        # If has image → send_photo with caption
        # If text only → send_message
        # Attach inline keyboard
        ...
    
    async def handle_callback(self, callback_query):
        action = callback_query.data  # "approve", "edit", "regen", "delete"
        post = self.pending[callback_query.message.message_id]
        
        if action == "approve":
            await channel_bot.send(post)
            await callback_query.answer("✅ Отправлено!")
        elif action == "edit":
            # Ask admin to send new text
            ...
        elif action == "regen":
            new_post = await regenerate(post)
            await self.send_for_approval(new_post)
        elif action == "delete":
            del self.pending[...]
```

---

## 7. SETTINGS & CONFIGURATION

### `config.py`
```python
ADMIN_BOT_TOKEN = ""         # Bot for admin approval
CHANNEL_BOT_TOKEN = ""       # Bot that posts to channels
ADMIN_CHAT_ID = 0            # Your Telegram user ID
ANTHROPIC_API_KEY = ""       # Claude API key

# Scheduling
MORNING_POST_TIME = "07:00"  # Local time (UTC+3)
NEWS_CHECK_INTERVAL_MIN = 60
SIGNAL_SCAN_INTERVAL_MIN = 30
FILLER_POST_TIMES = ["14:00", "20:00"]  # Random ±30 min

# Signal settings
MIN_SIGNAL_QUALITY_SCORE = 0.65  # 0-1, minimum confluence score
MAX_SIGNALS_PER_DAY = 3
```

### Per-Channel Settings (stored in `storage/settings.json`):
```json
{
  "-100123456789": {
    "channel_name": "My Trading Channel",
    "signal_mode": "smc",          // "smc" or "strategy"
    "morning_chart": "btc_chart",  // "none", "btc_chart", "custom"
    "morning_custom_symbol": "",
    "post_formatting": "with_bold", // "with_bold" or "plain"
    "language": "ru",
    "active": true,
    "intervals_to_scan": ["4h", "1d"],
    "symbols_whitelist": []         // empty = scan all USDT pairs
  }
}
```

### Admin Commands:
```
/start          — welcome + help
/addchannel     — add channel by ID
/removechannel  — remove channel
/settings       — show settings menu (inline keyboard)
/morning        — generate + send morning post now
/scan           — force market scan now
/ad             — create ad post
/status         — show bot status + scheduled jobs
/style          — toggle post formatting (bold/plain)
/mode           — toggle signal mode (SMC/Strategy)
```

---

## 8. SCHEDULER

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="Europe/Kiev")

# Morning post
scheduler.add_job(run_morning_posts, 'cron', hour=7, minute=0)

# News check
scheduler.add_job(run_news_check, 'interval', minutes=60)

# Signal scanning  
scheduler.add_job(run_signal_scan, 'interval', minutes=30)

# Filler posts (with randomization)
scheduler.add_job(maybe_filler_post, 'cron', hour=14, minute=0)
scheduler.add_job(maybe_filler_post, 'cron', hour=20, minute=0)
```

---

## 9. REQUIREMENTS.TXT

```
python-telegram-bot==20.7
anthropic==0.25.0
apscheduler==3.10.4
requests==2.31.0
beautifulsoup4==4.12.3
matplotlib==3.8.4
mplfinance==0.12.10b0
Pillow==10.3.0
numpy==1.26.4
pandas==2.2.2
python-dotenv==1.0.1
aiohttp==3.9.5
```

---

## 10. CHART GENERATION — DETAILED IMPLEMENTATION

### `chart_generator.py` — complete implementation spec:

```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
from PIL import Image
import io, random, os

def draw_candlestick(ax, candles: list, style: dict):
    """Draw OHLCV candlesticks matching the example chart style exactly"""
    for i, c in enumerate(candles):
        x = i
        o, h, l, cl = c['open'], c['high'], c['low'], c['close']
        bull = cl >= o
        
        # Wick
        ax.plot([x, x], [l, h], color=style['wick_color'], lw=0.8, zorder=3)
        
        # Body
        body_color = style['candle_bull'] if bull else style['candle_bear']
        body_h = abs(cl - o)
        body_y = min(o, cl)
        
        if style.get('hollow_bull') and bull:
            # Hollow candle (white fill with border)
            rect = mpatches.Rectangle((x - style['candle_width']/2, body_y),
                                       style['candle_width'], body_h,
                                       facecolor='white',
                                       edgecolor=style['candle_border_bull'],
                                       linewidth=0.8, zorder=4)
        else:
            rect = mpatches.Rectangle((x - style['candle_width']/2, body_y),
                                       style['candle_width'], body_h,
                                       facecolor=body_color,
                                       edgecolor=style.get('candle_border_bull' if bull else 'candle_border_bear', body_color),
                                       linewidth=0.5, zorder=4)
        ax.add_patch(rect)

def draw_zone(ax, top: float, bottom: float, x_start: float, x_end: float,
              fill_color: str, alpha: float, border_color: str = None):
    """Draw supply/demand zone rectangle"""
    rect = mpatches.Rectangle((x_start, bottom), x_end - x_start, top - bottom,
                                facecolor=fill_color, alpha=alpha,
                                edgecolor=border_color or fill_color,
                                linewidth=0.8, zorder=2)
    ax.add_patch(rect)

def draw_prediction_arrow(ax, start_x: float, start_y: float,
                           path_points: list, color: str, lw: float = 1.8):
    """
    Draw white zigzag prediction line with arrowhead at end.
    path_points: [(dx, dy), ...] relative offsets from start
    """
    xs = [start_x] + [start_x + p[0] for p in path_points]
    ys = [start_y] + [start_y + p[1] for p in path_points]
    
    # Draw line segments
    ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, zorder=6,
            solid_capstyle='round')
    
    # Draw final segment with arrow
    ax.annotate('', xy=(xs[-1], ys[-1]), xytext=(xs[-2], ys[-2]),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                                mutation_scale=12))

def add_price_label(ax, price: float, x_pos: float, bg_color: str,
                    text_color: str, fontsize: int = 10):
    """Black/green/red price label box on the right axis"""
    ax.text(x_pos, price, f' {price:,.2f} ', fontsize=fontsize,
            color=text_color, fontweight='bold',
            bbox=dict(boxstyle='square,pad=0.1', facecolor=bg_color,
                      edgecolor='none'),
            va='center', ha='left', zorder=10)

def generate_chart(symbol, interval, candle_count=60, style_name="A",
                   zones=None, bos_levels=None, horizontal_lines=None,
                   prediction_path=None, extra_labels=None,
                   poi_box=None, signal_type=None) -> bytes:
    
    style = STYLE_A if style_name == "A" else STYLE_B
    candles = get_klines(symbol, interval, candle_count)
    
    fig, ax = plt.subplots(figsize=(style['image_size'][0]/style['dpi'],
                                     style['image_size'][1]/style['dpi']),
                            dpi=style['dpi'])
    
    # Background
    if style_name == "B":
        bg_files = os.listdir("charts/backgrounds/")
        bg_img = Image.open(f"charts/backgrounds/{random.choice(bg_files)}")
        bg_img = bg_img.resize(style['image_size'])
        bg_arr = np.array(bg_img)
        ax.imshow(bg_arr, extent=[0, candle_count+10, 
                  min(c['low'] for c in candles)*0.995,
                  max(c['high'] for c in candles)*1.005],
                  aspect='auto', alpha=0.55, zorder=0)
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#00000000')
    else:
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
        ax.grid(True, color=style['grid_color'], linewidth=0.5, zorder=1)
    
    # Draw zones first (behind candles)
    if zones:
        for z in zones:
            color = style['zone_bull_fill'] if z['type'] == 'demand' else style['zone_bear_fill']
            border = style.get('zone_border_bull' if z['type']=='demand' else 'zone_border_bear')
            draw_zone(ax, z['top'], z['bottom'], 0, candle_count+8,
                      color, style['zone_alpha'], border)
    
    # Draw candles
    draw_candlestick(ax, candles, style)
    
    # BOS lines
    if bos_levels:
        for bos in bos_levels:
            bar_idx = bos.get('bar', len(candles)//2)
            ax.axhline(y=bos['price'], xmin=bar_idx/candle_count, xmax=1.0,
                      color=style.get('bos_line_color', '#00BCD4'),
                      linestyle='--', linewidth=1.0, zorder=5)
            ax.text(bar_idx, bos['price'], ' BOS', fontsize=8,
                   color=style.get('bos_label_color', '#00BCD4'), va='bottom')
    
    # Horizontal lines (targets, stops)
    if horizontal_lines:
        for hl in horizontal_lines:
            ls = '--' if hl.get('style') == 'dashed' else '-'
            ax.axhline(y=hl['price'], color=hl['color'], linestyle=ls,
                      linewidth=1.0, zorder=5)
            if hl.get('label'):
                add_price_label(ax, hl['price'], candle_count+0.5,
                               hl['color'], 'white')
    
    # POI box
    if poi_box:
        draw_zone(ax, poi_box['top'], poi_box['bottom'], 
                  len(candles)-5, candle_count+8,
                  '#607D8B', 0.3, '#90A4AE')
        ax.text(candle_count+1, (poi_box['top']+poi_box['bottom'])/2,
               poi_box.get('label', 'POI'), fontsize=8, color='#90A4AE', va='center')
    
    # Prediction path
    if prediction_path:
        last_candle = candles[-1]
        draw_prediction_arrow(ax, len(candles)-1, last_candle['close'],
                             prediction_path, 
                             style.get('prediction_arrow_color', '#555555'))
    
    # Current price label
    last_price = candles[-1]['close']
    add_price_label(ax, last_price, candle_count+0.5,
                   style['price_label_bg'], style.get('price_label_color', 'white'))
    
    # Extra labels (targets etc)
    if extra_labels:
        for lbl in extra_labels:
            add_price_label(ax, lbl['price'], candle_count+0.5,
                           lbl['bg_color'], 'white')
    
    # Watermarks (Style B)
    if style.get('watermark_tv'):
        ax.text(0.01, 0.03, '🔁 TradingView', transform=ax.transAxes,
               fontsize=10, color='#888888', alpha=0.8, va='bottom')
    if style.get('watermark_smart'):
        ax.text(0.99, 0.03, 'SMART', transform=ax.transAxes,
               fontsize=10, color='#888888', alpha=0.8, va='bottom', ha='right')
    
    # Header (Style B)
    if style.get('header_text'):
        interval_map = {"1h": "1ч", "4h": "4ч", "1d": "1д"}
        header = f"{symbol} Perpetual Contract · {interval_map.get(interval, interval)} · Bybit"
        ax.set_title(header, color='#CCCCCC', fontsize=10, pad=5, loc='left')
    
    # Axes cleanup
    ax.set_xlim(-1, candle_count + 12)
    price_range = [min(c['low'] for c in candles), max(c['high'] for c in candles)]
    ax.set_ylim(price_range[0]*0.997, price_range[1]*1.003)
    ax.yaxis.tick_right()
    ax.tick_params(colors=style.get('axis_color', '#999999'), labelsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['right'].set_color(style.get('axis_color', '#CCCCCC'))
    ax.set_xticks([])
    
    plt.tight_layout(pad=0)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=style['dpi'], bbox_inches='tight',
               facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()
```

---

## 11. ERROR HANDLING & RELIABILITY

```python
import logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s %(levelname)s %(message)s',
                    handlers=[logging.FileHandler('bot.log'), 
                              logging.StreamHandler()])

# Retry decorator for Binance API
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def get_klines_with_retry(symbol, interval, limit):
    return get_klines(symbol, interval, limit)

# Rate limiting for Claude API
# Max 5 posts/minute generated
# Cache market data for 5 minutes
```

---

## 12. DEPLOYMENT

### `.env` file:
```
ADMIN_BOT_TOKEN=xxx
CHANNEL_BOT_TOKEN=xxx  
ADMIN_CHAT_ID=123456789
ANTHROPIC_API_KEY=xxx
TIMEZONE=Europe/Kiev
```

### Run:
```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in .env
python main.py
```

### `main.py` entry point:
```python
import asyncio
from admin_bot import AdminBot
from scheduler import start_scheduler

async def main():
    admin = AdminBot()
    start_scheduler()
    await admin.run()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## IMPLEMENTATION NOTES FOR CODEX

1. **Charts are the most critical part** — spend 80% of effort getting them right. The chart must visually match the examples in prim1-prim4.PNG exactly: zones as colored rectangles behind candles, BOS dashed lines, prediction arrows as polylines with arrowheads, price labels as colored boxes on the right.

2. **Style B charts** must load real background images from `charts/backgrounds/` folder. The user will add their own car/city images there. Make the background blend naturally with charts (dark overlay, chart elements clearly visible).

3. **Approval flow cannot be skipped** — every single post type must pass through admin approval before sending to channel.

4. **Claude API calls** should be async and handle rate limits gracefully (queue if needed).

5. **The bot must work with private channels** — use channel ID (e.g. -100XXXXXXXXX), not just @username. Verify bot is admin before registering.

6. **investing.com scraping** — use their AJAX endpoint with proper headers. If scraping fails, skip the news post silently and log the error.

7. **Signal quality** — don't spam signals. Better to send 1 high-quality signal per day than 5 mediocre ones. The `MIN_SIGNAL_QUALITY_SCORE` threshold must be respected.

8. **Filler posts** — add ±20 minute random jitter to scheduled times so posts don't appear at exactly the same time every day.
