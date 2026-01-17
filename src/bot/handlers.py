from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
import logging
from io import BytesIO
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.services.exif import get_exif_gps
from src.services.clip_service import get_clip_service
from src.services.geocoding import get_location_from_gps, get_coords_from_zip
from src.services.map_service import generate_stone_map_image
from src.database.connection import async_session
from src.database.models import Stone, StoneHistory

logger = logging.getLogger(__name__)

# Conversation states
WAITING_NAME = 1
WAITING_DESCRIPTION = 2
WAITING_LOCATION = 3

# Similarity threshold for finding existing stones
# 0.70 - false positives (similar background)
# 0.80 - false positives (colorful stones)
# 0.88 - too strict, misses real matches
# 0.85 - still too strict (Стрекоза: 0.8491)
# 0.84 - optimal: catches 0.8491, rejects 0.8235
SIMILARITY_THRESHOLD = 0.82


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Привет! Я kamyczki-bot.\n\n"
        "Отправь мне фото камня:\n"
        "• Если камень уже зарегистрирован — покажу информацию\n"
        "• Если новый — помогу зарегистрировать"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать справку\n"
        "/mine - Мои камни\n"
        "/cancel - Отменить текущую операцию\n\n"
        "Просто отправь фото камня!"
    )


async def mine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mine command - show user's stones."""
    user_id = update.effective_user.id

    try:
        async with async_session() as session:
            # Get stones registered by user
            result = await session.execute(
                select(Stone)
                .options(selectinload(Stone.history))
                .where(Stone.registered_by_user_id == user_id)
            )
            stones = result.scalars().all()

            if not stones:
                await update.message.reply_text(
                    "У тебя пока нет зарегистрированных камней.\n\n"
                    "Отправь фото камня, чтобы зарегистрировать!"
                )
                return

            lines = ["🪨 Твои камни:\n"]
            for stone in stones:
                history_count = len(stone.history)
                lines.append(f"• {stone.name} ({history_count})")

            await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in mine_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo message - detect stone, search or register."""
    try:
        # Clear previous session data
        context.user_data.clear()

        await update.message.reply_text("Анализирую изображение...")

        # Download photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await file.download_as_bytearray())
        logger.info(f"Downloaded photo: {len(image_bytes)} bytes")

        # Smart crop stone from background
        clip = get_clip_service()
        crop_result = clip.smart_crop_stone(image_bytes)

        if crop_result is None:
            await update.message.reply_text(
                "❌ Камень не найден на изображении.\n\n"
                "Убедитесь, что камень хорошо виден на фото и попробуйте снова."
            )
            return ConversationHandler.END

        cropped_bytes, thumbnail_bytes = crop_result

        # Check if cropped image is a painted stone
        is_stone, confidence = clip.is_stone(cropped_bytes)
        logger.info(f"Stone detection: is_stone={is_stone}, confidence={confidence:.4f}")

        if not is_stone:
            await update.message.reply_text(
                "❌ Камень не распознан.\n\n"
                "Убедитесь, что на фото плоский камень с рисунком, "
                "и попробуйте снова."
            )
            return ConversationHandler.END

        # Get embedding from cropped image for better similarity search
        embedding = clip.get_embedding(cropped_bytes)
        logger.info(f"Generated embedding: {len(embedding)} dimensions")

        # Search for similar stone in database
        existing_stone = await find_similar_stone(embedding)

        # Store data in context
        context.user_data["photo_file_id"] = photo.file_id
        context.user_data["embedding"] = embedding
        context.user_data["thumbnail_bytes"] = thumbnail_bytes
        context.user_data["latitude"] = None
        context.user_data["longitude"] = None
        context.user_data["zip_code"] = None
        context.user_data["location"] = None

        if existing_stone:
            # Stone found - show info and add to history
            context.user_data["found_stone_id"] = existing_stone.id
            context.user_data["existing_stone"] = existing_stone

            history_count = len(existing_stone.history)
            info_text = (
                f"✅ Камень найден!\n\n"
                f"📛 Имя: {existing_stone.name}\n"
            )
            if existing_stone.description:
                info_text += f"📝 Описание: {existing_stone.description}\n"
            info_text += f"📍 Замечен {history_count} раз(а)\n"
            info_text += "\nОтправь геолокацию или введи ZIP код:"

            # Send cropped thumbnail
            await update.message.reply_photo(
                photo=BytesIO(thumbnail_bytes),
                caption="📷 Распознанный камень"
            )

            # Ask for location
            location_keyboard = ReplyKeyboardMarkup(
                [[KeyboardButton("📍 Отправить местоположение", request_location=True)],
                 ["Ввести ZIP код"], ["Пропустить"]],
                one_time_keyboard=True,
                resize_keyboard=True,
            )
            await update.message.reply_text(info_text, reply_markup=location_keyboard)
            return WAITING_LOCATION
        else:
            # New stone - start registration
            # Send cropped thumbnail
            await update.message.reply_photo(
                photo=BytesIO(thumbnail_bytes),
                caption="📷 Распознанный камень"
            )
            await update.message.reply_text(
                "🆕 Новый камень!\n\n"
                "Введите имя для камня:"
            )
            return WAITING_NAME

    except Exception as e:
        logger.error(f"Error in handle_photo: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке фото. Попробуйте снова."
        )
        return ConversationHandler.END


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle stone name input."""
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text("Имя слишком короткое. Введите имя (минимум 2 символа):")
        return WAITING_NAME

    context.user_data["name"] = name
    await update.message.reply_text(
        f"Имя: {name}\n\n"
        "Добавить описание? (или нажми «Пропустить»)",
        reply_markup=ReplyKeyboardMarkup([["Пропустить"]], one_time_keyboard=True, resize_keyboard=True),
    )
    return WAITING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle description input."""
    text = update.message.text.strip()
    description = None if text == "Пропустить" else text
    context.user_data["description"] = description

    # Ask for location
    location_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить местоположение", request_location=True)],
         ["Ввести ZIP код"], ["Пропустить"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "Отправь геолокацию или введи ZIP код:",
        reply_markup=location_keyboard,
    )
    return WAITING_LOCATION


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle location message."""
    try:
        location = update.message.location

        if location:
            lat, lon = location.latitude, location.longitude
            context.user_data["latitude"] = lat
            context.user_data["longitude"] = lon
            logger.info(f"Received location: {lat}, {lon}")

            # Get address from coordinates
            try:
                geo_data = await get_location_from_gps(lat, lon)
                if geo_data:
                    context.user_data["zip_code"] = geo_data.get("zip_code")
                    context.user_data["location"] = geo_data
            except Exception as e:
                logger.error(f"Geocoding failed: {e}")

        # Check if this is for existing stone or new registration
        existing_stone = context.user_data.get("existing_stone")

        if existing_stone:
            # Add to history for existing stone
            await add_to_history(
                stone_id=existing_stone.id,
                user_id=update.effective_user.id,
                photo_file_id=context.user_data["photo_file_id"],
                latitude=context.user_data.get("latitude"),
                longitude=context.user_data.get("longitude"),
                zip_code=context.user_data.get("zip_code"),
            )
            logger.info(f"Added to history for stone_id={existing_stone.id}")

            msg = "✅ Сохранено в истории!"
            if context.user_data.get("location"):
                loc = context.user_data["location"]
                loc_str = ""
                if loc.get("city"):
                    loc_str += loc["city"]
                if loc.get("zip_code"):
                    loc_str += f", {loc['zip_code']}"
                if loc.get("country"):
                    loc_str += f", {loc['country']}"
                msg = f"🗺 Местоположение: {loc_str}\n" + msg

            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

            # Send map with updated history
            await send_stone_map(update, existing_stone.id)
        else:
            # Register new stone
            await register_stone(context.user_data, update.effective_user.id)
            logger.info(f"Registered new stone: {context.user_data['name']}")

            msg = f"✅ Камень «{context.user_data['name']}» зарегистрирован!"
            if context.user_data.get("location"):
                loc = context.user_data["location"]
                loc_str = ""
                if loc.get("city"):
                    loc_str += loc["city"]
                if loc.get("zip_code"):
                    loc_str += f", {loc['zip_code']}"
                if loc.get("country"):
                    loc_str += f", {loc['country']}"
                msg += f"\n🗺 Местоположение: {loc_str}"

            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_location: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте снова.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


