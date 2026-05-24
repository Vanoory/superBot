from __future__ import annotations

from models import PostDraft, SignalSetup
from utils import format_price

from .formatting import render_signal_text


class SignalPostGenerator:
    def __init__(self, style_service, chart_generator) -> None:
        self.style_service = style_service
        self.chart_generator = chart_generator

    async def generate(self, channel_id: str, settings: dict, setup: SignalSetup, *, prompt: str, style_context: dict) -> PostDraft:
        fallback = (
            f"{setup.symbol} смотрю в {setup.side}, интереснее всего зона "
            f"{format_price(setup.entry_zone[0])}-{format_price(setup.entry_zone[1])}$.\n"
            "Если рынок даст нормальный добор без истерики, сетап выглядит вполне рабочим.\n"
            "Позицию все так же логичнее открывать аккуратно, без перегруза по депозиту."
        )
        description = await self.style_service.generate(
            prompt,
            fallback,
            style_notes=style_context.get("notes"),
            reference_examples=style_context.get("examples"),
            temperature=0.5,
            max_tokens=220,
        )
        text = render_signal_text(
            symbol=setup.symbol,
            side=setup.side,
            entry_zone=setup.entry_zone,
            leverage=setup.leverage,
            targets=setup.targets,
            stop=setup.stop,
            stop_to_be_rule=setup.stop_to_be_rule,
            description=description,
            with_bold=settings.get("post_formatting") == "with_bold",
        )
        image_bytes = self.chart_generator.render(setup.chart_spec) if setup.chart_spec else None
        return PostDraft(
            kind="signal",
            channel_ids=[channel_id],
            text=text,
            image_bytes=image_bytes,
            metadata={
                "kind": "signal",
                "channel_id": channel_id,
                "setup": setup.to_dict(),
                "prompt": prompt,
                "style_context": style_context,
            },
        )
