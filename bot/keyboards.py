from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def approval_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Отправить", callback_data=f"approve:{draft_id}"),
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit:{draft_id}"),
            ],
            [
                InlineKeyboardButton("🔁 Перегенерировать", callback_data=f"regen:{draft_id}"),
                InlineKeyboardButton("❌ Удалить", callback_data=f"delete:{draft_id}"),
            ],
        ]
    )


def channels_keyboard(channel_ids: list[str], prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(channel_id, callback_data=f"{prefix}:{channel_id}")] for channel_id in channel_ids]
    return InlineKeyboardMarkup(rows)


def settings_keyboard(channel_id: str, settings: dict, webapp_enabled: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(f"Режим: {settings['signal_mode']}", callback_data=f"settingsmenu:signal_mode:{channel_id}"),
            InlineKeyboardButton(f"Текст: {settings['post_formatting']}", callback_data=f"settingsmenu:post_formatting:{channel_id}"),
        ],
        [
            InlineKeyboardButton(f"Утро: {settings['morning_post_variant']}", callback_data=f"settingsmenu:morning_post_variant:{channel_id}"),
            InlineKeyboardButton(f"Активность: {'on' if settings['active'] else 'off'}", callback_data=f"settingsmenu:active:{channel_id}"),
        ],
        [
            InlineKeyboardButton(f"Утр. график: {settings['morning_chart']}", callback_data=f"settingsmenu:morning_chart:{channel_id}"),
            InlineKeyboardButton(f"Утр. ТФ: {settings['morning_chart_interval']}", callback_data=f"timeframes:morning:{channel_id}"),
        ],
        [
            InlineKeyboardButton("ТФ анализа", callback_data=f"timeframes:scan:{channel_id}"),
            InlineKeyboardButton("Время постов", callback_data=f"timesmenu:{channel_id}"),
        ],
        [
            InlineKeyboardButton("Zoom", callback_data=f"zoommenu:{channel_id}"),
            InlineKeyboardButton("Профиль", callback_data=f"profilemenu:{channel_id}"),
        ],
    ]
    if webapp_enabled:
        rows.append([InlineKeyboardButton("Галерея стилей", callback_data=f"openstyleapp:{channel_id}")])
        rows.append([InlineKeyboardButton("Примеры постов", callback_data=f"opencontentapp:{channel_id}")])
    return InlineKeyboardMarkup(rows)


def choice_keyboard(channel_id: str, field: str, options: list[tuple[str, str]], selected: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    for value, title in options:
        prefix = "✅ " if value == selected else ""
        rows.append([InlineKeyboardButton(f"{prefix}{title}", callback_data=f"set:{field}:{channel_id}:{value}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"backsettings:{channel_id}")])
    return InlineKeyboardMarkup(rows)


def timeframe_keyboard(channel_id: str, mode: str, selected: list[str], options: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for timeframe in options:
        marker = "✅ " if timeframe in selected else ""
        rows.append([InlineKeyboardButton(f"{marker}{timeframe}", callback_data=f"toggletf:{mode}:{channel_id}:{timeframe}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"backsettings:{channel_id}")])
    return InlineKeyboardMarkup(rows)


def zoom_keyboard(channel_id: str, settings: dict) -> InlineKeyboardMarkup:
    rows = []
    for slot, label in [("signal", "Signal"), ("smc", "SMC"), ("morning", "Morning")]:
        current = settings.get(f"chart_zoom_{slot}", "standard")
        rows.append([InlineKeyboardButton(f"{label}: {current}", callback_data=f"zoomslot:{slot}:{channel_id}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"backsettings:{channel_id}")])
    return InlineKeyboardMarkup(rows)


def zoom_choice_keyboard(channel_id: str, slot: str, selected: str) -> InlineKeyboardMarkup:
    return choice_keyboard(
        channel_id,
        f"chart_zoom_{slot}",
        [("tight", "Впритык"), ("standard", "Стандарт"), ("wide", "Отдалённый")],
        selected=selected,
    )


def times_keyboard(channel_id: str, settings: dict) -> InlineKeyboardMarkup:
    filler_times = settings.get("filler_post_times", ["14:00", "20:00"])
    rows = [
        [InlineKeyboardButton(f"Утро: {settings.get('morning_post_time', '09:00')}", callback_data=f"settime:morning_post_time:{channel_id}")],
        [InlineKeyboardButton(f"Filler 1: {filler_times[0] if filler_times else 'off'}", callback_data=f"settime:filler_0:{channel_id}")],
        [InlineKeyboardButton(f"Filler 2: {filler_times[1] if len(filler_times) > 1 else 'off'}", callback_data=f"settime:filler_1:{channel_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"backsettings:{channel_id}")],
    ]
    return InlineKeyboardMarkup(rows)


def webapp_open_keyboard(url: str, title: str = "Открыть приложение") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(title, web_app=WebAppInfo(url=url))]])
