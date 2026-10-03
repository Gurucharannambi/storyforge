"""
StoryForge configuration.

Everything here has a free, zero-cost default so the app runs out of the box.
Override any of it with a `.env` file in the project root (see .env.example)
or real environment variables — nothing needs to be hard-coded.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is a convenience, not a hard requirement.
    pass


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(_env("STORYFORGE_DATA_DIR", str(ROOT_DIR / "data")))
PROJECTS_DIR = DATA_DIR / "projects"
# Database for stories + images. Default = local SQLite file (no setup).
# For cloud storage set a Postgres URL (Supabase / Neon / Railway ...).
DATABASE_URL = _env("STORYFORGE_DATABASE_URL", "").strip() or f"sqlite:///{(DATA_DIR / 'storyforge.db').as_posix()}"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# LLM (story text) backend
# ---------------------------------------------------------------------------
# "ollama"        -> local Ollama server (free, fully offline, recommended)
# "openai_compat" -> any local OpenAI-compatible server: LM Studio,
#                     text-generation-webui, vLLM, llama.cpp server, etc.
LLM_BACKEND = _env("STORYFORGE_LLM_BACKEND", "ollama")
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434")
# Any model you've pulled with `ollama pull <name>` works. Good free choices,
# smallest/fastest first: "qwen2.5:7b-instruct", "llama3.1:8b",
# "mistral:7b-instruct", or a bigger one like "qwen2.5:32b" / "glm4:9b" if
# your machine can take it. GLM-5.3 or similar can be used here too, once
# it has an Ollama/GGUF build available.
OLLAMA_MODEL = _env("STORYFORGE_LLM_MODEL", "qwen2.5:7b-instruct")
OPENAI_COMPAT_BASE_URL = _env("STORYFORGE_LLM_BASE_URL", "http://localhost:1234/v1")
OPENAI_COMPAT_API_KEY = _env("STORYFORGE_LLM_API_KEY", "not-needed")
OPENAI_COMPAT_MODEL = _env("STORYFORGE_LLM_MODEL", "local-model")
LLM_TIMEOUT_S = _env_int("STORYFORGE_LLM_TIMEOUT", 1800)

# ---------------------------------------------------------------------------
# Image generation backend
# ---------------------------------------------------------------------------
# "pollinations" -> free hosted API, no key, no GPU needed. Zero setup.
#                    Great default so the app "just works" everywhere.
# "diffusers"    -> fully local SDXL / SD1.5 / FLUX via HuggingFace diffusers.
#                    Needs a decent GPU (or patience on CPU) but is 100%
#                    offline and free.
# "automatic1111"-> talk to a local AUTOMATIC1111 / SD-WebUI-compatible
#                    server already running on your machine.
IMAGE_BACKEND = _env("STORYFORGE_IMAGE_BACKEND", "pollinations")

POLLINATIONS_BASE_URL = _env("STORYFORGE_POLLINATIONS_URL", "https://image.pollinations.ai/prompt")
POLLINATIONS_MODEL = _env("STORYFORGE_POLLINATIONS_MODEL", "flux")  # flux | turbo | etc.
POLLINATIONS_TIMEOUT_S = _env_int("STORYFORGE_POLLINATIONS_TIMEOUT", 120)
# Free anonymous tier is rate limited: space requests out and retry on 429.
POLLINATIONS_MIN_INTERVAL_S = _env_int("STORYFORGE_POLLINATIONS_INTERVAL", 6)
POLLINATIONS_RETRIES = _env_int("STORYFORGE_POLLINATIONS_RETRIES", 6)
# Optional free key from https://enter.pollinations.ai - raises the rate limit.
POLLINATIONS_API_KEY = _env("STORYFORGE_POLLINATIONS_KEY", "")

# Local diffusers model id, e.g. "stabilityai/stable-diffusion-xl-base-1.0",
# "black-forest-labs/FLUX.1-schnell" (fast, Apache-2.0),
# "runwayml/stable-diffusion-v1-5" (small, works on modest GPUs / CPU)
DIFFUSERS_MODEL_ID = _env("STORYFORGE_DIFFUSERS_MODEL", "stabilityai/sdxl-turbo")
DIFFUSERS_DEVICE = _env("STORYFORGE_DIFFUSERS_DEVICE", "auto")  # auto | cuda | mps | cpu
DIFFUSERS_STEPS = _env_int("STORYFORGE_DIFFUSERS_STEPS", 25)

AUTOMATIC1111_BASE_URL = _env("STORYFORGE_A1111_URL", "http://127.0.0.1:7860")

IMAGE_WIDTH = _env_int("STORYFORGE_IMAGE_WIDTH", 768)
IMAGE_HEIGHT = _env_int("STORYFORGE_IMAGE_HEIGHT", 768)

# ---------------------------------------------------------------------------
# App server
# ---------------------------------------------------------------------------
HOST = _env("STORYFORGE_HOST", "0.0.0.0")
PORT = _env_int("STORYFORGE_PORT", 8000)
