from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import config
from .base import ImageBackend, ImageGenError

_PIPELINE_CACHE: dict[str, object] = {}


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class DiffusersBackend(ImageBackend):
    """
    Fully local, fully offline image generation using HuggingFace `diffusers`.
    Works with any free/open-weight text-to-image model on the Hub, e.g.:
      - "stabilityai/sdxl-turbo"                (fast, good on 8GB+ GPUs)
      - "stabilityai/stable-diffusion-xl-base-1.0"
      - "black-forest-labs/FLUX.1-schnell"      (Apache-2.0, needs more VRAM)
      - "runwayml/stable-diffusion-v1-5"        (small, works on modest GPUs/CPU)

    The pipeline is lazily loaded and cached across calls/scenes so you only
    pay the model-load cost once per run.
    """

    name = "diffusers"

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or config.DIFFUSERS_MODEL_ID
        self.device = _resolve_device(config.DIFFUSERS_DEVICE)

    def check_available(self) -> tuple[bool, str]:
        try:
            import torch  # noqa: F401
            import diffusers  # noqa: F401
        except ImportError:
            return False, (
                "`torch` and `diffusers` aren't installed. Run: "
                "pip install torch diffusers transformers accelerate safetensors"
            )
        if self.device == "cpu":
            return True, (
                f"diffusers ready on CPU with '{self.model_id}' — this will be slow "
                "(minutes per image). A GPU (CUDA or Apple MPS) is strongly recommended."
            )
        return True, f"diffusers ready on {self.device} with '{self.model_id}'."

    def _load_pipeline(self):
        if self.model_id in _PIPELINE_CACHE:
            return _PIPELINE_CACHE[self.model_id]

        try:
            import torch
            from diffusers import AutoPipelineForText2Image
        except ImportError as e:
            raise ImageGenError(
                "`torch`/`diffusers` aren't installed. Run: "
                "pip install torch diffusers transformers accelerate safetensors"
            ) from e

        dtype = torch.float16 if self.device in ("cuda", "mps") else torch.float32
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(
                self.model_id, torch_dtype=dtype, use_safetensors=True
            )
            pipe = pipe.to(self.device)
        except Exception as e:  # noqa: BLE001
            raise ImageGenError(
                f"Failed to load model '{self.model_id}': {e}. Check the model id, "
                "your internet connection (first run downloads weights), and disk space."
            ) from e

        _PIPELINE_CACHE[self.model_id] = pipe
        return pipe

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
        import torch

        pipe = self._load_pipeline()
        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)

        kwargs = dict(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=config.DIFFUSERS_STEPS,
            generator=generator,
        )
        # SDXL-Turbo/schnell-style distilled models want guidance_scale=0 and few steps;
        # regular SD/SDXL models want negative prompts + real guidance. Try to do the
        # right thing without requiring the user to configure it.
        if "turbo" in self.model_id.lower() or "schnell" in self.model_id.lower():
            kwargs["guidance_scale"] = 0.0
            kwargs["num_inference_steps"] = min(config.DIFFUSERS_STEPS, 4)
        else:
            kwargs["guidance_scale"] = 7.0
            if negative_prompt:
                kwargs["negative_prompt"] = negative_prompt

        try:
            result = pipe(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise ImageGenError(f"Image generation failed: {e}") from e

        image = result.images[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)
