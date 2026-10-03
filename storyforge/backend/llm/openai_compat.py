from __future__ import annotations

import requests

from .. import config
from .base import LLMBackend, LLMError


class OpenAICompatBackend(LLMBackend):
    """
    Talks to any local server exposing an OpenAI-compatible /chat/completions
    endpoint: LM Studio, text-generation-webui, llama.cpp's server, vLLM,
    KoboldCpp, etc. All free, all local — this backend just needs a base URL.
    """

    name = "openai_compat"

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None):
        self.model = model or config.OPENAI_COMPAT_MODEL
        self.base_url = (base_url or config.OPENAI_COMPAT_BASE_URL).rstrip("/")
        self.api_key = api_key or config.OPENAI_COMPAT_API_KEY

    def check_available(self) -> tuple[bool, str]:
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return False, (
                f"Can't reach an OpenAI-compatible server at {self.base_url}. "
                "Start LM Studio / text-generation-webui / llama.cpp server "
                "with its local API enabled, then try again."
            )
        except Exception as e:  # noqa: BLE001
            return False, f"Local server health check failed: {e}"
        return True, f"Local server ready at {self.base_url} (model '{self.model}')."

    def generate(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=config.LLM_TIMEOUT_S,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise LLMError(f"Couldn't reach local server at {self.base_url}.") from e
        except requests.exceptions.Timeout as e:
            raise LLMError(f"Local server timed out after {config.LLM_TIMEOUT_S}s.") from e
        except requests.exceptions.HTTPError as e:
            raise LLMError(f"Local server returned an error: {e} — {resp.text[:300]}") from e

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"Unexpected response shape from local server: {data}") from e
