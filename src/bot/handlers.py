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
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
import logging
from io import BytesIO
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from src.config import settings
from src.services.exif import get_exif_gps
from src.services.clip_service import get_clip_service
from src.services.geocoding import get_location_from_gps, get_coords_from_zip
from src.services.map_service import generate_stone_map_image
from src.database.connection import async_session
from src.database.models import Stone, StoneHistory
from src.i18n import get_text, get_user_language, load_user_language, save_user_language, LANGUAGES

logger = logging.getLogger(__name__)

# Conversation states
WAITING_NAME = 1
WAITING_DESCRIPTION = 2
WAITING_LOCATION = 3

# Similarity threshold for finding existing stones
SIMILARITY_THRESHOLD = 0.82

# Pagination settings
STONES_PER_PAGE = 10


def t(key: str, update: Update, **kwargs) -> str:
    """Shortcut for get_text with user_id from update."""
    return get_text(key, update.effective_user.id, **kwargs)


def get_location_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get location keyboard with translated buttons."""
    lang = get_user_language(user_id)
    btn_location = get_text("btn_send_location", user_id)
    btn_zip = get_text("btn_enter_zip", user_id)
    btn_skip = get_text("btn_skip", user_id)

    return ReplyKeyboardMarkup(
        [[KeyboardButton(btn_location, request_location=True)],
         [btn_zip], [btn_skip]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def get_skip_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get skip keyboard with translated button."""
    btn_skip = get_text("btn_skip", user_id)
    return ReplyKeyboardMarkup([[btn_skip]], one_time_keyboard=True, resize_keyboard=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await load_user_language(update.effective_user.id)
    await update.message.reply_text(t("start", update))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await load_user_language(update.effective_user.id)
    await update.message.reply_text(t("help", update))


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lang command - show language selection."""
    await load_user_language(update.effective_user.id)
    keyboard = []
    for code, name in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"lang:{code}")])

    await update.message.reply_text(
        t("lang_select", update),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection callback."""
    query = update.callback_query
    await query.answer()

    lang_code = query.data.split(":")[1]
    await save_user_language(update.effective_user.id, lang_code)

    await query.edit_message_text(get_text("lang_changed", update.effective_user.id))


async def mine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mine command - show user's stones with pagination."""
    await load_user_language(update.effective_user.id)
    await show_my_stones(update, page=0)


async def show_my_stones(update: Update, page: int = 0, edit_message: bool = False) -> None:
    """Show user's stones with pagination."""
    user_id = update.effective_user.id

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .options(selectinload(Stone.history))
                .where(Stone.registered_by_user_id == user_id)
                .order_by(Stone.id)
            )
            stones = result.scalars().all()

            if not stones:
                text = get_text("no_stones", user_id)
                if edit_message:
                    await update.callback_query.edit_message_text(text)
                else:
                    await update.message.reply_text(text)
                return

            total_stones = len(stones)
            total_pages = (total_stones + STONES_PER_PAGE - 1) // STONES_PER_PAGE
            page = max(0, min(page, total_pages - 1))

            start_idx = page * STONES_PER_PAGE
            end_idx = min(start_idx + STONES_PER_PAGE, total_stones)
            page_stones = stones[start_idx:end_idx]

            # Header and page info only (stone info is on buttons)
            lines = [
                get_text("my_stones", user_id),
                "",
                get_text("page_info", user_id, page=page + 1, total=total_pages, count=total_stones)
            ]

            # Build keyboard: single wide info button with fixed-width text
            # Use low dot for padding (less intrusive than underscore)
            NBSP = "."  # Low dot for visual padding
            BUTTON_WIDTH = 30  # Total visible characters for alignment
            keyboard = []
            for stone in page_stones:
                history_count = len(stone.history)
                prefix = f"📋 #{stone.id} "
                suffix = f"({history_count})"
                # Calculate space for name (including padding)
                name_space = BUTTON_WIDTH - len(prefix) - len(suffix) - 1  # -1 for space before suffix
                if len(stone.name) > name_space:
                    # Truncate with ".."
                    name_display = stone.name[:name_space - 2] + ".."
                else:
                    # Pad with figure spaces to fixed width
                    padding = NBSP * (name_space - len(stone.name))
                    name_display = stone.name + padding
                button_text = f"{prefix}{name_display} {suffix}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"stone_info:{stone.id}"),
                ])

            # Navigation buttons
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(
                    get_text("btn_prev_page", user_id),
                    callback_data=f"mine_page:{page - 1}"
                ))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(
                    get_text("btn_next_page", user_id),
                    callback_data=f"mine_page:{page + 1}"
                ))
            if nav_buttons:
                keyboard.append(nav_buttons)

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            if edit_message:
                await update.callback_query.edit_message_text(
                    "\n".join(lines),
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    "\n".join(lines),
                    reply_markup=reply_markup
                )

    except Exception as e:
        logger.error(f"Error in show_my_stones: {e}", exc_info=True)
        text = get_text("error_generic", user_id)
        if edit_message:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)


