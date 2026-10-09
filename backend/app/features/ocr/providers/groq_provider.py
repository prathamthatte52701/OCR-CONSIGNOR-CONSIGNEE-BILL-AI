"""Groq provider — round-robins across multiple API keys, retries only on retryable failures."""

import asyncio
import itertools

from groq import APIStatusError, AsyncGroq

from app.core.config import settings
from app.features.ocr.providers.base import AIProvider

RETRYABLE_STATUS_CODES = {401, 403, 429, 500, 502, 503, 504}
REQUEST_TIMEOUT_SECONDS = 60
MAX_COMPLETION_TOKENS = 2048  # reasoning models spend part of this budget before the JSON


def _model_options(model: str) -> dict[str, str]:
    """Per-model request options. The gpt-oss models are reasoning models: low effort keeps the
    answer fast and leaves the token budget for the JSON itself."""
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    return {}


class GroqProvider(AIProvider):
    def __init__(self) -> None:
        self._keys = settings.groq_api_keys
        if not self._keys:
            raise RuntimeError("No GROQ_API_KEYS configured.")
        self._key_cycle = itertools.cycle(self._keys)

    async def extract(self, system_prompt: str, user_prompt: str) -> str:
        last_error: Exception | None = None
        for _ in range(len(self._keys)):
            api_key = next(self._key_cycle)
            client = AsyncGroq(api_key=api_key)
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=settings.groq_model,
                        temperature=0.1,
                        max_completion_tokens=MAX_COMPLETION_TOKENS,
                        **_model_options(settings.groq_model),
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise RuntimeError("Groq returned an empty response.")
                return content
            except APIStatusError as exc:
                last_error = exc
                if exc.status_code in RETRYABLE_STATUS_CODES:
                    continue
                raise
            except TimeoutError as exc:
                last_error = exc
                continue

        raise RuntimeError(f"All Groq API keys exhausted. Last error: {last_error}")
