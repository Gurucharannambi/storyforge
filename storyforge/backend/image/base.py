"""
Abstract interface every image-generation backend must implement.
Adding a new free/local image model means writing one class here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class ImageGenError(RuntimeError):
    pass


class ImageBackend(ABC):
    name: str = "base"

    @abstractmethod
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
        """Generate an image and write it to out_path (PNG/JPEG)."""
        raise NotImplementedError

    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        raise NotImplementedError


def get_image_backend(backend_name: Optional[str] = None, model: Optional[str] = None) -> ImageBackend:
    from .. import config

    name = (backend_name or config.IMAGE_BACKEND).lower()

    if name == "pollinations":
        from .pollinations_backend import PollinationsBackend
        return PollinationsBackend(model=model or config.POLLINATIONS_MODEL)

    if name == "diffusers":
        from .diffusers_backend import DiffusersBackend
        return DiffusersBackend(model_id=model or config.DIFFUSERS_MODEL_ID)

    if name in ("automatic1111", "a1111", "sdwebui"):
        from .automatic1111_backend import Automatic1111Backend
        return Automatic1111Backend()

    raise ImageGenError(
        f"Unknown image backend '{name}'. Valid options: "
        "'pollinations', 'diffusers', 'automatic1111'."
    )
