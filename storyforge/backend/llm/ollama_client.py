from __future__ import annotations

import requests

from .. import config
from .base import LLMBackend, LLMError


class OllamaBackend(LLMBackend):
    """
    Talks to a local Ollama server (https://ollama.com), the easiest way to
    run open-weight LLMs (Llama 3.1, Qwen2.5, Mistral, GLM4, DeepSeek, etc.)
    for free with a single `ollama pull <model>` command. 100% offline.
    """

    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or config.OLLAMA_MODEL
        self.host = (host or config.OLLAMA_HOST).rstrip("/")

    def check_available(self) -> tuple[bool, str]:
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return False, (
                f"Can't reach Ollama at {self.host}. Install it from "
                "https://ollama.com and run `ollama serve` (or just open the "
                "Ollama app), then try again."
            )
        except Exception as e:  # noqa: BLE001
            return False, f"Ollama health check failed: {e}"

        models = [m.get("name", "") for m in resp.json().get("models", [])]
        base = self.model.split(":")[0]
        if not any(self.model == m or base == m.split(":")[0] for m in models):
            return False, (
                f"Model '{self.model}' isn't pulled yet. Run: "
                f"`ollama pull {self.model}`. Installed models: "
                f"{', '.join(models) or 'none'}."
            )
        return True, f"Ollama ready with model '{self.model}'."

    def generate(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.8, "num_ctx": 8192},
        }
        if json_mode:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=payload, timeout=config.LLM_TIMEOUT_S
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise LLMError(
                f"Couldn't reach Ollama at {self.host}. Is `ollama serve` running?"
            ) from e
        except requests.exceptions.Timeout as e:
            raise LLMError(
                f"Ollama timed out after {config.LLM_TIMEOUT_S}s. Try a smaller "
                "model or increase STORYFORGE_LLM_TIMEOUT."
            ) from e
        except requests.exceptions.HTTPError as e:
            raise LLMError(f"Ollama returned an error: {e} — {resp.text[:300]}") from e

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise LLMError("Ollama returned an empty response.")
        return content
