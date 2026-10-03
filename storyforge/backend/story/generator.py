"""
Story generation: turns a user's idea + parameters into a structured story
(title, synopsis, characters, locations, objects, scenes) via a local LLM.

This module only talks to the LLM and returns validated data — it knows
nothing about images or the web layer, which keeps it easy to test and
swap out independently (per the "modular architecture" requirement).
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..llm.base import LLMBackend, LLMError
from .schema import Character, Location, Project, Scene, StoryObject, StoryParams

SYSTEM_PROMPT = """You are a professional children's/YA story writer and story editor \
working for an illustrated storybook studio. You always respond with a SINGLE valid \
JSON object and nothing else: no markdown fences, no commentary, no trailing text.

You write vivid, age-appropriate, well-structured stories broken cleanly into scenes \
that each work as a single illustration. You keep character appearances consistent \
and describe them with concrete, visual, paintable details (not abstract traits)."""

STORY_JSON_SCHEMA_HINT = """{
  "title": "string, catchy title for the story",
  "synopsis": "string, 2-4 sentence overview",
  "characters": [
    {
      "name": "string",
      "role": "protagonist | sidekick | antagonist | supporting",
      "description": "1-3 sentences about their personality and role in the story",
      "visual_tags": "short comma-separated list of concrete visual/appearance details for an image generator, e.g. 'young girl, curly red hair, green raincoat, freckles, gap-toothed smile'"
    }
  ],
  "locations": [
    {
      "name": "string",
      "description": "1-2 sentences",
      "visual_tags": "comma-separated visual details, e.g. 'misty pine forest, mossy stones, shafts of morning light'"
    }
  ],
  "objects": [
    {
      "name": "string, an important recurring object/item in the story (optional, can be empty list)",
      "description": "1 sentence",
      "visual_tags": "comma-separated visual details"
    }
  ],
  "scenes": [
    {
      "index": 0,
      "title": "short scene title",
      "text": "the actual story prose for this scene, written for the target age group, 80-180 words",
      "setting": "must match a location name from 'locations' above",
      "characters_present": ["names, must match entries in 'characters' above"],
      "mood": "short mood/lighting descriptor, e.g. 'tense, dusk, cool blue light'"
    }
  ]
}"""


def _build_user_prompt(params: StoryParams) -> str:
    return f"""Write a complete illustrated story with EXACTLY {params.num_scenes} scenes.

Story idea: {params.idea}
Genre: {params.genre}
Target age group: {params.target_age}
Art style (for context only, does not change the writing): {params.art_style}

Requirements:
- Exactly {params.num_scenes} scenes, indexed 0 to {params.num_scenes - 1}, in narrative order.
- Introduce every character the first time they appear with enough detail that an \
illustrator could draw them consistently in every later scene.
- Keep a clear throughline: setup, rising action, climax, resolution, scaled to \
{params.num_scenes} scenes.
- Language, themes, and intensity must suit the target age group.
- Every scene's "text" must be self-contained prose (not a bullet list, not a caption).
- Reuse location and character names EXACTLY across scenes when they recur — this is \
critical for visual consistency later.

Respond with ONLY a JSON object matching this exact shape (field names identical):
{STORY_JSON_SCHEMA_HINT}"""


def _extract_json(raw: str) -> dict[str, Any]:
    """LLMs sometimes wrap JSON in markdown fences or add stray text. Recover it."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # Fall back to the widest {...} span in the text.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(
            "The model's response wasn't valid JSON. Try again, or switch to a "
            f"stronger model. Parse error: {e}"
        ) from e


def _coerce_story_dict(data: dict[str, Any], params: StoryParams) -> Project:
    characters = [
        Character(
            name=c.get("name", "Unnamed"),
            role=c.get("role", ""),
            description=c.get("description", ""),
            visual_tags=c.get("visual_tags", ""),
        )
        for c in data.get("characters", []) or []
    ]
    locations = [
        Location(
            name=l.get("name", "Unnamed place"),
            description=l.get("description", ""),
            visual_tags=l.get("visual_tags", ""),
        )
        for l in data.get("locations", []) or []
    ]
    objects = [
        StoryObject(
            name=o.get("name", ""),
            description=o.get("description", ""),
            visual_tags=o.get("visual_tags", ""),
        )
        for o in data.get("objects", []) or []
        if o.get("name")
    ]

    raw_scenes = sorted(data.get("scenes", []) or [], key=lambda s: s.get("index", 0))
    scenes = [
        Scene(
            index=i,
            title=s.get("title", f"Scene {i + 1}"),
            text=s.get("text", ""),
            setting=s.get("setting", ""),
            characters_present=s.get("characters_present", []) or [],
            mood=s.get("mood", ""),
        )
        for i, s in enumerate(raw_scenes)
    ]

    return Project(
        title=data.get("title", "Untitled Story"),
        params=params,
        synopsis=data.get("synopsis", ""),
        characters=characters,
        locations=locations,
        objects=objects,
        scenes=scenes,
    )


