from __future__ import annotations

from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from charts.styles import CHART_THEME_PRESETS
from models import ChannelRecord, PostDraft
from utils import normalize_hhmm
from .keyboards import (
    channels_keyboard,
    choice_keyboard,
    settings_keyboard,
    timeframe_keyboard,
    times_keyboard,
    webapp_open_keyboard,
    zoom_choice_keyboard,
    zoom_keyboard,
)


LOGGER = logging.getLogger(__name__)
SCAN_TIMEFRAME_OPTIONS = ["15m", "1h", "4h", "1d"]
MORNING_TIMEFRAME_OPTIONS = ["15m", "1h", "4h", "1d"]


class BotHandlers:
    def __init__(
        self,
        *,
        config,
        asset_manager,
        channel_repository,
        settings_repository,
        pending_repository,
        ledger_repository,
        schedule_state_repository,
        post_service,
        approval_manager,
        scheduler,
    ) -> None:
        self.config = config
        self.asset_manager = asset_manager
        self.channel_repository = channel_repository
        self.settings_repository = settings_repository
        self.pending_repository = pending_repository
        self.ledger_repository = ledger_repository
        self.schedule_state_repository = schedule_state_repository
        self.post_service = post_service
        self.approval_manager = approval_manager
        self.scheduler = scheduler
        self.bot_user_id: int | None = None
        self.awaiting_ad: dict[int, dict] = {}
        self.awaiting_custom_input: dict[int, dict] = {}

    async def capture_bot_identity(self, application) -> None:
        me = await application.bot.get_me()
        self.bot_user_id = me.id
        await application.bot.set_my_commands(
            [
                BotCommand("start", "help"),
                BotCommand("addchannel", "register a channel"),
                BotCommand("removechannel", "remove a channel"),
                BotCommand("profile", "show channel profile"),
                BotCommand("settings", "open channel settings"),
                BotCommand("morning", "generate morning post"),
                BotCommand("morningvariant", "select morning post variant"),
                BotCommand("scan", "scan for signal"),
                BotCommand("chartstyle", "open chart style gallery"),
                BotCommand("setstylenote", "set style notes"),
                BotCommand("addstyleexample", "save example post"),
                BotCommand("addchartbg", "upload chart background"),
                BotCommand("addchartref", "upload chart reference"),
                BotCommand("timeframes", "set analysis timeframes"),
                BotCommand("posttimes", "set post times"),
                BotCommand("zoom", "set chart zoom"),
                BotCommand("ad", "create ad post"),
                BotCommand("status", "show bot status"),
                BotCommand("style", "select text formatting"),
                BotCommand("mode", "select signal mode"),
            ]
        )

    def _is_admin(self, update: Update) -> bool:
        return bool(update.effective_user and update.effective_user.id == self.config.admin_chat_id)

    async def _reject_non_admin(self, update: Update) -> bool:
        if self._is_admin(update):
            return False
        if update.effective_message:
            await update.effective_message.reply_text("Этот бот принимает команды только от администратора.")
        return True

    @staticmethod
    def _normalize_channel_ref(value: str) -> str:
        return value.strip()

    @staticmethod
    def _coerce_chat_lookup(value: str) -> int | str:
        normalized = value.strip()
        if normalized.startswith("-") and normalized[1:].isdigit():
            return int(normalized)
        return normalized

    def _resolve_target_channels(self, args: list[str]) -> list[str]:
        if args and (args[0].startswith("-") or args[0].startswith("@")):
            return [self._normalize_channel_ref(args[0])]
        active = self.channel_repository.list_channels(active_only=True)
        return [record.channel_id for record in active]

    def _single_channel_or_default(self, channel_arg: str | None = None) -> str | None:
        if channel_arg:
            return self._normalize_channel_ref(channel_arg)
        channels = self.channel_repository.list_channels(active_only=False)
        if len(channels) == 1:
            return channels[0].channel_id
        return channels[0].channel_id if channels else None

    def _current_local(self) -> datetime:
        return datetime.now(ZoneInfo(self.config.timezone))

    def _webapp_url(self, app_name: str, channel_id: str) -> str | None:
        if not self.config.webapp_base_url:
            return None
        base = self.config.webapp_base_url.rstrip("/")
        return f"{base}/{app_name}/{channel_id}"

    async def _send_settings_overview(self, message, channel_id: str) -> None:
        settings = self.settings_repository.get(channel_id)
        await message.reply_text(
            f"Настройки {channel_id}",
            reply_markup=settings_keyboard(channel_id, settings, webapp_enabled=bool(self.config.webapp_base_url)),
        )

    def _profile_lines(self, channel_id: str) -> list[str]:
        settings = self.settings_repository.get(channel_id)
        assets = self.asset_manager.profile_summary(channel_id)
        notes = settings.get("writing_style_notes", "").strip()
        notes_preview = notes[:140] + ("..." if len(notes) > 140 else "")
        return [
            f"Профиль канала {channel_id}",
            f"• morning variant: {settings.get('morning_post_variant', 'brief')}",
            f"• morning time: {settings.get('morning_post_time', '09:00')}",
            f"• morning TF: {settings.get('morning_chart_interval', '4h')}",
            f"• scan TF: {', '.join(settings.get('intervals_to_scan', []))}",
            f"• signal preset: {settings.get('chart_style_signal_preset')}",
            f"• smc preset: {settings.get('chart_style_smc_preset')}",
            f"• morning preset: {settings.get('chart_style_morning_preset')}",
            f"• zooms: signal={settings.get('chart_zoom_signal')} | smc={settings.get('chart_zoom_smc')} | morning={settings.get('chart_zoom_morning')}",
            f"• text examples: {assets['text_samples']}",
            f"• chart refs: {assets['chart_refs']}",
            f"• chart backgrounds: {assets['backgrounds']}",
            f"• style notes: {notes_preview or 'нет'}",
        ]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channels = self.channel_repository.list_channels(active_only=False)
        text = [
            "Бот готов.",
            "",
            "Основные команды:",
            "/addchannel <id|@username>",
            "/settings",
            "/profile [channel]",
            "/morning [channel] [brief|analysis]",
            "/scan [channel]",
            "/chartstyle [channel]",
            "/timeframes [channel]",
            "/posttimes [channel]",
            "/zoom [channel]",
        ]
        if channels:
            text.extend(["", "Каналы:", *[f"• {item.channel_id} ({item.channel_name})" for item in channels]])
        await update.effective_message.reply_text("\n".join(text))

    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        if not context.args:
            await update.effective_message.reply_text("Использование: /addchannel <id|@username>")
            return
        if self.bot_user_id is None:
            self.bot_user_id = (await context.bot.get_me()).id

        channel_ref = self._normalize_channel_ref(context.args[0])
        lookup_value = self._coerce_chat_lookup(channel_ref)

        try:
            chat = await context.bot.get_chat(lookup_value)
        except BadRequest as exc:
            LOGGER.warning("Channel lookup failed for %s: %s", channel_ref, exc)
            await update.effective_message.reply_text(
                "Не удалось найти канал.\n\n"
                "Проверь по шагам:\n"
                "1. Бот уже добавлен в канал.\n"
                "2. Боту выданы права администратора.\n"
                "3. Для приватного канала используй id вида `-100...`.\n"
                "4. Если используешь `@username`, проверь что он введён без ошибок.",
                parse_mode="Markdown",
            )
            return
        except Forbidden as exc:
            LOGGER.warning("Channel lookup forbidden for %s: %s", channel_ref, exc)
            await update.effective_message.reply_text(
                "Telegram не дал боту доступ к каналу. Обычно это значит, что бот ещё не добавлен в канал."
            )
            return

        try:
            member = await context.bot.get_chat_member(chat.id, self.bot_user_id)
        except (BadRequest, Forbidden) as exc:
            LOGGER.warning("Failed to inspect bot membership for %s: %s", channel_ref, exc)
            await update.effective_message.reply_text(
                "Канал найден, но я не смог проверить права бота. Убедись, что бот добавлен в канал и назначен администратором."
            )
            return

        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            await update.effective_message.reply_text("Сначала дай боту права администратора в канале.")
            return

        record = ChannelRecord(channel_id=str(chat.id), channel_name=chat.title or chat.username or str(chat.id))
        self.channel_repository.add(record)
        self.asset_manager.ensure_channel_dirs(record.channel_id)
        self.settings_repository.update(record.channel_id, {"channel_name": record.channel_name})
        await update.effective_message.reply_text(f"Канал добавлен: {record.channel_name} ({record.channel_id})")

    async def remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        if not context.args:
            await update.effective_message.reply_text("Использование: /removechannel <id|@username>")
            return
        channel_id = self._normalize_channel_ref(context.args[0])
        removed = self.channel_repository.remove(channel_id)
        self.settings_repository.remove(channel_id)
        self.asset_manager.remove_channel_assets(channel_id)
        await update.effective_message.reply_text("Канал удален." if removed else "Такого канала в списке нет.")

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Сначала добавь канал через /addchannel.")
            return
        await update.effective_message.reply_text("\n".join(self._profile_lines(channel_id)))

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channels = self.channel_repository.list_channels(active_only=False)
        if not channels:
            await update.effective_message.reply_text("Сначала добавь канал через /addchannel.")
            return
        if len(channels) == 1:
            await self._send_settings_overview(update.effective_message, channels[0].channel_id)
            return
        await update.effective_message.reply_text(
            "Выбери канал для настроек:",
            reply_markup=channels_keyboard([item.channel_id for item in channels], "settingspick"),
        )

    async def manual_morning(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        variant = None
        args = list(context.args)
        if args and args[-1] in {"brief", "analysis"}:
            variant = args.pop()
        target_channels = self._resolve_target_channels(args)
        count = 0
        for channel_id in target_channels:
            draft = await self.post_service.generate_morning_post(channel_id, variant=variant)
            await self.approval_manager.send_for_approval(draft)
            count += 1
        await update.effective_message.reply_text(f"Утренние посты отправлены на согласование: {count}")

    async def morning_variant(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        args = list(context.args)
        channel_id = self._single_channel_or_default(args[0] if args and (args[0].startswith("-") or args[0].startswith("@")) else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        if args and args[-1] in {"brief", "analysis"}:
            variant = args[-1]
            self.settings_repository.update(channel_id, {"morning_post_variant": variant})
            await update.effective_message.reply_text(f"{channel_id}: morning_post_variant = {variant}")
            return
        await update.effective_message.reply_text(
            "Выбери вариант утреннего поста:",
            reply_markup=choice_keyboard(
                channel_id,
                "morning_post_variant",
                [("brief", "Обычный"), ("analysis", "С разбором")],
                selected=self.settings_repository.get(channel_id)["morning_post_variant"],
            ),
        )

    async def manual_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        count = await self.generate_signal_for_channels(self._resolve_target_channels(list(context.args)))
        await update.effective_message.reply_text(f"Сигналы отправлены на согласование: {count}")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channels = self.channel_repository.list_channels(active_only=False)
        pending = len(self.pending_repository.list())
        jobs = self.scheduler.describe_jobs()
        lines = [
            f"Каналов: {len(channels)}",
            f"Pending approval: {pending}",
            "Jobs:",
            *[f"• {job}" for job in jobs],
        ]
        for channel in channels:
            counts = self.ledger_repository.get_counts(channel.channel_id)
            lines.append(f"• {channel.channel_name}: reserved={counts['reserved']}, published={counts['published']}")
        await update.effective_message.reply_text("\n".join(lines))

    async def toggle_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        settings = self.settings_repository.get(channel_id)
        await update.effective_message.reply_text(
            "Выбери формат текста:",
            reply_markup=choice_keyboard(
                channel_id,
                "post_formatting",
                [("with_bold", "С выделением"), ("plain", "Без выделения")],
                selected=settings["post_formatting"],
            ),
        )

    async def toggle_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        settings = self.settings_repository.get(channel_id)
        await update.effective_message.reply_text(
            "Выбери режим сигналов:",
            reply_markup=choice_keyboard(
                channel_id,
                "signal_mode",
                [("smc", "SMC"), ("strategy", "Strategy")],
                selected=settings["signal_mode"],
            ),
        )

    async def chart_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        args = list(context.args)
        channel_id = self._single_channel_or_default(args[0] if args and (args[0].startswith("-") or args[0].startswith("@")) else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        if len(args) >= 2 and args[-2] in {"signal", "smc", "morning"}:
            slot = args[-2]
            preset = args[-1]
            field = {
                "signal": "chart_style_signal_preset",
                "smc": "chart_style_smc_preset",
                "morning": "chart_style_morning_preset",
            }[slot]
            self.settings_repository.update(channel_id, {field: preset})
            await update.effective_message.reply_text(f"{channel_id}: {field} = {preset}")
            return

        url = self._webapp_url("style-gallery", channel_id)
        if url:
            await update.effective_message.reply_text(
                "Открой галерею стилей графика:",
                reply_markup=webapp_open_keyboard(url, title="Открыть галерею стилей"),
            )
            return

        presets = ", ".join(sorted(CHART_THEME_PRESETS.keys()))
        await update.effective_message.reply_text(
            "Для web app укажи `WEBAPP_BASE_URL` в `.env`.\n"
            f"Пока можно выбрать вручную: /chartstyle {channel_id} <signal|smc|morning> <preset>\n"
            f"Пресеты: {presets}"
        )

    async def timeframes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        settings = self.settings_repository.get(channel_id)
        await update.effective_message.reply_text(
            "Выбери ТФ для поиска сигналов:",
            reply_markup=timeframe_keyboard(channel_id, "scan", settings.get("intervals_to_scan", []), SCAN_TIMEFRAME_OPTIONS),
        )

    async def posttimes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        settings = self.settings_repository.get(channel_id)
        await update.effective_message.reply_text(
            "Настрой время постов:",
            reply_markup=times_keyboard(channel_id, settings),
        )

    async def zoom(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        settings = self.settings_repository.get(channel_id)
        await update.effective_message.reply_text(
            "Выбери zoom для графиков:",
            reply_markup=zoom_keyboard(channel_id, settings),
        )

    async def set_style_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args and (context.args[0].startswith("-") or context.args[0].startswith("@")) else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        args = list(context.args)
        if args and channel_id == args[0]:
            args = args[1:]
        note_text = " ".join(args).strip()
        if note_text:
            self.settings_repository.update(channel_id, {"writing_style_notes": note_text})
            await update.effective_message.reply_text("Заметки по стилю обновлены.")
            return
        self.awaiting_custom_input[update.effective_user.id] = {"mode": "style_note", "channel_id": channel_id}
        await update.effective_message.reply_text("Отправь следующим сообщением заметки по стилю канала.")

    async def add_style_example(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        url = self._webapp_url("content-studio", channel_id)
        if url:
            await update.effective_message.reply_text(
                "Открой studio для загрузки примеров постов:",
                reply_markup=webapp_open_keyboard(url, title="Открыть studio примеров"),
            )
            return
        self.awaiting_custom_input[update.effective_user.id] = {"mode": "style_example", "channel_id": channel_id}
        await update.effective_message.reply_text("Отправь следующим сообщением пример поста для этого канала.")

    async def add_chart_background(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        self.awaiting_custom_input[update.effective_user.id] = {"mode": "chart_background", "channel_id": channel_id}
        await update.effective_message.reply_text("Отправь следующим сообщением картинку-фон для графиков этого канала.")

    async def add_chart_reference(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        channel_id = self._single_channel_or_default(context.args[0] if context.args else None)
        if not channel_id:
            await update.effective_message.reply_text("Не удалось определить канал.")
            return
        self.awaiting_custom_input[update.effective_user.id] = {"mode": "chart_reference", "channel_id": channel_id}
        await update.effective_message.reply_text("Отправь следующим сообщением пример графика-референса.")

    async def ad_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        target_channels = self._resolve_target_channels(list(context.args))
        if not target_channels:
            await update.effective_message.reply_text("Сначала добавь канал.")
            return
        self.awaiting_ad[update.effective_user.id] = {"channel_id": target_channels[0]}
        await update.effective_message.reply_text(
            "Отправь рекламный пост текстом или фото с подписью в формате:\n"
            "exchange | promo text | link | bonus(optional)"
        )

    async def handle_admin_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_non_admin(update):
            return
        if not update.effective_message:
            return

        edit_draft_id = self.approval_manager.pop_edit_mode(update.effective_user.id)
        if edit_draft_id:
            draft = self.pending_repository.get(edit_draft_id)
            if not draft:
                await update.effective_message.reply_text("Черновик для редактирования уже не найден.")
                return
            text = update.effective_message.text_html or update.effective_message.caption_html or draft.text
            updated = PostDraft(
                id=draft.id,
                kind=draft.kind,
                channel_ids=draft.channel_ids,
                text=text,
                metadata=draft.metadata,
                image_bytes=draft.image_bytes,
                parse_mode=draft.parse_mode,
                created_at=draft.created_at,
            )
            self.pending_repository.save(updated)
            await update.effective_message.reply_text("Текст обновил, отправляю новый preview.")
            await self.approval_manager.send_for_approval(updated)
            return

        custom_state = self.awaiting_custom_input.pop(update.effective_user.id, None)
        if custom_state:
            channel_id = custom_state["channel_id"]
            mode = custom_state["mode"]

            if mode in {"style_example", "style_note"}:
                text = update.effective_message.text or update.effective_message.caption or ""
                if not text.strip():
                    self.awaiting_custom_input[update.effective_user.id] = custom_state
                    await update.effective_message.reply_text("Нужен текст сообщением или подписью.")
                    return
                if mode == "style_example":
                    self.asset_manager.save_text_sample(channel_id, text)
                    await update.effective_message.reply_text("Пример поста сохранён в профиль канала.")
                else:
                    self.settings_repository.update(channel_id, {"writing_style_notes": text.strip()})
                    await update.effective_message.reply_text("Заметки по стилю сохранены.")
                return

            if mode in {"chart_background", "chart_reference"}:
                if not update.effective_message.photo:
                    self.awaiting_custom_input[update.effective_user.id] = custom_state
                    await update.effective_message.reply_text("Нужно отправить изображение.")
                    return
                file = await update.effective_message.photo[-1].get_file()
                image_bytes = bytes(await file.download_as_bytearray())
                bucket = "backgrounds" if mode == "chart_background" else "chart_refs"
                self.asset_manager.save_image(channel_id, image_bytes, bucket=bucket, suffix=".jpg")
                await update.effective_message.reply_text(
                    "Фон для графиков сохранён." if mode == "chart_background" else "График-референс сохранён в профиль канала."
                )
                return

            if mode == "time_input":
                raw = (update.effective_message.text or "").strip().lower()
                field = custom_state["field"]
                if raw != "off":
                    try:
                        raw = normalize_hhmm(raw)
                    except Exception:  # noqa: BLE001
                        self.awaiting_custom_input[update.effective_user.id] = custom_state
                        await update.effective_message.reply_text("Нужен формат `HH:MM`, например `09:30`, или `off`.")
                        return
                settings = self.settings_repository.get(channel_id)
                if field == "morning_post_time":
                    self.settings_repository.update(channel_id, {"morning_post_time": raw})
                else:
                    filler_times = list(settings.get("filler_post_times", ["14:00", "20:00"]))
                    index = int(field.split("_")[1])
                    while len(filler_times) <= index:
                        filler_times.append("off")
                    filler_times[index] = raw
                    self.settings_repository.update(channel_id, {"filler_post_times": filler_times})
                await update.effective_message.reply_text("Время обновлено.")
                return

        ad_state = self.awaiting_ad.pop(update.effective_user.id, None)
        if ad_state:
            raw = update.effective_message.caption or update.effective_message.text or ""
            parts = [part.strip() for part in raw.split("|")]
            if len(parts) < 3:
                self.awaiting_ad[update.effective_user.id] = ad_state
                await update.effective_message.reply_text("Нужен формат: exchange | promo text | link | bonus(optional)")
                return
            payload = {
                "exchange_name": parts[0],
                "promo_text": parts[1],
                "link": parts[2],
                "bonus": parts[3] if len(parts) > 3 else "",
            }
            image_bytes = None
            if update.effective_message.photo:
                file = await update.effective_message.photo[-1].get_file()
                image_bytes = bytes(await file.download_as_bytearray())
            draft = await self.post_service.generate_ad_post(ad_state["channel_id"], payload, image_bytes=image_bytes)
            await self.approval_manager.send_for_approval(draft)
            await update.effective_message.reply_text("Рекламный пост ушел на согласование.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not self._is_admin(update):
            return
        await query.answer()
        payload = query.data or ""

        if payload.startswith("settingspick:"):
            channel_id = payload.split(":", 1)[1]
            await self._send_settings_overview(query.message, channel_id)
            return

        if payload.startswith("backsettings:"):
            channel_id = payload.split(":", 1)[1]
            await query.message.reply_text(
                f"Настройки {channel_id}",
                reply_markup=settings_keyboard(channel_id, self.settings_repository.get(channel_id), webapp_enabled=bool(self.config.webapp_base_url)),
            )
            return

        if payload.startswith("profilemenu:"):
            channel_id = payload.split(":", 1)[1]
            await query.message.reply_text("\n".join(self._profile_lines(channel_id)))
            return

        if payload.startswith("openstyleapp:"):
            channel_id = payload.split(":", 1)[1]
            url = self._webapp_url("style-gallery", channel_id)
            if not url:
                await query.message.reply_text("WEBAPP_BASE_URL пока не настроен.")
                return
            await query.message.reply_text("Открой галерею:", reply_markup=webapp_open_keyboard(url, "Открыть галерею стилей"))
            return

        if payload.startswith("opencontentapp:"):
            channel_id = payload.split(":", 1)[1]
            url = self._webapp_url("content-studio", channel_id)
            if not url:
                await query.message.reply_text("WEBAPP_BASE_URL пока не настроен.")
                return
            await query.message.reply_text("Открой studio:", reply_markup=webapp_open_keyboard(url, "Открыть studio примеров"))
            return

        if payload.startswith("settingsmenu:"):
            _, field, channel_id = payload.split(":", 2)
            settings = self.settings_repository.get(channel_id)
            if field == "signal_mode":
                markup = choice_keyboard(channel_id, "signal_mode", [("smc", "SMC"), ("strategy", "Strategy")], selected=settings["signal_mode"])
                await query.message.reply_text("Выбери режим сигналов:", reply_markup=markup)
                return
            if field == "post_formatting":
                markup = choice_keyboard(channel_id, "post_formatting", [("with_bold", "С выделением"), ("plain", "Без выделения")], selected=settings["post_formatting"])
                await query.message.reply_text("Выбери формат текста:", reply_markup=markup)
                return
            if field == "morning_post_variant":
                markup = choice_keyboard(channel_id, "morning_post_variant", [("brief", "Обычный"), ("analysis", "С разбором")], selected=settings["morning_post_variant"])
                await query.message.reply_text("Выбери вариант утреннего поста:", reply_markup=markup)
                return
            if field == "active":
                markup = choice_keyboard(channel_id, "active", [("true", "Включить"), ("false", "Выключить")], selected="true" if settings["active"] else "false")
                await query.message.reply_text("Включить или выключить канал?", reply_markup=markup)
                return
            if field == "morning_chart":
                markup = choice_keyboard(channel_id, "morning_chart", [("btc_chart", "BTC график"), ("custom", "Своя монета"), ("none", "Без графика")], selected=settings["morning_chart"])
                await query.message.reply_text("Выбери вариант утреннего графика:", reply_markup=markup)
                return

        if payload.startswith("set:"):
            _, field, channel_id, value = payload.split(":", 3)
            patch = {field: {"true": True, "false": False}.get(value, value)}
            self.settings_repository.update(channel_id, patch)
            await query.message.reply_text(f"{field} обновлено: {patch[field]}")
            await self._send_settings_overview(query.message, channel_id)
            return

        if payload.startswith("timeframes:"):
            _, mode, channel_id = payload.split(":", 2)
            settings = self.settings_repository.get(channel_id)
            if mode == "scan":
                markup = timeframe_keyboard(channel_id, "scan", settings.get("intervals_to_scan", []), SCAN_TIMEFRAME_OPTIONS)
                await query.message.reply_text("ТФ для анализа:", reply_markup=markup)
            else:
                markup = choice_keyboard(
                    channel_id,
                    "morning_chart_interval",
                    [(item, item) for item in MORNING_TIMEFRAME_OPTIONS],
                    selected=settings.get("morning_chart_interval", "4h"),
                )
                await query.message.reply_text("ТФ для утреннего графика:", reply_markup=markup)
            return

        if payload.startswith("toggletf:"):
            _, mode, channel_id, timeframe = payload.split(":", 3)
            settings = self.settings_repository.get(channel_id)
            selected = list(settings.get("intervals_to_scan", []))
            if timeframe in selected:
                selected.remove(timeframe)
            else:
                selected.append(timeframe)
            if not selected:
                selected = ["4h"]
            selected = [tf for tf in SCAN_TIMEFRAME_OPTIONS if tf in selected]
            self.settings_repository.update(channel_id, {"intervals_to_scan": selected})
            await query.message.reply_text(
                "ТФ обновлены:",
                reply_markup=timeframe_keyboard(channel_id, mode, selected, SCAN_TIMEFRAME_OPTIONS),
            )
            return

        if payload.startswith("timesmenu:"):
            channel_id = payload.split(":", 1)[1]
            await query.message.reply_text("Настрой время постов:", reply_markup=times_keyboard(channel_id, self.settings_repository.get(channel_id)))
            return

        if payload.startswith("settime:"):
            _, field, channel_id = payload.split(":", 2)
            self.awaiting_custom_input[update.effective_user.id] = {"mode": "time_input", "channel_id": channel_id, "field": field}
            await query.message.reply_text("Отправь временем `HH:MM` или `off` следующим сообщением.")
            return

        if payload.startswith("zoommenu:"):
            channel_id = payload.split(":", 1)[1]
            await query.message.reply_text("Выбери zoom:", reply_markup=zoom_keyboard(channel_id, self.settings_repository.get(channel_id)))
            return

        if payload.startswith("zoomslot:"):
            _, slot, channel_id = payload.split(":", 2)
            settings = self.settings_repository.get(channel_id)
            await query.message.reply_text(
                f"Выбери zoom для {slot}:",
                reply_markup=zoom_choice_keyboard(channel_id, slot, settings.get(f"chart_zoom_{slot}", "standard")),
            )
            return

        if ":" not in payload:
            return
        action, draft_id = payload.split(":", 1)
        draft = self.pending_repository.get(draft_id)
        if not draft:
            await query.message.reply_text("Черновик уже не найден.")
            return

        if action == "approve":
            await self.approval_manager.publish(draft)
            self.pending_repository.delete(draft_id)
            await query.message.reply_text("Пост отправлен в канал.")
            return

        if action == "edit":
            self.approval_manager.set_edit_mode(update.effective_user.id, draft_id)
            await query.message.reply_text("Отправь новый текст следующим сообщением.")
            return

        if action == "regen":
            regenerated = await self.post_service.regenerate_post(draft)
            if regenerated is None:
                await query.message.reply_text("Не получилось перегенерировать этот тип поста.")
                return
            self.pending_repository.delete(draft_id)
            await self.approval_manager.send_for_approval(regenerated)
            await query.message.reply_text("Новая версия уже у тебя в личке.")
            return

        if action == "delete":
            self.approval_manager.delete_pending(draft_id, release_signal_slot=True)
            await query.message.reply_text("Черновик удален.")

    async def run_schedule_tick(self) -> int:
        now = self._current_local()
        hhmm = now.strftime("%H:%M")
        day_key = now.strftime("%Y-%m-%d")
        created = 0
        for record in self.channel_repository.list_channels(active_only=True):
            settings = self.settings_repository.get(record.channel_id)
            if not settings.get("active", True):
                continue

            morning_time = settings.get("morning_post_time", "09:00")
            if morning_time != "off" and morning_time == hhmm:
                slot = f"morning:{morning_time}"
                if not self.schedule_state_repository.is_slot_consumed(record.channel_id, slot, day_key):
                    draft = await self.post_service.generate_morning_post(record.channel_id)
                    await self.approval_manager.send_for_approval(draft)
                    self.schedule_state_repository.mark_slot(record.channel_id, slot, day_key)
                    created += 1

            for index, filler_time in enumerate(settings.get("filler_post_times", [])):
                if filler_time == "off" or filler_time != hhmm:
                    continue
                slot = f"filler:{index}:{filler_time}"
                if self.schedule_state_repository.is_slot_consumed(record.channel_id, slot, day_key):
                    continue
                draft = await self.post_service.generate_filler_post(record.channel_id)
                await self.approval_manager.send_for_approval(draft)
                self.schedule_state_repository.mark_slot(record.channel_id, slot, day_key)
                created += 1
        return created

    async def generate_morning_for_active_channels(self) -> int:
        count = 0
        for record in self.channel_repository.list_channels(active_only=True):
            draft = await self.post_service.generate_morning_post(record.channel_id)
            await self.approval_manager.send_for_approval(draft)
            count += 1
        return count

    async def generate_news_for_active_channels(self) -> int:
        count = 0
        for record in self.channel_repository.list_channels(active_only=True):
            draft = await self.post_service.generate_news_post(record.channel_id)
            if not draft:
                continue
            await self.approval_manager.send_for_approval(draft)
            count += 1
        return count

    async def generate_signal_for_channels(self, channel_ids: list[str]) -> int:
        count = 0
        for channel_id in channel_ids:
            settings = self.settings_repository.get(channel_id)
            limit = int(settings.get("max_signals_per_day") or self.config.max_signals_per_day)
            if not self.ledger_repository.can_queue(channel_id, limit):
                continue
            draft = await self.post_service.generate_signal_post(channel_id)
            if not draft:
                continue
            self.ledger_repository.reserve(channel_id)
            await self.approval_manager.send_for_approval(draft)
            count += 1
        return count

    async def generate_signal_for_active_channels(self) -> int:
        channels = [record.channel_id for record in self.channel_repository.list_channels(active_only=True)]
        return await self.generate_signal_for_channels(channels)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        LOGGER.exception("Unhandled bot error", exc_info=context.error)
        if isinstance(context.error, TelegramError):
            message = "Telegram вернул ошибку при обработке команды. Проверь права бота, channel id и повтори попытку."
        else:
            message = "Во время обработки команды произошла ошибка. Я записал её в лог."
        target_message = getattr(update, "effective_message", None) if update else None
        if target_message:
            try:
                await target_message.reply_text(message)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to send error message to chat")
