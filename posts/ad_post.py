from __future__ import annotations

from models import PostDraft

from .formatting import render_simple_text


class AdPostGenerator:
    def __init__(self, style_service) -> None:
        self.style_service = style_service

    async def generate(
        self,
        channel_id: str,
        settings: dict,
        payload: dict,
        *,
        prompt: str,
        style_context: dict,
        image_bytes: bytes | None = None,
    ) -> PostDraft:
        fallback = (
            f"Для тех кто спрашивал где торгую, вот нормальный вариант по {payload['exchange_name']}.\n"
            f"{payload['promo_text']}\n"
            f"Ссылка: {payload['link']}"
        )
        text = await self.style_service.generate(
            prompt,
            fallback,
            style_notes=style_context.get("notes"),
            reference_examples=style_context.get("examples"),
            temperature=0.55,
            max_tokens=220,
        )
        formatted = render_simple_text(f"Реклама | {payload['exchange_name']}", text, settings.get("post_formatting") == "with_bold")
        return PostDraft(
            kind="ad",
            channel_ids=[channel_id],
            text=formatted,
            image_bytes=image_bytes,
            metadata={"kind": "ad", "channel_id": channel_id, "payload": payload, "prompt": prompt, "style_context": style_context},
        )
