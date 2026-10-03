"""
StoryForge web layer. Thin FastAPI wrapper around backend.pipeline — no
business logic lives here, just request/response handling, validation
errors, and static file serving.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, pipeline
from .image.base import ImageGenError, get_image_backend
from .llm.base import LLMError, get_llm_backend
from .story.schema import GenStatus, Project, StoryParams
from .storybook import project_store, renderer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("storyforge")

app = FastAPI(title="StoryForge", version="1.0.0")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# ---------------------------------------------------------------------------
# Health / config
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    """Reports whether the configured LLM and image backends are actually
    reachable/usable right now, with actionable messages for the UI."""
    results = {}

    try:
        llm = get_llm_backend()
        ok, msg = llm.check_available()
        results["llm"] = {"backend": llm.name, "ok": ok, "message": msg}
    except Exception as e:  # noqa: BLE001
        results["llm"] = {"backend": config.LLM_BACKEND, "ok": False, "message": str(e)}

    try:
        img = get_image_backend()
        ok, msg = img.check_available()
        results["image"] = {"backend": img.name, "ok": ok, "message": msg}
    except Exception as e:  # noqa: BLE001
        results["image"] = {"backend": config.IMAGE_BACKEND, "ok": False, "message": str(e)}

    results["healthy"] = results["llm"]["ok"] and results["image"]["ok"]
    return results


@app.get("/api/config")
def get_config():
    return {
        "llm_backend": config.LLM_BACKEND,
        "llm_model": config.OLLAMA_MODEL if config.LLM_BACKEND == "ollama" else config.OPENAI_COMPAT_MODEL,
        "image_backend": config.IMAGE_BACKEND,
        "image_model": {
            "pollinations": config.POLLINATIONS_MODEL,
            "diffusers": config.DIFFUSERS_MODEL_ID,
            "automatic1111": "(server-configured)",
        }.get(config.IMAGE_BACKEND, ""),
        "image_width": config.IMAGE_WIDTH,
        "image_height": config.IMAGE_HEIGHT,
    }


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@app.get("/api/projects")
def list_projects():
    return project_store.list_projects()


@app.post("/api/projects", response_model=Project)
def create_project(params: StoryParams):
    try:
        return pipeline.create_story(params)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("Story generation failed")
        raise HTTPException(status_code=500, detail=f"Story generation failed: {e}") from e


@app.get("/api/projects/{project_id}", response_model=Project)
def get_project(project_id: str):
    project = project_store.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if not project_store.delete(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"deleted": project_id}


# ---------------------------------------------------------------------------
# Scene text regeneration
# ---------------------------------------------------------------------------
class RegenerateTextBody(BaseModel):
    direction: str = ""


@app.post("/api/projects/{project_id}/scenes/{scene_id}/regenerate-text", response_model=Project)
def regenerate_scene_text_endpoint(project_id: str, scene_id: str, body: RegenerateTextBody):
    try:
        return pipeline.regenerate_scene(project_id, scene_id, direction=body.direction)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------
@app.post("/api/projects/{project_id}/images")
def generate_all_images(project_id: str):
    try:
        pipeline.start_generate_all_images(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"started": True}


@app.get("/api/projects/{project_id}/images/progress")
def image_progress(project_id: str):
    return pipeline.get_progress(project_id)


class RegenerateImageBody(BaseModel):
    seed: Optional[int] = None


@app.post("/api/projects/{project_id}/scenes/{scene_id}/regenerate-image", response_model=Project)
def regenerate_scene_image(project_id: str, scene_id: str, body: RegenerateImageBody):
    try:
        return pipeline.generate_scene_image(project_id, scene_id, seed=body.seed)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ImageGenError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Storybook rendering / download
# ---------------------------------------------------------------------------
@app.get("/api/projects/{project_id}/storybook", response_class=HTMLResponse)
def get_storybook(project_id: str):
    project = project_store.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return renderer.render_html(project)


@app.get("/api/projects/{project_id}/storybook/download")
def download_storybook(project_id: str):
    project = project_store.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    path = renderer.render_to_file(project)
    return FileResponse(
        path, media_type="text/html", filename=f"{project.title.replace(' ', '_')}.html"
    )


# ---------------------------------------------------------------------------
# Static assets: generated images + frontend SPA
# ---------------------------------------------------------------------------
@app.get("/api/projects/{project_id}/images/{filename}")
def get_scene_image(project_id: str, filename: str):
    path = project_store.ensure_image(project_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(path)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:

    @app.get("/")
    def root():
        return JSONResponse({"message": "StoryForge API is running. Frontend not found."})
