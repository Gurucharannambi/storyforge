"""
Persistence layer backed by a real database (SQLAlchemy).

* Default: a local SQLite file  ->  data/storyforge.db   (zero setup)
* Cloud:   set STORYFORGE_DATABASE_URL to any Postgres URL (Supabase, Neon,
           Railway, ...) and the same code stores everything there instead.

What is stored:
  projects : one row per story (full project JSON + a few searchable columns)
  images   : every generated picture as bytes, so the database alone is a
             complete backup. Pictures are ALSO cached as files in
             data/projects/<id>/images/ because the app serves them from disk;
             if a file is missing it is restored from the database on demand.

Older stories saved as data/projects/<id>/project.json are imported
automatically the first time the app starts.
"""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete as sa_delete,
    insert,
    select,
    update,
)

from .. import config
from ..story.schema import Project

_meta = MetaData()

_projects = Table(
    "projects",
    _meta,
    Column("id", String(64), primary_key=True),
    Column("title", Text),
    Column("status", String(32)),
    Column("num_scenes", Integer),
    Column("art_style", Text),
    Column("created_at", String(40)),
    Column("updated_at", String(40)),
    Column("data", Text, nullable=False),
)

_images = Table(
    "images",
    _meta,
    Column("project_id", String(64), primary_key=True),
    Column("filename", String(255), primary_key=True),
    Column("data", LargeBinary, nullable=False),
)

_engine = None
_engine_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Engine / setup
# ---------------------------------------------------------------------------
def _normalized_url() -> str:
    url = config.DATABASE_URL.strip()
    if url.startswith("postgres://"):  # some providers still hand out this form
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            url = _normalized_url()
            kwargs: dict = {"pool_pre_ping": True}
            if url.startswith("sqlite"):
                kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            engine = create_engine(url, **kwargs)
            _meta.create_all(engine)
            _engine = engine
            print(f"[StoryForge] Database: {engine.url.render_as_string(hide_password=True)}")
            _import_legacy_projects()
    return _engine


def _project_dir(project_id: str) -> Path:
    return config.PROJECTS_DIR / project_id


def images_dir(project_id: str) -> Path:
    d = _project_dir(project_id) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _row_values(project: Project) -> dict:
    return {
        "title": project.title,
        "status": str(getattr(project.status, "value", project.status)),
        "num_scenes": len(project.scenes),
        "art_style": project.params.art_style,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "data": project.model_dump_json(),
    }


def _import_legacy_projects() -> None:
    """One-time import of old file-based stories (project.json) into the DB."""
    if not config.PROJECTS_DIR.exists():
        return
    engine = _engine
    for d in config.PROJECTS_DIR.iterdir():
        f = d / "project.json"
        if not f.is_file():
            continue
        try:
            project = Project.model_validate(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
        with engine.begin() as conn:
            if conn.execute(select(_projects.c.id).where(_projects.c.id == project.id)).first():
                continue
            conn.execute(insert(_projects).values(id=project.id, **_row_values(project)))
        img_dir = d / "images"
        if img_dir.is_dir():
            for img in img_dir.iterdir():
                if img.is_file():
                    store_image(project.id, img)
        print(f"[StoryForge] Imported old story into database: {project.title}")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def save(project: Project) -> Project:
    now = datetime.now(timezone.utc).isoformat()
    if not project.created_at:
        project.created_at = now
    project.updated_at = now

    _project_dir(project.id).mkdir(parents=True, exist_ok=True)
    values = _row_values(project)
    with get_engine().begin() as conn:
        exists = conn.execute(select(_projects.c.id).where(_projects.c.id == project.id)).first()
        if exists:
            conn.execute(update(_projects).where(_projects.c.id == project.id).values(**values))
        else:
            conn.execute(insert(_projects).values(id=project.id, **values))
    return project


def load(project_id: str) -> Optional[Project]:
    with get_engine().connect() as conn:
        row = conn.execute(select(_projects.c.data).where(_projects.c.id == project_id)).first()
    if not row:
        return None
    return Project.model_validate_json(row[0])


def delete(project_id: str) -> bool:
    with get_engine().begin() as conn:
        res = conn.execute(sa_delete(_projects).where(_projects.c.id == project_id))
        conn.execute(sa_delete(_images).where(_images.c.project_id == project_id))
    d = _project_dir(project_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return res.rowcount > 0


def list_projects() -> list[dict]:
    """Lightweight listing (id, title, status, scene count) for the gallery view."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                _projects.c.id,
                _projects.c.title,
                _projects.c.status,
                _projects.c.num_scenes,
                _projects.c.created_at,
                _projects.c.art_style,
            ).order_by(_projects.c.created_at.desc())
        ).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "status": r.status,
            "num_scenes": r.num_scenes,
            "created_at": r.created_at,
            "art_style": r.art_style,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def store_image(project_id: str, path: Path) -> bool:
    """Copy a generated picture into the database (upsert). Never raises."""
    try:
        data = Path(path).read_bytes()
        name = Path(path).name
        with get_engine().begin() as conn:
            exists = conn.execute(
                select(_images.c.filename).where(
                    (_images.c.project_id == project_id) & (_images.c.filename == name)
                )
            ).first()
            if exists:
                conn.execute(
                    update(_images)
                    .where((_images.c.project_id == project_id) & (_images.c.filename == name))
                    .values(data=data)
                )
            else:
                conn.execute(insert(_images).values(project_id=project_id, filename=name, data=data))
        return True
    except Exception as e:  # DB trouble must not break image generation
        print(f"[StoryForge] Could not store image in database: {e}")
        return False


def ensure_image(project_id: str, filename: str) -> Optional[Path]:
    """Return the local file for an image, restoring it from the DB if needed."""
    filename = Path(filename).name  # no path tricks
    path = images_dir(project_id) / filename
    if path.exists():
        return path
    with get_engine().connect() as conn:
        row = conn.execute(
            select(_images.c.data).where(
                (_images.c.project_id == project_id) & (_images.c.filename == filename)
            )
        ).first()
    if not row:
        return None
    path.write_bytes(row[0])
    return path
