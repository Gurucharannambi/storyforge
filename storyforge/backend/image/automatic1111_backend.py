from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import requests

from .. import config
from .base import ImageBackend, ImageGenError


class Automatic1111Backend(ImageBackend):
    """
    Talks to a locally running AUTOMATIC1111 Stable Diffusion WebUI (or any
    server implementing its /sdapi/v1/txt2img contract, e.g. some ComfyUI
    wrappers). Use this if you already run SD WebUI for other projects and
    want StoryForge to reuse the same checkpoint/LoRAs/extensions.
    """

    name = "automatic1111"

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or config.AUTOMATIC1111_BASE_URL).rstrip("/")

    def check_available(self) -> tuple[bool, str]:
        try:
            resp = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=5)
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            return False, (
                f"Can't reach AUTOMATIC1111 at {self.base_url}. Start SD WebUI with "
                "`--api` and make sure the URL/port matches STORYFORGE_A1111_URL."
            )
        models = resp.json()
        if not models:
            return False, "AUTOMATIC1111 is running but has no checkpoint loaded."
        return True, f"AUTOMATIC1111 ready at {self.base_url}."

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
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": 25,
            "cfg_scale": 7,
            "seed": seed if seed is not None else -1,
            "sampler_name": "DPM++ 2M Karras",
        }
        try:
            resp = requests.post(
                f"{self.base_url}/sdapi/v1/txt2img", json=payload, timeout=300
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ImageGenError(f"AUTOMATIC1111 request failed: {e}") from e

        data = resp.json()
        images = data.get("images") or []
        if not images:
            raise ImageGenError("AUTOMATIC1111 returned no images.")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(images[0]))