async def handle_skip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skip location button."""
    try:
        existing_stone = context.user_data.get("existing_stone")

        if existing_stone:
            # Add to history without location
            await add_to_history(
                stone_id=existing_stone.id,
                user_id=update.effective_user.id,
                photo_file_id=context.user_data["photo_file_id"],
            )
            logger.info(f"Added to history (no location) for stone_id={existing_stone.id}")
            await update.message.reply_text(
                "✅ Сохранено в истории (без местоположения)!",
                reply_markup=ReplyKeyboardRemove(),
            )
            # Send map
            await send_stone_map(update, existing_stone.id)
        else:
            # Register new stone without location
            await register_stone(context.user_data, update.effective_user.id)
            logger.info(f"Registered new stone (no location): {context.user_data['name']}")
            await update.message.reply_text(
                f"✅ Камень «{context.user_data['name']}» зарегистрирован!",
                reply_markup=ReplyKeyboardRemove(),
            )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_skip_location: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте снова.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


async def send_stone_map(update: Update, stone_id: int) -> None:
    """Send map image for stone history."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .options(selectinload(Stone.history))
                .where(Stone.id == stone_id)
            )
            stone = result.scalar_one_or_none()

            if stone and stone.history:
                map_image = generate_stone_map_image(stone.history, stone.name)
                if map_image:
                    # Check if Mini App URL is configured
                    if settings.webapp_base_url:
                        webapp_url = f"{settings.webapp_base_url}/static/index.html?stone_id={stone_id}"
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton(
                                "🗺 Интерактивная карта",
                                web_app=WebAppInfo(url=webapp_url)
                            )]
                        ])
                        await update.message.reply_photo(
                            photo=BytesIO(map_image),
                            caption="🗺 Карта перемещений\n🟢 старт → 🔴 финиш",
                            reply_markup=keyboard,
                        )
                    else:
                        await update.message.reply_photo(
                            photo=BytesIO(map_image),
                            caption="🗺 Карта перемещений\n🟢 старт → 🔴 финиш"
                        )
    except Exception as e:
        logger.error(f"Error sending map: {e}", exc_info=True)


