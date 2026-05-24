from __future__ import annotations

from models import NewsEvent, PostDraft

from .formatting import render_news_text


class NewsPostGenerator:
    def __init__(self, style_service) -> None:
        self.style_service = style_service

    async def generate(self, channel_id: str, settings: dict, events: list[NewsEvent], *, prompt: str, style_context: dict) -> PostDraft:
        fallback = "Сделаю один сетап ближе к новостям и после реакции рынка уже доберу, если все красиво сложится."
        closing_line = await self.style_service.generate(
            prompt,
            fallback,
            style_notes=style_context.get("notes"),
            reference_examples=style_context.get("examples"),
            temperature=0.5,
            max_tokens=80,
        )
        lines = []
        for event in events:
            lines.append(f"{event.time} USD ▶️ {event.title}")
            details = []
            if event.forecast:
                details.append(f"Прогноз: {event.forecast}")
            if event.previous:
                details.append(f"Пред.: {event.previous}")
            if details:
                lines.append("    " + " | ".join(details))
        text = render_news_text(lines, closing_line, settings.get("post_formatting") == "with_bold")
        return PostDraft(
            kind="news",
            channel_ids=[channel_id],
            text=text,
            metadata={
                "kind": "news",
                "channel_id": channel_id,
                "events": [event.to_dict() for event in events],
                "prompt": prompt,
                "style_context": style_context,
            },
        )
