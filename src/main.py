import logging
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


async def post_init(application: Application) -> None:
    """Initialize services after bot startup."""
    await init_db()
    logger.info("Database initialized")


def main() -> None:
    """Start the bot."""
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
