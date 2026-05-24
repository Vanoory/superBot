from __future__ import annotations

from models import PostDraft

from .formatting import render_simple_text


class FillerPostGenerator:
    def __init__(self, style_service) -> None:
        self.style_service = style_service

    async def generate(self, channel_id: str, settings: dict, *, snapshot: str, prompt: str, style_context: dict) -> PostDraft:
        fallback = (
            "Пока рынок особо никуда не спешит, реакция у альты слабенькая.\n"
            "Так что я бы лучше дождался понятного импульса, а не лез просто потому что скучно.\n"
            "Если дадут движение по битку, уже от него будем плясать."
        )
        text = await self.style_service.generate(
            prompt,
            fallback,
            style_notes=style_context.get("notes"),
            reference_examples=style_context.get("examples"),
            temperature=0.65,
            max_tokens=180,
        )
        formatted = render_simple_text(None, text, settings.get("post_formatting") == "with_bold")
        return PostDraft(
            kind="filler",
            channel_ids=[channel_id],
            text=formatted,
            metadata={"kind": "filler", "channel_id": channel_id, "snapshot": snapshot, "prompt": prompt, "style_context": style_context},
        )
