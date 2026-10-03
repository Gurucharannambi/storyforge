"""
Renders a finished (or in-progress) Project into a single self-contained
HTML file: a flip-through interactive storybook a user can double-click
open in any browser, with no server required, images embedded as base64.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

from ..story.schema import Project
from . import project_store

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --paper: #FBF7EE;
    --ink: #232017;
    --ink-soft: #5B5646;
    --accent: #B8863E;
    --accent-deep: #6E4A21;
    --rule: #E4DBC5;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #2B2A26;
    color: var(--ink);
    font-family: 'Iowan Old Style', 'Palatino Linotype', Georgia, serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 100vh;
    padding: 32px 16px 64px;
  }}
  .cover {{
    max-width: 720px;
    text-align: center;
    color: #EFE9D8;
    margin-bottom: 28px;
  }}
  .cover h1 {{
    font-size: 2.4rem;
    margin: 0 0 8px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }}
  .cover p {{ color: #C9C2AC; font-size: 1.05rem; line-height: 1.6; }}
  .page {{
    background: var(--paper);
    max-width: 760px;
    width: 100%;
    border-radius: 6px;
    box-shadow: 0 18px 40px rgba(0,0,0,0.35);
    margin-bottom: 22px;
    overflow: hidden;
  }}
  .page img {{
    width: 100%;
    display: block;
    aspect-ratio: 1 / 1;
    object-fit: cover;
    background: #ECE5D2;
  }}
  .page .missing-img {{
    width: 100%;
    aspect-ratio: 1 / 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--ink-soft);
    font-family: Georgia, serif;
    font-style: italic;
    background: repeating-linear-gradient(45deg, #ECE5D2, #ECE5D2 10px, #E5DCC4 10px, #E5DCC4 20px);
  }}
  .page-body {{
    padding: 28px 34px 32px;
    border-top: 1px solid var(--rule);
  }}
  .page-num {{
    font-family: Georgia, serif;
    color: var(--accent-deep);
    font-size: 0.8rem;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
  }}
  .page-title {{
    font-size: 1.35rem;
    margin: 0 0 12px;
    color: var(--ink);
  }}
  .page-text {{
    font-size: 1.08rem;
    line-height: 1.75;
    color: var(--ink);
    max-width: 62ch;
  }}
  footer {{
    color: #8A8471;
    font-size: 0.8rem;
    margin-top: 12px;
  }}
</style>
</head>
<body>
  <div class="cover">
    <h1>{title}</h1>
    <p>{synopsis}</p>
  </div>
  {pages}
  <footer>Made with StoryForge — free &amp; open-source, generated locally.</footer>
</body>
</html>
"""

_PAGE_BLOCK = """<article class="page">
  {img_html}
  <div class="page-body">
    <div class="page-num">Scene {num} of {total}</div>
    <h2 class="page-title">{scene_title}</h2>
    <p class="page-text">{scene_text}</p>
  </div>
</article>
"""


def _img_data_uri(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower() or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def render_html(project: Project) -> str:
    pages = []
    total = len(project.scenes)
    for i, scene in enumerate(sorted(project.scenes, key=lambda s: s.index), start=1):
        img_html = '<div class="missing-img">Illustration not generated yet</div>'
        if scene.image_path:
            img_file = project_store.ensure_image(project.id, Path(scene.image_path).name)
            if img_file is not None and img_file.exists():
                img_html = f'<img src="{_img_data_uri(img_file)}" alt="{html.escape(scene.title)}">'
        pages.append(
            _PAGE_BLOCK.format(
                img_html=img_html,
                num=i,
                total=total,
                scene_title=html.escape(scene.title or f"Scene {i}"),
                scene_text=html.escape(scene.text).replace("\n", "<br>"),
            )
        )

    return _PAGE_TEMPLATE.format(
        title=html.escape(project.title),
        synopsis=html.escape(project.synopsis),
        pages="\n".join(pages),
    )


def render_to_file(project: Project) -> Path:
    out_path = project_store._project_dir(project.id) / "storybook.html"  # noqa: SLF001
    out_path.write_text(render_html(project), encoding="utf-8")
    return out_path
