"""
Scene planning: turns each narrative Scene into a detailed image-generation
prompt, weaving in character/location/object visual tags from story memory
so the same character looks the same across every illustration.
"""
from __future__ import annotations

from . import character_memory as memory
from .schema import Project, Scene

NEGATIVE_PROMPT_DEFAULT = (
    "text, watermark, signature, extra limbs, deformed hands, disfigured, "
    "blurry, lowres, jpeg artifacts, out of frame, cropped, duplicate, "
    "bad anatomy, bad proportions"
)

STYLE_QUALITY_SUFFIX = "high detail, professional children's book illustration, cohesive color palette"


def build_visual_prompt(project: Project, scene: Scene) -> str:
    style = project.params.art_style.strip() or "storybook illustration"

    chars = memory.find_mentioned_characters(scene, project.characters)
    location = memory.find_location(scene, project.locations)
    objects = memory.find_mentioned_objects(scene, project.objects)

    char_fragment = memory.character_consistency_fragment(chars)
    location_fragment = ""
    if location:
        location_fragment = f"{location.name}: {location.visual_tags or location.description}"
    object_fragment = ", ".join(
        f"{o.name} ({o.visual_tags})" if o.visual_tags else o.name for o in objects
    )

    scene_action = scene.text.strip()
    if len(scene_action) > 400:
        # Keep the prompt focused on the visual beat, not the whole prose passage.
        scene_action = scene_action[:400].rsplit(".", 1)[0] + "."

    pieces = [
        f"{style} illustration.",
        f"Scene: {scene_action}",
    ]
    if char_fragment:
        pieces.append(f"Characters: {char_fragment}.")
    if location_fragment:
        pieces.append(f"Setting: {location_fragment}.")
    if object_fragment:
        pieces.append(f"Notable objects: {object_fragment}.")
    if scene.mood:
        pieces.append(f"Mood/lighting: {scene.mood}.")
    pieces.append(STYLE_QUALITY_SUFFIX + ".")

    return " ".join(pieces)


def plan_scenes(project: Project) -> Project:
    """Fill in visual_prompt / negative_prompt for every scene in the project."""
    for scene in project.scenes:
        scene.visual_prompt = build_visual_prompt(project, scene)
        scene.negative_prompt = NEGATIVE_PROMPT_DEFAULT
    return project


def replan_scene(project: Project, scene: Scene) -> Scene:
    scene.visual_prompt = build_visual_prompt(project, scene)
    scene.negative_prompt = NEGATIVE_PROMPT_DEFAULT
    return scene
