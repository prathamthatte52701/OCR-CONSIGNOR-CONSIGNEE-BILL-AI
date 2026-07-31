"""AI provider abstraction — swap the LLM backend without touching pipeline/prompt code."""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def extract(self, system_prompt: str, user_prompt: str) -> str:
        """Returns the raw text response (expected to be JSON)."""