async def mine_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination callback for /mine."""
    query = update.callback_query
    await query.answer()

    page = int(query.data.split(":")[1])
    await show_my_stones(update, page=page, edit_message=True)


async def stone_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle stone info callback from /mine list."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    stone_id = int(query.data.split(":")[1])

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .options(selectinload(Stone.history))
                .where(Stone.id == stone_id)
            )
            stone = result.scalar_one_or_none()

            if not stone:
                await query.message.reply_text(get_text("info_not_found", user_id, id=stone_id))
                return

            history_count = len(stone.history)
            info_text = get_text("stone_id", user_id, id=stone.id) + "\n"
            info_text += get_text("stone_name", user_id, name=stone.name) + "\n"
            if stone.description:
                info_text += get_text("stone_description", user_id, description=stone.description) + "\n"
            info_text += get_text("stone_seen", user_id, count=history_count)

            # Delete button for stone owner
            delete_button = None
            if stone.registered_by_user_id == user_id:
                delete_button = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        get_text("btn_delete", user_id),
                        callback_data=f"delete_ask:{stone.id}"
                    )
                ]])

            if stone.photo_file_id:
                await query.message.reply_photo(
                    photo=stone.photo_file_id,
                    caption=info_text,
                    reply_markup=delete_button
                )
            else:
                await query.message.reply_text(info_text, reply_markup=delete_button)

            if stone.history:
                await send_stone_map_from_query(query, stone.id)

    except Exception as e:
        logger.error(f"Error in stone_info_callback: {e}", exc_info=True)
        await query.message.reply_text(get_text("error_generic", user_id))


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info command - show stone details by ID."""
    user_id = update.effective_user.id
    await load_user_language(user_id)

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(t("info_usage", update))
        return

    try:
        stone_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(t("info_usage", update))
        return

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .options(selectinload(Stone.history))
                .where(Stone.id == stone_id)
            )
            stone = result.scalar_one_or_none()

            if not stone:
                await update.message.reply_text(t("info_not_found", update, id=stone_id))
                return

            history_count = len(stone.history)
            info_text = t("stone_id", update, id=stone.id) + "\n"
            info_text += t("stone_name", update, name=stone.name) + "\n"
            if stone.description:
                info_text += t("stone_description", update, description=stone.description) + "\n"
            info_text += t("stone_seen", update, count=history_count)

            if stone.photo_file_id:
                await update.message.reply_photo(
                    photo=stone.photo_file_id,
                    caption=info_text
                )
            else:
                await update.message.reply_text(info_text)

            if stone.history:
                await send_stone_map(update, stone.id)

    except Exception as e:
        logger.error(f"Error in info_command: {e}", exc_info=True)
        await update.message.reply_text(t("error_generic", update))


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command - delete a stone by ID."""
    user_id = update.effective_user.id
    await load_user_language(user_id)

    # Parse stone ID from command arguments
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(t("delete_usage", update))
        return

    try:
        stone_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(t("delete_usage", update))
        return

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .where(Stone.id == stone_id)
                .where(Stone.registered_by_user_id == user_id)
            )
            stone = result.scalar_one_or_none()

            if not stone:
                await update.message.reply_text(t("delete_not_found", update, id=stone_id))
                return

            # Ask for confirmation
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        get_text("btn_confirm_delete", user_id),
                        callback_data=f"delete_confirm:{stone_id}"
                    ),
                    InlineKeyboardButton(
                        get_text("btn_cancel_delete", user_id),
                        callback_data=f"delete_cancel:{stone_id}"
                    ),
                ]
            ])

            await update.message.reply_text(
                t("delete_confirm", update, name=stone.name, id=stone_id),
                reply_markup=keyboard
            )

    except Exception as e:
        logger.error(f"Error in delete_command: {e}", exc_info=True)
        await update.message.reply_text(t("error_generic", update))


async def delete_ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle delete request from /mine list - show confirmation dialog."""
    query = update.callback_query
    await query.answer()

    stone_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .where(Stone.id == stone_id)
                .where(Stone.registered_by_user_id == user_id)
            )
            stone = result.scalar_one_or_none()

            if not stone:
                await query.message.reply_text(get_text("delete_not_found", user_id, id=stone_id))
                return

            # Ask for confirmation
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        get_text("btn_confirm_delete", user_id),
                        callback_data=f"delete_confirm:{stone_id}"
                    ),
                    InlineKeyboardButton(
                        get_text("btn_cancel_delete", user_id),
                        callback_data=f"delete_cancel:{stone_id}"
                    ),
                ]
            ])

            await query.message.reply_text(
                get_text("delete_confirm", user_id, name=stone.name, id=stone_id),
                reply_markup=keyboard
            )

    except Exception as e:
        logger.error(f"Error in delete_ask_callback: {e}", exc_info=True)
        await query.message.reply_text(get_text("error_generic", user_id))


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle delete confirmation/cancellation callback."""
    query = update.callback_query
    await query.answer()

    action, stone_id_str = query.data.split(":")
    stone_id = int(stone_id_str)
    user_id = update.effective_user.id

    if action == "delete_cancel":
        await query.edit_message_text(get_text("delete_cancelled", user_id))
        return

    # Confirm deletion
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Stone)
                .where(Stone.id == stone_id)
                .where(Stone.registered_by_user_id == user_id)
            )
            stone = result.scalar_one_or_none()

            if not stone:
                await query.edit_message_text(get_text("delete_not_found", user_id, id=stone_id))
                return

            stone_name = stone.name

            # Delete history first (foreign key constraint)
            await session.execute(
                delete(StoneHistory).where(StoneHistory.stone_id == stone_id)
            )

            # Delete stone
            await session.execute(
                delete(Stone).where(Stone.id == stone_id)
            )

            await session.commit()

            await query.edit_message_text(get_text("delete_success", user_id, name=stone_name))
            logger.info(f"User {user_id} deleted stone {stone_id} ({stone_name})")

    except Exception as e:
        logger.error(f"Error in delete_callback: {e}", exc_info=True)
        await query.edit_message_text(get_text("error_generic", user_id))


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo message - detect stone, search or register."""
    try:
        context.user_data.clear()
        await load_user_language(update.effective_user.id)

        await update.message.reply_text(t("analyzing", update))

        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await file.download_as_bytearray())
        logger.info(f"Downloaded photo: {len(image_bytes)} bytes")

        clip = get_clip_service()
        crop_result = clip.smart_crop_stone(image_bytes)

        if crop_result is None:
            await update.message.reply_text(t("stone_not_found", update))
            return ConversationHandler.END

        cropped_bytes, thumbnail_bytes = crop_result

        is_stone, confidence = clip.is_stone(cropped_bytes)
        logger.info(f"Stone detection: is_stone={is_stone}, confidence={confidence:.4f}")

        if not is_stone:
            await update.message.reply_text(t("stone_not_recognized", update))
            return ConversationHandler.END

        embedding = clip.get_embedding(cropped_bytes)
        logger.info(f"Generated embedding: {len(embedding)} dimensions")

        existing_stone = await find_similar_stone(embedding)

        context.user_data["photo_file_id"] = photo.file_id
        context.user_data["embedding"] = embedding
        context.user_data["thumbnail_bytes"] = thumbnail_bytes
        context.user_data["latitude"] = None
        context.user_data["longitude"] = None
        context.user_data["zip_code"] = None
        context.user_data["location"] = None

        if existing_stone:
            context.user_data["found_stone_id"] = existing_stone.id
            context.user_data["existing_stone"] = existing_stone

            history_count = len(existing_stone.history)
            info_text = t("stone_found", update) + "\n\n"
            info_text += t("stone_id", update, id=existing_stone.id) + "\n"
            info_text += t("stone_name", update, name=existing_stone.name) + "\n"
            if existing_stone.description:
                info_text += t("stone_description", update, description=existing_stone.description) + "\n"
            info_text += t("stone_seen", update, count=history_count)
            info_text += t("send_location_prompt", update)

            await update.message.reply_photo(
                photo=BytesIO(thumbnail_bytes),
                caption=t("cropped_stone", update)
            )

            await update.message.reply_text(
                info_text,
                reply_markup=get_location_keyboard(update.effective_user.id)
            )
            return WAITING_LOCATION
        else:
            await update.message.reply_photo(
                photo=BytesIO(thumbnail_bytes),
                caption=t("cropped_stone", update)
            )
            await update.message.reply_text(
                t("new_stone", update) + "\n\n" + t("enter_name", update)
            )
            return WAITING_NAME

    except Exception as e:
        logger.error(f"Error in handle_photo: {e}", exc_info=True)
        await update.message.reply_text(t("error_photo", update))
        return ConversationHandler.END


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle stone name input."""
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text(t("name_too_short", update))
        return WAITING_NAME

    context.user_data["name"] = name
    await update.message.reply_text(
        t("add_description", update, name=name),
        reply_markup=get_skip_keyboard(update.effective_user.id),
    )
    return WAITING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle description input."""
    text = update.message.text.strip()
    btn_skip = get_text("btn_skip", update.effective_user.id)

    description = None if text == btn_skip else text
    context.user_data["description"] = description

    await update.message.reply_text(
        t("send_location_prompt", update).strip(),
        reply_markup=get_location_keyboard(update.effective_user.id),
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

            try:
                geo_data = await get_location_from_gps(lat, lon)
                if geo_data:
                    context.user_data["zip_code"] = geo_data.get("zip_code")
                    context.user_data["location"] = geo_data
            except Exception as e:
                logger.error(f"Geocoding failed: {e}")

        existing_stone = context.user_data.get("existing_stone")

        if existing_stone:
            await add_to_history(
                stone_id=existing_stone.id,
                user_id=update.effective_user.id,
                photo_file_id=context.user_data["photo_file_id"],
                latitude=context.user_data.get("latitude"),
                longitude=context.user_data.get("longitude"),
                zip_code=context.user_data.get("zip_code"),
            )
            logger.info(f"Added to history for stone_id={existing_stone.id}")

            msg = t("saved_to_history", update)
            if context.user_data.get("location"):
                loc = context.user_data["location"]
                loc_str = ""
                if loc.get("city"):
                    loc_str += loc["city"]
                if loc.get("zip_code"):
                    loc_str += f", {loc['zip_code']}"
                if loc.get("country"):
                    loc_str += f", {loc['country']}"
                msg = t("location_label", update, location=loc_str) + "\n" + msg

            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
            await send_stone_map(update, existing_stone.id)
        else:
            stone_id = await register_stone(context.user_data, update.effective_user.id)
            logger.info(f"Registered new stone: {context.user_data['name']} (ID: {stone_id})")

            msg = t("stone_registered", update, name=context.user_data['name'], id=stone_id)
            if context.user_data.get("location"):
                loc = context.user_data["location"]
                loc_str = ""
                if loc.get("city"):
                    loc_str += loc["city"]
                if loc.get("zip_code"):
                    loc_str += f", {loc['zip_code']}"
                if loc.get("country"):
                    loc_str += f", {loc['country']}"
                msg += "\n" + t("location_label", update, location=loc_str)

            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_location: {e}", exc_info=True)
        await update.message.reply_text(
            t("error_generic", update),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


async def handle_skip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skip location button."""
    try:
        existing_stone = context.user_data.get("existing_stone")

        if existing_stone:
            await add_to_history(
                stone_id=existing_stone.id,
                user_id=update.effective_user.id,
                photo_file_id=context.user_data["photo_file_id"],
            )
            logger.info(f"Added to history (no location) for stone_id={existing_stone.id}")
            await update.message.reply_text(
                t("saved_no_location", update),
                reply_markup=ReplyKeyboardRemove(),
            )
            await send_stone_map(update, existing_stone.id)
        else:
            stone_id = await register_stone(context.user_data, update.effective_user.id)
            logger.info(f"Registered new stone (no location): {context.user_data['name']} (ID: {stone_id})")
            await update.message.reply_text(
                t("stone_registered", update, name=context.user_data['name'], id=stone_id),
                reply_markup=ReplyKeyboardRemove(),
            )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_skip_location: {e}", exc_info=True)
        await update.message.reply_text(
            t("error_generic", update),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


async def send_stone_map(update: Update, stone_id: int) -> None:
    """Send map image for stone history."""
    await _send_stone_map_impl(update.message, update.effective_user.id, stone_id)


async def send_stone_map_from_query(query, stone_id: int) -> None:
    """Send map image for stone history from callback query."""
    await _send_stone_map_impl(query.message, query.from_user.id, stone_id)


async def _send_stone_map_impl(message, user_id: int, stone_id: int) -> None:
    """Internal implementation for sending stone map."""
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
                    if settings.webapp_base_url:
                        webapp_url = f"{settings.webapp_base_url}/static/index.html?stone_id={stone_id}"
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton(
                                get_text("interactive_map", user_id),
                                web_app=WebAppInfo(url=webapp_url)
                            )]
                        ])
                        await message.reply_photo(
                            photo=BytesIO(map_image),
                            caption=get_text("map_caption", user_id),
                            reply_markup=keyboard,
                        )
                    else:
                        await message.reply_photo(
                            photo=BytesIO(map_image),
                            caption=get_text("map_caption", user_id)
                        )
    except Exception as e:
        logger.error(f"Error sending map: {e}", exc_info=True)


async def handle_location_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle unexpected input in WAITING_LOCATION state."""
    text = update.message.text.strip() if update.message.text else ""
    text_lower = text.lower()
    user_id = update.effective_user.id

    # Get translated button texts for comparison
    btn_skip = get_text("btn_skip", user_id).lower()
    btn_zip = get_text("btn_enter_zip", user_id).lower()

    # Accept variations of "skip" in all languages
    skip_variants = ["пропустить", "skip", "pomiń", "пропуск", "-", "нет", "no", "nie"]
    if text_lower == btn_skip or text_lower in skip_variants:
        return await handle_skip_location(update, context)

    # User wants to enter ZIP code
    zip_variants = ["ввести zip код", "ввести zip", "zip", "zip код", "enter zip", "wpisz kod"]
    if text_lower == btn_zip or text_lower in zip_variants:
        await update.message.reply_text(
            t("enter_zip", update),
            reply_markup=get_skip_keyboard(user_id),
        )
        return WAITING_LOCATION

    # Check if input looks like a ZIP code
    if len(text) >= 3 and len(text) <= 10 and text.replace("-", "").replace(" ", "").isalnum():
        coords = await get_coords_from_zip(text)
        lat, lon = coords if coords else (None, None)

        context.user_data["zip_code"] = text
        context.user_data["latitude"] = lat
        context.user_data["longitude"] = lon

        existing_stone = context.user_data.get("existing_stone")

        if existing_stone:
            await add_to_history(
                stone_id=existing_stone.id,
                user_id=user_id,
                photo_file_id=context.user_data["photo_file_id"],
                latitude=lat,
                longitude=lon,
                zip_code=text,
            )
            msg = t("saved_to_history", update) + "\n" + t("zip_label", update, zip=text)
            if lat and lon:
                msg += "\n" + t("coords_label", update, lat=lat, lon=lon)
            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
            await send_stone_map(update, existing_stone.id)
        else:
            stone_id = await register_stone(context.user_data, user_id)
            msg = t("stone_registered", update, name=context.user_data['name'], id=stone_id)
            msg += "\n" + t("zip_label", update, zip=text)
            if lat and lon:
                msg += "\n" + t("coords_label", update, lat=lat, lon=lon)
            await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END

    await update.message.reply_text(t("location_prompt", update))
    return WAITING_LOCATION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text(t("cancelled", update), reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def find_similar_stone(embedding: list[float]) -> Stone | None:
    """Find stone with similar embedding using cosine similarity.

    Uses HNSW index for O(log n) search instead of O(n).
    """
    try:
        async with async_session() as session:
            # Convert embedding to PostgreSQL array format
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            # Use raw SQL with text() to properly pass vector parameter
            # This allows pgvector to use the HNSW index for fast ANN search
            from sqlalchemy import text

            result = await session.execute(
                text("""
                    SELECT id, name, description, photo_file_id, embedding,
                           registered_by_user_id, created_at,
                           1 - (embedding <=> :embedding::vector) as similarity
                    FROM stones
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> :embedding::vector
                    LIMIT 1
                """),
                {"embedding": embedding_str}
            )
            row = result.fetchone()

            if not row:
                return None

            similarity = row.similarity

            if similarity >= SIMILARITY_THRESHOLD:
                # Load the full Stone object with history
                stone_result = await session.execute(
                    select(Stone)
                    .options(selectinload(Stone.history))
                    .where(Stone.id == row.id)
                )
                stone = stone_result.scalar_one()
                logger.info(f"Match: {stone.name} (sim={similarity:.4f})")
                return stone
            else:
                logger.info(f"No match (best={similarity:.4f}, threshold={SIMILARITY_THRESHOLD})")
                return None

    except Exception as e:
        logger.error(f"Similarity search error: {e}", exc_info=True)
        return None


async def register_stone(data: dict, user_id: int) -> int:
    """Register new stone and add first history entry. Returns stone ID."""
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
        return stone.id


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
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location_fallback),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("mine", mine_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang:"))
    app.add_handler(CallbackQueryHandler(mine_page_callback, pattern="^mine_page:"))
    app.add_handler(CallbackQueryHandler(stone_info_callback, pattern="^stone_info:"))
    app.add_handler(CallbackQueryHandler(delete_ask_callback, pattern="^delete_ask:"))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern="^delete_confirm:|^delete_cancel:"))
    app.add_handler(conv_handler)
