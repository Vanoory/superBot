from __future__ import annotations

import logging

from .groq_client import GroqChatClient
from .prompts import STYLE_SYSTEM_PROMPT


LOGGER = logging.getLogger(__name__)


class StyleTextService:
    def __init__(self, client: GroqChatClient | None) -> None:
        self.client = client

    def _compose_prompt(self, user_prompt: str, style_notes: str | None, reference_examples: list[str] | None) -> str:
        parts = [user_prompt]
        if style_notes:
            parts.append(f"Дополнительные заметки по стилю канала:\n{style_notes.strip()}")
        if reference_examples:
            trimmed = []
            for index, example in enumerate(reference_examples[:4], start=1):
                compact = " ".join(example.strip().split())
                trimmed.append(f"Пример {index}:\n{compact[:1200]}")
            parts.append(
                "Ниже реальные примеры постов канала. Не копируй их слово в слово, а подстройся под лексику, длину, ритм и оформление:\n\n"
                + "\n\n".join(trimmed)
            )
        return "\n\n".join(part for part in parts if part.strip())

    async def generate(
        self,
        user_prompt: str,
        fallback_text: str,
        *,
        style_notes: str | None = None,
        reference_examples: list[str] | None = None,
        temperature: float = 0.6,
        max_tokens: int = 400,
    ) -> str:
        if not self.client:
            return fallback_text
        composed_prompt = self._compose_prompt(user_prompt, style_notes, reference_examples)
        try:
            return await self.client.generate_text(
                STYLE_SYSTEM_PROMPT,
                composed_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Falling back to deterministic text after LLM error: %s", exc)
            return fallback_text
