import asyncio
import logging
from telegram import BotCommand
from telegram.ext import Application

from src.config import settings
from src.bot import setup_handlers
from src.database import init_db
from src.web import start_web_server
from src.services.clip_service import get_clip_service

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress noisy httpx logs (telegram API polling)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    """Initialize services after bot startup."""
    await init_db()
    logger.info("Database initialized")

    # Pre-load CLIP model (heavy, do it once at startup)
    logger.info("Loading CLIP model...")
    get_clip_service()
    logger.info("CLIP model loaded")

    # Set bot commands menu for each language
    # Note: /info and /delete require ID argument, so they're not in menu
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

    # Default (Polish)
    await application.bot.set_my_commands(commands_pl)
    # Language-specific menus
    await application.bot.set_my_commands(commands_pl, language_code="pl")
    await application.bot.set_my_commands(commands_en, language_code="en")
    await application.bot.set_my_commands(commands_ru, language_code="ru")
    logger.info("Bot commands menu set for all languages")


def main() -> None:
    """Start the bot."""
    # Create event loop before uvicorn imports uvloop
    asyncio.set_event_loop(asyncio.new_event_loop())

    # Start web server for Mini App
    start_web_server(port=settings.web_port)

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    setup_handlers(app)

    logger.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