def _extend_scenes(llm: LLMBackend, project: Project, target: int) -> None:
    """The model returned too few scenes: write the missing ones one at a time,
    continuing the story it already produced (cheaper than re-rolling it all)."""
    system = (
        "You are a professional children's/YA story writer. Respond with ONLY a JSON "
        "object — no markdown fences, no commentary."
    )
    chars = "\n".join(f"- {c.name}: {c.description}" for c in project.characters)
    locs = ", ".join(l.name for l in project.locations)
    while len(project.scenes) < target:
        i = len(project.scenes)
        prior = "\n".join(
            f"Scene {sc.index + 1} ({sc.title}): {sc.text}" for sc in project.scenes
        )
        is_last = (i + 1) == target
        user = f"""Story title: {project.title}
Synopsis: {project.synopsis}
Target age group: {project.params.target_age}
Characters:
{chars}
Locations: {locs}

Scenes written so far:
{prior}

Write scene number {i + 1} of {target}. {"This is the FINAL scene: resolve the story." if is_last else "Continue the story; do not end it yet."}
Reuse character and location names exactly. The scene text should be 80-180 words of prose.

Respond with ONLY: {{"title": "...", "text": "...", "setting": "a location name", "characters_present": ["names"], "mood": "..."}}"""
        data = _extract_json(llm.generate(system, user, json_mode=True))
        text = data.get("text", "")
        if not text:
            raise LLMError("The model returned an empty scene.")
        project.scenes.append(
            Scene(
                index=i,
                title=data.get("title", f"Scene {i + 1}"),
                text=text,
                setting=data.get("setting", ""),
                characters_present=data.get("characters_present", []) or [],
                mood=data.get("mood", ""),
            )
        )


def generate_story(llm: LLMBackend, params: StoryParams, *, max_attempts: int = 2) -> Project:
    """
    Ask the LLM for a structured story and return a validated Project with
    EXACTLY params.num_scenes scenes. Retries if the JSON can't be parsed; if the
    model returns too few scenes, the missing ones are written individually.
    """
    target = params.num_scenes
    user_prompt = _build_user_prompt(params)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        prompt = user_prompt
        if attempt > 1:
            prompt += (
                "\n\nIMPORTANT: your previous response could not be parsed as JSON. "
                "Respond with ONLY the raw JSON object — no markdown fences, no prose "
                "before or after it."
            )
        try:
            raw = llm.generate(SYSTEM_PROMPT, prompt, json_mode=True)
            data = _extract_json(raw)
            project = _coerce_story_dict(data, params)
            if not project.scenes:
                raise LLMError("The model produced a story with no scenes.")
            if len(project.scenes) > target:
                project.scenes = project.scenes[:target]
            elif len(project.scenes) < target:
                _extend_scenes(llm, project, target)
            return project
        except LLMError as e:
            last_error = e
            continue

    raise last_error or LLMError("Story generation failed for an unknown reason.")


def regenerate_scene_text(
    llm: LLMBackend, project: Project, scene: Scene, *, direction: str = ""
) -> Scene:
    """Rewrite a single scene's prose while keeping story continuity."""
    other_scenes = "\n".join(
        f"Scene {s.index}: {s.text}" for s in project.scenes if s.id != scene.id
    )
    char_notes = "\n".join(f"- {c.name}: {c.description}" for c in project.characters)

    system = (
        "You are a professional children's/YA story editor. Respond with ONLY a JSON "
        'object of the shape {"title": "...", "text": "...", "mood": "..."} — no '
        "markdown fences, no extra commentary."
    )
    user = f"""Story title: {project.title}
Synopsis: {project.synopsis}
Characters:
{char_notes}

Full story so far (for continuity, do not repeat verbatim):
{other_scenes}

Rewrite ONLY scene {scene.index} (currently titled "{scene.title}"), keeping it \
consistent with the rest of the story, the same setting ("{scene.setting}") and the \
same characters present ({', '.join(scene.characters_present)}).
{'Direction for the rewrite: ' + direction if direction else ''}

Respond with ONLY: {{"title": "...", "text": "...", "mood": "..."}}"""

    raw = llm.generate(system, user, json_mode=True)
    data = _extract_json(raw)
    scene.title = data.get("title", scene.title)
    scene.text = data.get("text", scene.text)
    scene.mood = data.get("mood", scene.mood)
    return scene
