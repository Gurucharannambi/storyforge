"""
Persistent story context: character, location, and object profiles.

The story generator extracts these once; this module is what turns them
into reusable prompt fragments so every scene image stays visually
consistent, and lets a user hand-edit a character's visual_tags and have
it apply to every future (re)generated image automatically.
"""
from __future__ import annotations

from typing import Iterable

from .schema import Character, Location, Project, Scene, StoryObject


def find_mentioned_characters(scene: Scene, characters: Iterable[Character]) -> list[Character]:
    wanted = {n.strip().lower() for n in scene.characters_present}
    if wanted:
        matched = [c for c in characters if c.name.strip().lower() in wanted]
        if matched:
            return matched
    # Fall back to scanning scene text for character names if the LLM left
    # characters_present empty or mismatched.
    text_lower = scene.text.lower()
    return [c for c in characters if c.name.lower() in text_lower]


def find_location(scene: Scene, locations: Iterable[Location]) -> Location | None:
    if not scene.setting:
        return None
    setting_norm = scene.setting.strip().lower()
    for loc in locations:
        if loc.name.strip().lower() == setting_norm:
            return loc
    # loose match
    for loc in locations:
        if loc.name.strip().lower() in setting_norm or setting_norm in loc.name.strip().lower():
            return loc
    return None


def find_mentioned_objects(scene: Scene, objects: Iterable[StoryObject]) -> list[StoryObject]:
    text_lower = scene.text.lower()
    return [o for o in objects if o.name and o.name.lower() in text_lower]


def character_consistency_fragment(characters: list[Character]) -> str:
    """
    One clause per character: "NAME (visual tags)" — appended to every scene
    prompt that includes them so the image model draws the same look each
    time, instead of reinventing the character per scene.
    """
    parts = []
    for c in characters:
        tags = c.visual_tags.strip() or c.description.strip()
        if tags:
            parts.append(f"{c.name} ({tags})")
        else:
            parts.append(c.name)
    return ", ".join(parts)


def update_character(project: Project, character_id: str, **fields) -> Character | None:
    for c in project.characters:
        if c.id == character_id:
            for k, v in fields.items():
                if hasattr(c, k) and v is not None:
                    setattr(c, k, v)
            return c
    return None
