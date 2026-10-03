from __future__ import annotations

import random
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

from .. import config
from .base import ImageBackend, ImageGenError


# The free anonymous tier only allows roughly ONE request at a time and rejects
# bursts with HTTP 429. So all requests go through one lock, are spaced apart,
# and are retried with backoff when the server says "slow down".
_REQUEST_LOCK = threading.Lock()
_last_request_at = 0.0


class PollinationsBackend(ImageBackend):
    """
    Uses https://pollinations.ai — a free, keyless, hosted image generation
    API (backed by open models such as FLUX). This is the zero-setup default:
    no GPU, no downloads, no account. Great for trying StoryForge instantly;
    switch to 'diffusers' for fully offline/local generation later.
    """

    name = "pollinations"

    def __init__(self, model: str | None = None):
        self.model = model or config.POLLINATIONS_MODEL

    def check_available(self) -> tuple[bool, str]:
        try:
            resp = requests.get("https://image.pollinations.ai/", timeout=8)
            if resp.status_code >= 500:
                return False, "Pollinations.ai looks down right now (server error)."
        except requests.exceptions.RequestException as e:
            return False, (
                "Can't reach pollinations.ai — check your internet connection, or "
                f"switch STORYFORGE_IMAGE_BACKEND to 'diffusers' for offline use. ({e})"
            )
        return True, f"Pollinations.ai ready (model '{self.model}')."

    def generate(
        self,
        prompt: str,
        negative_prompt: str,
        out_path: Path,
        *,
        width: int,
        height: int,
        seed: Optional[int] = None,
    ) -> None:
        seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        encoded_prompt = urllib.parse.quote(prompt[:1800])
        params = {
            "model": self.model,
            "width": width,
            "height": height,
            "seed": seed,
            "nologo": "true",
            "private": "true",
        }
        base_url = config.POLLINATIONS_BASE_URL
        headers = {}
        if config.POLLINATIONS_API_KEY:
            params["key"] = config.POLLINATIONS_API_KEY
            headers["Authorization"] = f"Bearer {config.POLLINATIONS_API_KEY}"
            # Keyed requests go to Pollinations' current unified endpoint.
            if base_url.rstrip("/") == "https://image.pollinations.ai/prompt":
                base_url = "https://gen.pollinations.ai/image"
        url = f"{base_url.rstrip('/')}/{encoded_prompt}"

        global _last_request_at
        resp = None
        last_problem = ""
        last_status = 0
        with _REQUEST_LOCK:
            for attempt in range(1, config.POLLINATIONS_RETRIES + 1):
                wait = config.POLLINATIONS_MIN_INTERVAL_S - (time.time() - _last_request_at)
                if wait > 0:
                    time.sleep(wait)
                try:
                    resp = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=config.POLLINATIONS_TIMEOUT_S,
                    )
                except requests.exceptions.Timeout:
                    last_problem = f"timed out after {config.POLLINATIONS_TIMEOUT_S}s"
                    resp = None
                except requests.exceptions.RequestException as e:
                    last_problem = str(e)
                    resp = None
                finally:
                    _last_request_at = time.time()

                if resp is not None:
                    if resp.status_code in (402, 429) or resp.status_code >= 500:
                        last_status = resp.status_code
                        last_problem = f"HTTP {resp.status_code} (server busy / rate limited)"
                        try:
                            retry_after = float(resp.headers.get("Retry-After", ""))
                        except ValueError:
                            retry_after = 0.0
                        if attempt < config.POLLINATIONS_RETRIES:
                            time.sleep(max(retry_after, 8.0 * attempt))
                        resp = None
                        continue
                    break  # success or a non-retryable status; handled below
                if attempt < config.POLLINATIONS_RETRIES:
                    time.sleep(8.0 * attempt)

        if resp is None:
            if last_status == 402:
                raise ImageGenError(
                    "Pollinations.ai refused this image (HTTP 402 Payment Required). "
                    "Its free no-key tier is out of quota right now. Fix: get a FREE key "
                    "at https://enter.pollinations.ai and put it in the .env file as "
                    "STORYFORGE_POLLINATIONS_KEY=your_key (run.bat can ask you for it)."
                )
            raise ImageGenError(
                f"Pollinations.ai failed after {config.POLLINATIONS_RETRIES} tries "
                f"({last_problem}). The free service limits how fast you can "
                "generate images - wait a minute and click again, or add a free key "
                "(STORYFORGE_POLLINATIONS_KEY in .env, from enter.pollinations.ai)."
            )

        try:
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ImageGenError(f"Pollinations.ai request failed: {e}") from e

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            raise ImageGenError(
                f"Pollinations.ai did not return an image (content-type: {content_type})."
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
