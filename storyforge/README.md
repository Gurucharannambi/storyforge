# StoryForge

A free, open-source, locally-runnable app that turns a one-line idea into a
fully illustrated storybook:

1. You describe an idea, genre, target age, art style, and number of scenes.
2. A local/open LLM writes a structured story — title, synopsis, characters,
   locations, objects, and scenes — as JSON.
3. Character/location/object descriptions are kept as persistent "story
   memory" so the same character looks the same in every picture.
4. Each scene gets a detailed image prompt built from that memory.
5. A free/open image model illustrates every scene.
6. Everything is assembled into an interactive storybook you can read in the
   browser or download as a single, self-contained HTML file.
7. Any scene's text or image can be regenerated on its own, without
   redoing the whole book.

No paid API keys are required to run this. Everything defaults to free
options, and every model is swappable.

---

## 1. Architecture at a glance

```
storyforge/
├── backend/
│   ├── config.py              # all settings, free defaults, env-overridable
│   ├── app.py                 # FastAPI app — thin HTTP layer only
│   ├── pipeline.py            # orchestrates: LLM -> story -> scenes -> images
│   ├── llm/                   # pluggable text-generation backends
│   │   ├── base.py            #   abstract interface + factory
│   │   ├── ollama_client.py   #   local Ollama (default)
│   │   └── openai_compat.py   #   any local OpenAI-compatible server
│   ├── story/
│   │   ├── schema.py          # Project / Scene / Character / Location models
│   │   ├── generator.py       # LLM prompting + JSON parsing/repair
│   │   ├── character_memory.py# persistent visual-consistency profiles
│   │   └── scene_planner.py   # builds each scene's image prompt
│   ├── image/                 # pluggable image-generation backends
│   │   ├── base.py            #   abstract interface + factory
│   │   ├── pollinations_backend.py   # free hosted, zero setup (default)
│   │   ├── diffusers_backend.py      # fully local SDXL / FLUX / SD1.5
│   │   └── automatic1111_backend.py  # talk to your own SD WebUI
│   └── storybook/
│       ├── project_store.py   # JSON-on-disk persistence, one folder/story
│       └── renderer.py        # renders the interactive/standalone HTML book
├── frontend/                  # plain HTML/CSS/JS single-page UI, no build step
├── data/projects/             # generated stories + images live here
├── requirements.txt
├── requirements-diffusers.txt # optional, only for fully-local image gen
├── .env.example
└── run.py
```

Every backend (LLM or image model) implements a small abstract interface
(`llm/base.py`, `image/base.py`) and is selected by name in config — adding
a new model to the app never requires touching the web layer or the story
logic.

---

## 2. Requirements

