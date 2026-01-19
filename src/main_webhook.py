"""Webhook mode entry point for Cloud Run / serverless deployment."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update, BotCommand
from telegram.ext import Application

from src.config import settings
from src.bot import setup_handlers
from src.database import init_db
from src.services.ml_service import preload_models

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress noisy httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)

# Global application instance
ptb_app: Application = None


async def setup_bot_commands(bot):
    """Set up bot command menus for all languages."""
    commands_pl = [
        BotCommand("start", "Rozpocznij"),
        BotCommand("help", "Pomoc"),
        BotCommand("mine", "Moje kamyki"),
        BotCommand("lang", "Zmień język"),
        BotCommand("cancel", "Anuluj"),
    ]
    commands_en = [
        BotCommand("start", "Start"),
        BotCommand("help", "Help"),
        BotCommand("mine", "My rocks"),
        BotCommand("lang", "Change language"),
        BotCommand("cancel", "Cancel"),
    ]
    commands_ru = [
        BotCommand("start", "Начать"),
        BotCommand("help", "Справка"),
        BotCommand("mine", "Мои камни"),
        BotCommand("lang", "Сменить язык"),
        BotCommand("cancel", "Отмена"),
    ]

    await bot.set_my_commands(commands_pl)
    await bot.set_my_commands(commands_pl, language_code="pl")
    await bot.set_my_commands(commands_en, language_code="en")
    await bot.set_my_commands(commands_ru, language_code="ru")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global ptb_app

    logger.info("Starting webhook bot...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Pre-load ML models (skipped if using Modal)
    preload_models()

    # Build PTB application
    ptb_app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .updater(None)  # No updater for webhook mode
        .build()
    )

    setup_handlers(ptb_app)
    await ptb_app.initialize()
    await ptb_app.start()

    # Set up bot commands
    await setup_bot_commands(ptb_app.bot)
    logger.info("Bot commands menu set")

    # Set webhook
    webhook_url = f"{settings.webhook_url}/webhook"
    await ptb_app.bot.set_webhook(
        url=webhook_url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=True,
    )
    logger.info(f"Webhook set: {webhook_url}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await ptb_app.stop()
    await ptb_app.shutdown()


# Create FastAPI app
app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """Handle incoming Telegram webhook updates."""
    # Verify secret token
    if settings.webhook_secret:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if token != settings.webhook_secret:
            logger.warning("Invalid webhook secret token")
            return Response(status_code=403)

    # Process update
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)

    return Response(status_code=200)


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "kamyczki-bot", "mode": "webhook"}


# Include Mini App routes
from src.web.routes import router as web_router
app.include_router(web_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.web_port)
