"""
Data model for a StoryForge project.

This is the single source of truth for what a "story" looks like on disk
and over the API. Keeping it in one pydantic module means the LLM output
parser, the storage layer, and the API all validate against the same shape.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class GenStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class Character(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("char"))
    name: str
    role: str = ""                 # e.g. "protagonist", "sidekick", "villain"
    description: str = ""          # narrative description
    visual_tags: str = ""          # short comma-separated appearance tags used
                                    # verbatim in every image prompt they appear in,
                                    # e.g. "young red fox, orange fur, blue scarf,
                                    # big curious eyes"


class Location(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("loc"))
    name: str
    description: str = ""
    visual_tags: str = ""


class StoryObject(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("obj"))
    name: str
    description: str = ""
    visual_tags: str = ""


class Scene(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("scene"))
    index: int
    title: str = ""
    text: str = ""                         # the narrative prose for this scene
    setting: str = ""                      # location name reference
    characters_present: List[str] = Field(default_factory=list)  # character names
    mood: str = ""
    visual_prompt: str = ""                # full prompt sent to the image model
    negative_prompt: str = ""
    image_path: Optional[str] = None       # relative path once generated
    image_status: GenStatus = GenStatus.PENDING
    image_error: Optional[str] = None
    text_status: GenStatus = GenStatus.DONE


class StoryParams(BaseModel):
    idea: str
    genre: str = "adventure"
    target_age: str = "middle-grade (8-12)"
    art_style: str = "whimsical children's book watercolor"
    num_scenes: int = Field(default=6, ge=1, le=20)
    llm_backend: Optional[str] = None   # override server default for this project
    llm_model: Optional[str] = None
    image_backend: Optional[str] = None
    image_model: Optional[str] = None


class Project(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("proj"))
    title: str = "Untitled Story"
    params: StoryParams
    synopsis: str = ""
    characters: List[Character] = Field(default_factory=list)
    locations: List[Location] = Field(default_factory=list)
    objects: List[StoryObject] = Field(default_factory=list)
    scenes: List[Scene] = Field(default_factory=list)
    status: GenStatus = GenStatus.PENDING
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        return next((s for s in self.scenes if s.id == scene_id), None)

    def character_by_name(self, name: str) -> Optional[Character]:
        name_norm = name.strip().lower()
        return next((c for c in self.characters if c.name.strip().lower() == name_norm), None)