- **Python 3.10+**
- **A free way to run an LLM.** Recommended: [Ollama](https://ollama.com)
  (free, one-command install, runs fully offline).
- **A free way to generate images.** The default (`pollinations`) needs only
  an internet connection — no GPU, no install, no key. If you want fully
  offline image generation instead, you'll additionally need a GPU with
  ~6–12GB VRAM for `diffusers` (SDXL-Turbo/SD1.5 comfortably; FLUX wants
  more) or an already-running AUTOMATIC1111 install.

### Hardware guidance

| Setup                                   | What you need                                   |
|------------------------------------------|--------------------------------------------------|
| Text: Ollama + a 7-8B model              | 8GB+ RAM (CPU is fine, just slower than GPU)     |
| Text: Ollama + a 30B+ model              | 24GB+ RAM/VRAM, or a beefy CPU and patience       |
| Images: Pollinations (default)           | Just internet access — nothing local required     |
| Images: diffusers + SDXL-Turbo/SD1.5     | NVIDIA GPU 6GB+ VRAM, or Apple Silicon (MPS)      |
| Images: diffusers + full SDXL/FLUX       | 12GB+ VRAM recommended                            |
| Images: diffusers on CPU only            | Works, but minutes per image                      |

If you just want to try StoryForge with no setup beyond Ollama, the default
configuration (Ollama + Pollinations) needs no GPU at all.

---

## 3. Installation

```bash
# 1. Clone/unzip the project, then:
cd storyforge
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install the app's Python dependencies
pip install -r requirements.txt

# 3. (Optional) copy and edit the environment file
cp .env.example .env
```

### 3.1 Set up the free story-writing model (Ollama)

1. Install Ollama: https://ollama.com (macOS, Windows, Linux — all free).
2. Pull a model. Good free choices, roughly smallest/fastest to largest:
   ```bash
   ollama pull qwen2.5:7b-instruct      # default, good balance of speed/quality
   # or:
   ollama pull llama3.1:8b
   ollama pull mistral:7b-instruct
   ollama pull qwen2.5:32b              # stronger writing, needs more RAM/VRAM
   ```
   If/when a GLM-5.3-class open-weight model has an Ollama/GGUF build
   available, you can pull and use that the same way — just point
   `STORYFORGE_LLM_MODEL` at it.
3. Make sure Ollama is running (`ollama serve`, or just have the Ollama
   app open — on macOS/Windows it runs in the background automatically).
4. That's it — StoryForge talks to `http://localhost:11434` by default.

**Prefer LM Studio / text-generation-webui / vLLM instead?** Set
`STORYFORGE_LLM_BACKEND=openai_compat` and `STORYFORGE_LLM_BASE_URL` to
your server's OpenAI-compatible endpoint in `.env`.

### 3.2 Set up the illustration model

You don't have to do anything — the default backend (`pollinations`) is a
free, keyless, hosted API (backed by open models like FLUX) reachable the
moment you have internet access.

**Want fully offline image generation instead?**

```bash
pip install -r requirements-diffusers.txt
```
Then in `.env`:
```bash
STORYFORGE_IMAGE_BACKEND=diffusers
STORYFORGE_DIFFUSERS_MODEL=stabilityai/sdxl-turbo   # fast, ~6GB VRAM
# or: black-forest-labs/FLUX.1-schnell (Apache-2.0, needs more VRAM)
# or: runwayml/stable-diffusion-v1-5 (small, works on modest hardware)
```
The first run downloads the model weights from HuggingFace (free, no key
needed for these models) and caches them locally.

**Already run AUTOMATIC1111 / SD WebUI?** Start it with `--api` enabled,
then set `STORYFORGE_IMAGE_BACKEND=automatic1111` and `STORYFORGE_A1111_URL`
if it's not on the default `http://127.0.0.1:7860`.

### 3.3 Run it

```bash
python run.py
```

Then open **http://localhost:8000** in your browser.

The sidebar shows live status dots for both the story model and the
illustrator — if either isn't reachable yet, it tells you exactly what to
fix (e.g. "run `ollama pull qwen2.5:7b-instruct`").

---

## 4. Using StoryForge

1. Click **New story**, describe your idea, and pick genre / age / art
   style / number of scenes.
2. Click **Write the story** — the LLM generates the full structured story
   (this can take anywhere from a few seconds to a couple of minutes
   depending on your model and hardware).
3. You land on the storybook view with all scene text already written and
   the cast of characters listed at the top.
4. Click **Illustrate all scenes** to generate every picture, or illustrate
   scenes one at a time with **Illustrate this scene**. A progress bar
   tracks generation across the whole book.
5. Not happy with a scene? Use **Edit text** to rewrite just that scene
   (optionally with a direction, e.g. "make it funnier"), or **Repaint this
   scene** to regenerate just its illustration — neither touches the rest
   of the book.
6. When you're happy with it, click **Download storybook** to save a single
   self-contained `.html` file (images embedded) that opens in any browser,
   no server required — perfect for sharing or keeping.
7. Every story you make stays on your "shelf" in the sidebar (stored as
   plain JSON + images under `data/projects/`), so you can come back to it
   later.

---

## 5. Configuration reference

All settings live in `backend/config.py` and can be overridden via `.env`
or real environment variables — see `.env.example` for the full list,
including:

- `STORYFORGE_LLM_BACKEND` / `STORYFORGE_LLM_MODEL` / `OLLAMA_HOST`
- `STORYFORGE_LLM_BASE_URL` / `STORYFORGE_LLM_API_KEY` (for `openai_compat`)
- `STORYFORGE_IMAGE_BACKEND` / `STORYFORGE_POLLINATIONS_MODEL`
- `STORYFORGE_DIFFUSERS_MODEL` / `STORYFORGE_DIFFUSERS_DEVICE`
- `STORYFORGE_A1111_URL`
- `STORYFORGE_IMAGE_WIDTH` / `STORYFORGE_IMAGE_HEIGHT`
- `STORYFORGE_HOST` / `STORYFORGE_PORT`

You can also override the LLM/image backend and model **per story** by
passing `llm_backend`, `llm_model`, `image_backend`, or `image_model` in
the `POST /api/projects` request body — useful if you want to compare two
models against the same idea.

---

## 6. API reference (for scripting / extending)

| Method & path                                                    | Purpose                                  |
|-------------------------------------------------------------------|-------------------------------------------|
| `GET  /api/health`                                                | Check LLM + image backend availability   |
| `GET  /api/config`                                                | Current server-side model configuration  |
| `GET  /api/projects`                                              | List saved stories                       |
| `POST /api/projects`                                              | Create a new story (idea/genre/age/etc.) |
| `GET  /api/projects/{id}`                                         | Fetch a full story project               |
| `DELETE /api/projects/{id}`                                       | Delete a story                           |
| `POST /api/projects/{id}/scenes/{scene_id}/regenerate-text`       | Rewrite one scene's prose                |
| `POST /api/projects/{id}/images`                                  | Generate illustrations for every scene   |
| `GET  /api/projects/{id}/images/progress`                        | Poll illustration progress               |
| `POST /api/projects/{id}/scenes/{scene_id}/regenerate-image`      | Repaint one scene                        |
| `GET  /api/projects/{id}/storybook`                               | Rendered storybook HTML (inline)         |
| `GET  /api/projects/{id}/storybook/download`                      | Download the self-contained HTML book    |

Interactive Swagger docs are also available at **http://localhost:8000/docs**
once the server is running (FastAPI generates these automatically).

---

## 7. Troubleshooting

- **"Can't reach Ollama…"** — make sure `ollama serve` is running (or the
  Ollama desktop app is open), and that `OLLAMA_HOST` matches its address.
- **"Model isn't pulled yet"** — run the `ollama pull <model>` command it
  suggests.
- **The model's response wasn't valid JSON** — smaller/weaker local models
  occasionally produce malformed JSON. StoryForge automatically retries
  once with a stricter reminder; if it still fails, try a larger model
  (7B+ instruct models are noticeably more reliable at this than smaller
  ones).
- **Pollinations.ai request failed / timed out** — check your internet
  connection, or switch to `diffusers`/`automatic1111` for fully offline
  generation.
- **diffusers: "torch/diffusers aren't installed"** — run
  `pip install -r requirements-diffusers.txt`.
- **Images are slow** — that's expected on CPU; a GPU (CUDA or Apple
  Silicon MPS) speeds this up enormously, or just stick with the default
  hosted Pollinations backend.

