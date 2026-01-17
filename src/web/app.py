import logging
from pathlib import Path
from threading import Thread

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

logger = logging.getLogger(__name__)

app = FastAPI(title="Kamyczki Bot Web")

# CORS for Telegram Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router, prefix="/api")

# Static files (HTML, JS, CSS)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def start_web_server(host: str = "0.0.0.0", port: int = 8080) -> Thread:
    """Start web server in a background thread."""
    def run():
        # Use asyncio loop instead of uvloop to avoid conflict with telegram bot
        uvicorn.run(app, host=host, port=port, log_level="info", loop="asyncio")

    thread = Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"Web server started on http://{host}:{port}")
    return thread
