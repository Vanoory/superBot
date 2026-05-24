from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp


LOGGER = logging.getLogger(__name__)


class GroqChatClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self._semaphore = asyncio.Semaphore(1)

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.6,
        max_tokens: int = 400,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with self._semaphore:
            for attempt in range(3):
                try:
                    timeout = aiohttp.ClientTimeout(total=40)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(self.base_url, json=payload, headers=headers) as response:
                            if response.status in {429, 500, 502, 503, 504}:
                                body = await response.text()
                                raise RuntimeError(f"Groq temporary error {response.status}: {body[:200]}")
                            response.raise_for_status()
                            data: dict[str, Any] = await response.json()
                            return data["choices"][0]["message"]["content"].strip()
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("Groq request failed on attempt %s: %s", attempt + 1, exc)
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
        raise RuntimeError("Groq request failed")