---

## 8. Extending StoryForge

- **New text model:** add a class implementing `LLMBackend`
  (`backend/llm/base.py`) and register it in `get_llm_backend()`.
- **New image model:** add a class implementing `ImageBackend`
  (`backend/image/base.py`) and register it in `get_image_backend()`.
- **New frontend features:** the frontend is plain HTML/CSS/JS with no
  build step (`frontend/index.html`, `style.css`, `app.js`) — edit and
  refresh, no compilation needed.

---

## 9. License note

This project's own code is provided freely for you to use and modify. It
relies on third-party open models and tools (Ollama-served LLMs, FLUX/SDXL
family image models, Pollinations.ai, etc.) — check each one's own license
for your intended use (personal, commercial, etc.) before shipping a
product built on top of it.

---

## Database (local or cloud)

Stories and their pictures are stored in a real database via SQLAlchemy.

- **Local (default):** a SQLite file at `data/storyforge.db`. Nothing to set up.
  Open it with the free "DB Browser for SQLite" to see the `projects` and
  `images` tables. Old file-based stories are imported automatically.
- **Cloud:** create a free Postgres database (Supabase, Neon, ...) and put its
  connection string in `.env`:
  `STORYFORGE_DATABASE_URL=postgresql://user:password@host:5432/dbname`
  Stories and pictures are then saved in the cloud, so you can open the same
  library from any computer running StoryForge.

