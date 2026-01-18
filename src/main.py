import asyncio
import logging
from telegram import BotCommand
from telegram.ext import Application

from src.config import settings
from src.bot import setup_handlers
from src.database import init_db
from src.web import start_web_server

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

    # Set bot commands menu
    commands = [
        BotCommand("start", "Rozpocznij / Start / Начать"),
        BotCommand("help", "Pomoc / Help / Справка"),
        BotCommand("mine", "Moje kamyki / My rocks / Мои камни"),
        BotCommand("info", "Info o kamyku / Rock info / Инфо о камне"),
        BotCommand("delete", "Usuń kamyk / Delete rock / Удалить камень"),
        BotCommand("lang", "Zmień język / Change language / Сменить язык"),
        BotCommand("cancel", "Anuluj / Cancel / Отмена"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu set")


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
