"""
Orchestration layer. This is the only module that knows about *all* the
other modules — it wires LLM -> story -> scenes -> images -> storage
together, and is what the web layer calls. Keeping this separate means the
FastAPI app stays a thin HTTP wrapper, and the pipeline itself is testable
without any web framework involved.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from .image.base import ImageGenError, get_image_backend
from .llm.base import LLMError, get_llm_backend
from .story import character_memory, scene_planner
from .story.generator import generate_story, regenerate_scene_text
from .story.schema import GenStatus, Project, Scene, StoryParams
from .storybook import project_store

logger = logging.getLogger("storyforge")

# In-memory progress tracker, keyed by project id. Fine for a single-user
# local app; projects themselves are always persisted to disk regardless.
_PROGRESS: dict[str, dict] = {}
_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(project_id: str) -> threading.Lock:
    return _LOCKS.setdefault(project_id, threading.Lock())


def get_progress(project_id: str) -> dict:
    return _PROGRESS.get(project_id, {"state": "idle", "done": 0, "total": 0, "message": ""})


def _set_progress(project_id: str, **fields) -> None:
    current = _PROGRESS.setdefault(project_id, {"state": "idle", "done": 0, "total": 0, "message": ""})
    current.update(fields)


# ---------------------------------------------------------------------------
# Story creation
# ---------------------------------------------------------------------------
def create_story(params: StoryParams) -> Project:
    llm = get_llm_backend(params.llm_backend, params.llm_model)
    ok, msg = llm.check_available()
    if not ok:
        raise LLMError(msg)

    project = generate_story(llm, params)
    scene_planner.plan_scenes(project)
    project.status = GenStatus.DONE  # text stage done; images pending
    project_store.save(project)
    return project


def regenerate_scene(project_id: str, scene_id: str, direction: str = "") -> Project:
    project = _require_project(project_id)
    scene = project.get_scene(scene_id)
    if scene is None:
        raise ValueError(f"Scene '{scene_id}' not found in project '{project_id}'.")

    llm = get_llm_backend(project.params.llm_backend, project.params.llm_model)
    ok, msg = llm.check_available()
    if not ok:
        raise LLMError(msg)

    regenerate_scene_text(llm, project, scene, direction=direction)
    scene_planner.replan_scene(project, scene)
    # Text changed, so the old illustration no longer matches — mark it stale.
    scene.image_status = GenStatus.PENDING
    project_store.save(project)
    return project


# ---------------------------------------------------------------------------
# Image generation (all scenes, with progress; and single scene)
# ---------------------------------------------------------------------------
def _require_project(project_id: str) -> Project:
    project = project_store.load(project_id)
    if project is None:
        raise ValueError(f"Project '{project_id}' not found.")
    return project


def generate_scene_image(project_id: str, scene_id: str, *, seed: Optional[int] = None) -> Project:
    project = _require_project(project_id)
    scene = project.get_scene(scene_id)
    if scene is None:
        raise ValueError(f"Scene '{scene_id}' not found in project '{project_id}'.")

    from . import config

    backend = get_image_backend(project.params.image_backend, project.params.image_model)
    ok, msg = backend.check_available()
    if not ok:
        scene.image_status = GenStatus.ERROR
        scene.image_error = msg
        project_store.save(project)
        raise ImageGenError(msg)

    if not scene.visual_prompt:
        scene_planner.replan_scene(project, scene)

    scene.image_status = GenStatus.RUNNING
    scene.image_error = None
    project_store.save(project)

    out_path = project_store.images_dir(project.id) / f"scene_{scene.index:02d}.png"
    try:
        backend.generate(
            scene.visual_prompt,
            scene.negative_prompt,
            out_path,
            width=config.IMAGE_WIDTH,
            height=config.IMAGE_HEIGHT,
            seed=seed,
        )
        project_store.store_image(project.id, out_path)
        scene.image_path = f"images/{out_path.name}"
        scene.image_status = GenStatus.DONE
        scene.image_error = None
    except ImageGenError as e:
        scene.image_status = GenStatus.ERROR
        scene.image_error = str(e)
        project_store.save(project)
        raise

    project_store.save(project)
    return project


def generate_all_images(project_id: str) -> None:
    """
    Runs synchronously in a background thread (started by the API layer).
    Progress is polled via get_progress(). Continues past individual scene
    failures so one bad prompt doesn't block the rest of the book.
    """
    with _lock_for(project_id):
        project = _require_project(project_id)
        scenes = sorted(project.scenes, key=lambda s: s.index)
        total = len(scenes)
        _set_progress(project_id, state="running", done=0, total=total, message="Starting image generation…")

        for i, scene in enumerate(scenes):
            _set_progress(
                project_id,
                message=f"Generating illustration {i + 1} of {total}: “{scene.title}”…",
            )
            try:
                generate_scene_image(project_id, scene.id)
            except (ImageGenError, ValueError) as e:
                logger.warning("Scene %s image failed: %s", scene.id, e)
                _set_progress(project_id, message=f"Scene {i + 1} failed: {e}")
            _set_progress(project_id, done=i + 1)

        project = _require_project(project_id)
        failed = [s for s in project.scenes if s.image_status == GenStatus.ERROR]
        if failed:
            _set_progress(
                project_id,
                state="done_with_errors",
                message=f"Finished with {len(failed)} scene(s) that need attention.",
            )
        else:
            _set_progress(project_id, state="done", message="All illustrations generated.")


def start_generate_all_images(project_id: str) -> None:
    _require_project(project_id)  # fail fast if the project doesn't exist
    thread = threading.Thread(target=generate_all_images, args=(project_id,), daemon=True)
    thread.start()