async def handle_location_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle unexpected input in WAITING_LOCATION state."""
    text = update.message.text.strip() if update.message.text else ""
    text_lower = text.lower()

    # Accept variations of "skip"
    if text_lower in ["пропустить", "skip", "пропуск", "-", "нет"]:
        return await handle_skip_location(update, context)

    # User wants to enter ZIP code
    if text_lower in ["ввести zip код", "ввести zip", "zip", "zip код"]:
        await update.message.reply_text(
            "Введи почтовый индекс (ZIP код):",
            reply_markup=ReplyKeyboardMarkup([["Пропустить"]], one_time_keyboard=True, resize_keyboard=True),
        )
        return WAITING_LOCATION

    # Check if input looks like a ZIP code (alphanumeric, 3-10 chars)
    if len(text) >= 3 and len(text) <= 10 and text.replace("-", "").replace(" ", "").isalnum():
        # Try to get coordinates from ZIP code
        coords = await get_coords_from_zip(text)
        lat, lon = coords if coords else (None, None)

        context.user_data["zip_code"] = text
        context.user_data["latitude"] = lat
        context.user_data["longitude"] = lon

        existing_stone = context.user_data.get("existing_stone")

        if existing_stone:
            # Add to history for existing stone
            await add_to_history(
                stone_id=existing_stone.id,
                user_id=update.effective_user.id,
                photo_file_id=context.user_data["photo_file_id"],
                latitude=lat,
                longitude=lon,
                zip_code=text,
            )
            msg = f"✅ Сохранено в истории!\n📮 ZIP: {text}"
            if lat and lon:
                msg += f"\n📍 Координаты: {lat:.4f}, {lon:.4f}"
            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
            await send_stone_map(update, existing_stone.id)
        else:
            # Register new stone
            await register_stone(context.user_data, update.effective_user.id)
            msg = f"✅ Камень «{context.user_data['name']}» зарегистрирован!\n📮 ZIP: {text}"
            if lat and lon:
                msg += f"\n📍 Координаты: {lat:.4f}, {lon:.4f}"
            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END

    await update.message.reply_text(
        "Отправь геолокацию, введи ZIP код или нажми «Пропустить»."
    )
    return WAITING_LOCATION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text("Операция отменена.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def find_similar_stone(embedding: list[float]) -> Stone | None:
    """Find stone with similar embedding using cosine similarity."""
    try:
        async with async_session() as session:
            # Get all stones with embeddings
            result = await session.execute(
                select(Stone)
                .options(selectinload(Stone.history))
                .where(Stone.embedding.isnot(None))
            )
            stones = result.scalars().all()

            if not stones:
                return None

            # Calculate similarity for each stone
            best_stone = None
            best_similarity = -1.0

            for stone in stones:
                distance_result = await session.execute(
                    select(Stone.embedding.cosine_distance(embedding))
                    .where(Stone.id == stone.id)
                )
                distance = distance_result.scalar_one()
                similarity = 1 - distance

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_stone = stone

            if best_stone and best_similarity >= SIMILARITY_THRESHOLD:
                logger.info(f"Match: {best_stone.name} (sim={best_similarity:.4f})")
                return best_stone
            else:
                logger.info(f"No match (best={best_similarity:.4f}, threshold={SIMILARITY_THRESHOLD})")
                return None

    except Exception as e:
        logger.error(f"Similarity search error: {e}", exc_info=True)
        return None


async def register_stone(data: dict, user_id: int) -> None:
    """Register new stone and add first history entry."""
    async with async_session() as session:
        stone = Stone(
            name=data["name"],
            description=data.get("description"),
            photo_file_id=data["photo_file_id"],
            embedding=data["embedding"],
            registered_by_user_id=user_id,
        )
        session.add(stone)
        await session.flush()

        history = StoneHistory(
            stone_id=stone.id,
            telegram_user_id=user_id,
            photo_file_id=data["photo_file_id"],
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            zip_code=data.get("zip_code"),
        )
        session.add(history)
        await session.commit()


async def add_to_history(
    stone_id: int,
    user_id: int,
    photo_file_id: str,
    latitude: float = None,
    longitude: float = None,
    zip_code: str = None,
) -> None:
    """Add entry to stone history."""
    async with async_session() as session:
        history = StoneHistory(
            stone_id=stone_id,
            telegram_user_id=user_id,
            photo_file_id=photo_file_id,
            latitude=latitude,
            longitude=longitude,
            zip_code=zip_code,
        )
        session.add(history)
        await session.commit()


def setup_handlers(app: Application) -> None:
    """Register all handlers."""
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, handle_photo)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            WAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)],
            WAITING_LOCATION: [
                MessageHandler(filters.LOCATION, handle_location),
                MessageHandler(filters.Regex("^Пропустить$"), handle_skip_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location_fallback),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mine", mine_command))
    app.add_handler(conv_handler)
