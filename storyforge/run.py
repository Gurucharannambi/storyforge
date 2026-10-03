"""
Launch StoryForge.

    python run.py

Reads host/port from backend.config (which itself reads .env / env vars).
"""
import uvicorn

from backend import config

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host=config.HOST, port=config.PORT, reload=False)
