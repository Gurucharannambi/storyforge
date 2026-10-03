"""
Abstract interface every LLM backend must implement.

Adding a new free/local text model to StoryForge means writing one small
class here — nothing else in the app needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LLMError(RuntimeError):
    """Raised when the configured LLM backend can't produce a response."""


class LLMBackend(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        """Return the model's raw text completion for the given prompts."""
        raise NotImplementedError

    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        """
        Return (ok, message). Used by the /api/health endpoint so the UI can
        tell the user exactly what to fix (e.g. "Ollama isn't running" or
        "model not pulled yet") instead of a raw stack trace.
        """
        raise NotImplementedError


def get_llm_backend(backend_name: Optional[str] = None, model: Optional[str] = None) -> LLMBackend:
    """Factory: returns a ready-to-use LLM backend instance."""
    from .. import config

    name = (backend_name or config.LLM_BACKEND).lower()

    if name == "ollama":
        from .ollama_client import OllamaBackend
        return OllamaBackend(model=model or config.OLLAMA_MODEL)

    if name in ("openai_compat", "openai-compatible", "openai"):
        from .openai_compat import OpenAICompatBackend
        return OpenAICompatBackend(model=model or config.OPENAI_COMPAT_MODEL)

    raise LLMError(
        f"Unknown LLM backend '{name}'. Valid options: 'ollama', 'openai_compat'."
    )
