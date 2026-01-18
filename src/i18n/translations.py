"""Simple i18n system for the bot."""

from typing import Dict

# Supported languages
LANGUAGES = {
    "pl": "Polski",
    "en": "English",
    "ru": "Русский",
}

DEFAULT_LANGUAGE = "pl"

# User language preferences (in-memory, resets on restart)
# TODO: persist to database for production use
_user_languages: Dict[int, str] = {}


def get_user_language(user_id: int) -> str:
    """Get user's preferred language."""
    return _user_languages.get(user_id, DEFAULT_LANGUAGE)


def set_user_language(user_id: int, lang: str) -> None:
    """Set user's preferred language."""
    if lang in LANGUAGES:
        _user_languages[user_id] = lang


def get_text(key: str, user_id: int, **kwargs) -> str:
    """Get translated text for user's language."""
    lang = get_user_language(user_id)
    text = TEXTS.get(lang, TEXTS[DEFAULT_LANGUAGE]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


# Translation strings
TEXTS = {
    "pl": {
        # Commands
        "start": (
            "Cześć! Jestem kamyczki-bot.\n\n"
            "Wyślij mi zdjęcie kamyka:\n"
            "• Jeśli kamyk jest już zarejestrowany — pokażę informacje\n"
            "• Jeśli nowy — pomogę zarejestrować"
        ),
        "help": (
            "Dostępne komendy:\n"
            "/start - Rozpocznij pracę z botem\n"
            "/help - Pokaż pomoc\n"
            "/mine - Moje kamyki\n"
            "/info <id> - Informacje o kamyku\n"
            "/delete <id> - Usuń kamyk\n"
            "/lang - Zmień język\n"
            "/cancel - Anuluj bieżącą operację\n\n"
            "Po prostu wyślij zdjęcie kamyka!"
        ),
        "lang_select": "Wybierz język:",
        "lang_changed": "Język zmieniony na Polski",

        # Stone detection
        "analyzing": "Analizuję zdjęcie...",
        "stone_not_found": (
            "❌ Kamyk nie został znaleziony na zdjęciu.\n\n"
            "Upewnij się, że kamyk jest dobrze widoczny i spróbuj ponownie."
        ),
        "stone_not_recognized": (
            "❌ Kamyk nie został rozpoznany.\n\n"
            "Upewnij się, że na zdjęciu jest płaski kamyk z wzorem i spróbuj ponownie."
        ),
        "cropped_stone": "📷 Rozpoznany kamyk",

        # Existing stone
        "stone_found": "✅ Kamyk znaleziony!",
        "stone_id": "🔢 ID: {id}",
        "stone_name": "📛 Nazwa: {name}",
        "stone_description": "📝 Opis: {description}",
        "stone_seen": "📍 Widziany {count} raz(y)",
        "send_location_prompt": "\nWyślij lokalizację lub wpisz kod pocztowy:",

        # New stone
        "new_stone": "🆕 Nowy kamyk!",
        "enter_name": "Podaj nazwę dla kamyka:",
        "name_too_short": "Nazwa za krótka. Podaj nazwę (minimum 2 znaki):",
        "add_description": "Nazwa: {name}\n\nDodać opis? (lub naciśnij «Pomiń»)",

        # Location
        "btn_send_location": "📍 Wyślij lokalizację",
        "btn_enter_zip": "Wpisz kod pocztowy",
        "btn_skip": "Pomiń",
        "enter_zip": "Wpisz kod pocztowy (ZIP):",
        "location_prompt": "Wyślij lokalizację, wpisz kod pocztowy lub naciśnij «Pomiń».",

        # Save messages
        "saved_to_history": "✅ Zapisano w historii!",
        "saved_no_location": "✅ Zapisano w historii (bez lokalizacji)!",
        "stone_registered": "✅ Kamyk «{name}» zarejestrowany!",
        "location_label": "🗺 Lokalizacja: {location}",
        "zip_label": "📮 ZIP: {zip}",
        "coords_label": "📍 Współrzędne: {lat:.4f}, {lon:.4f}",

        # Map
        "map_caption": "🗺 Mapa podróży\n🟢 start → 🔴 koniec",
        "interactive_map": "🗺 Interaktywna mapa",

        # My stones
        "my_stones": "🪨 Twoje kamyki:\n",
        "no_stones": (
            "Nie masz jeszcze zarejestrowanych kamyków.\n\n"
            "Wyślij zdjęcie kamyka, aby zarejestrować!"
        ),
        "page_info": "📄 Strona {page}/{total} (kamyków: {count})",
        "btn_prev_page": "⬅️ Poprzednia",
        "btn_next_page": "Następna ➡️",

        # Info command
        "info_usage": "Użycie: /info <id>\nPrzykład: /info 5",
        "info_not_found": "❌ Kamyk #{id} nie znaleziony.",

        # Delete
        "delete_usage": "Użycie: /delete <id>\nPrzykład: /delete 5",
        "delete_not_found": "❌ Kamyk #{id} nie znaleziony lub nie należy do Ciebie.",
        "delete_confirm": "Usunąć kamyk «{name}» (ID: {id})?\n\n⚠️ Ta operacja jest nieodwracalna!",
        "delete_success": "✅ Kamyk «{name}» został usunięty.",
        "delete_cancelled": "Usuwanie anulowane.",
        "btn_confirm_delete": "🗑 Tak, usuń",
        "btn_cancel_delete": "❌ Anuluj",

        # Errors
        "error_photo": "❌ Wystąpił błąd podczas przetwarzania zdjęcia. Spróbuj ponownie.",
        "error_generic": "❌ Wystąpił błąd. Spróbuj ponownie.",
        "cancelled": "Operacja anulowana.",
    },

    "en": {
        # Commands
        "start": (
            "Hi! I'm kamyczki-bot.\n\n"
            "Send me a photo of a painted rock:\n"
            "• If it's already registered — I'll show info\n"
            "• If it's new — I'll help register it"
        ),
        "help": (
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show help\n"
            "/mine - My rocks\n"
            "/info <id> - Rock information\n"
            "/delete <id> - Delete a rock\n"
            "/lang - Change language\n"
            "/cancel - Cancel current operation\n\n"
            "Just send a photo of a rock!"
        ),
        "lang_select": "Select language:",
        "lang_changed": "Language changed to English",

        # Stone detection
        "analyzing": "Analyzing image...",
        "stone_not_found": (
            "❌ Rock not found in the image.\n\n"
            "Make sure the rock is clearly visible and try again."
        ),
        "stone_not_recognized": (
            "❌ Rock not recognized.\n\n"
            "Make sure it's a flat painted rock and try again."
        ),
        "cropped_stone": "📷 Recognized rock",

        # Existing stone
        "stone_found": "✅ Rock found!",
        "stone_id": "🔢 ID: {id}",
        "stone_name": "📛 Name: {name}",
        "stone_description": "📝 Description: {description}",
        "stone_seen": "📍 Seen {count} time(s)",
        "send_location_prompt": "\nSend location or enter ZIP code:",

        # New stone
        "new_stone": "🆕 New rock!",
        "enter_name": "Enter a name for the rock:",
        "name_too_short": "Name too short. Enter a name (minimum 2 characters):",
        "add_description": "Name: {name}\n\nAdd description? (or press «Skip»)",

        # Location
        "btn_send_location": "📍 Send location",
        "btn_enter_zip": "Enter ZIP code",
        "btn_skip": "Skip",
        "enter_zip": "Enter ZIP code:",
        "location_prompt": "Send location, enter ZIP code, or press «Skip».",

        # Save messages
        "saved_to_history": "✅ Saved to history!",
        "saved_no_location": "✅ Saved to history (no location)!",
        "stone_registered": "✅ Rock «{name}» registered!",
        "location_label": "🗺 Location: {location}",
        "zip_label": "📮 ZIP: {zip}",
        "coords_label": "📍 Coordinates: {lat:.4f}, {lon:.4f}",

        # Map
        "map_caption": "🗺 Journey map\n🟢 start → 🔴 finish",
        "interactive_map": "🗺 Interactive map",

        # My stones
        "my_stones": "🪨 Your rocks:\n",
        "no_stones": (
            "You don't have any registered rocks yet.\n\n"
            "Send a photo of a rock to register!"
        ),
        "page_info": "📄 Page {page}/{total} (rocks: {count})",
        "btn_prev_page": "⬅️ Previous",
        "btn_next_page": "Next ➡️",

        # Info command
        "info_usage": "Usage: /info <id>\nExample: /info 5",
        "info_not_found": "❌ Rock #{id} not found.",

        # Delete
        "delete_usage": "Usage: /delete <id>\nExample: /delete 5",
        "delete_not_found": "❌ Rock #{id} not found or doesn't belong to you.",
        "delete_confirm": "Delete rock «{name}» (ID: {id})?\n\n⚠️ This action is irreversible!",
        "delete_success": "✅ Rock «{name}» has been deleted.",
        "delete_cancelled": "Deletion cancelled.",
        "btn_confirm_delete": "🗑 Yes, delete",
        "btn_cancel_delete": "❌ Cancel",

        # Errors
        "error_photo": "❌ Error processing photo. Please try again.",
        "error_generic": "❌ An error occurred. Please try again.",
        "cancelled": "Operation cancelled.",
    },

    "ru": {
        # Commands
        "start": (
            "Привет! Я kamyczki-bot.\n\n"
            "Отправь мне фото камня:\n"
            "• Если камень уже зарегистрирован — покажу информацию\n"
            "• Если новый — помогу зарегистрировать"
        ),
        "help": (
            "Доступные команды:\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать справку\n"
            "/mine - Мои камни\n"
            "/info <id> - Информация о камне\n"
            "/delete <id> - Удалить камень\n"
            "/lang - Сменить язык\n"
            "/cancel - Отменить текущую операцию\n\n"
            "Просто отправь фото камня!"
        ),
        "lang_select": "Выберите язык:",
        "lang_changed": "Язык изменён на Русский",

        # Stone detection
        "analyzing": "Анализирую изображение...",
        "stone_not_found": (
            "❌ Камень не найден на изображении.\n\n"
            "Убедитесь, что камень хорошо виден на фото и попробуйте снова."
        ),
        "stone_not_recognized": (
            "❌ Камень не распознан.\n\n"
            "Убедитесь, что на фото плоский камень с рисунком, "
            "и попробуйте снова."
        ),
        "cropped_stone": "📷 Распознанный камень",

        # Existing stone
        "stone_found": "✅ Камень найден!",
        "stone_id": "🔢 ID: {id}",
        "stone_name": "📛 Имя: {name}",
        "stone_description": "📝 Описание: {description}",
        "stone_seen": "📍 Замечен {count} раз(а)",
        "send_location_prompt": "\nОтправь геолокацию или введи ZIP код:",

        # New stone
        "new_stone": "🆕 Новый камень!",
        "enter_name": "Введите имя для камня:",
        "name_too_short": "Имя слишком короткое. Введите имя (минимум 2 символа):",
        "add_description": "Имя: {name}\n\nДобавить описание? (или нажми «Пропустить»)",

        # Location
        "btn_send_location": "📍 Отправить местоположение",
        "btn_enter_zip": "Ввести ZIP код",
        "btn_skip": "Пропустить",
        "enter_zip": "Введи почтовый индекс (ZIP код):",
        "location_prompt": "Отправь геолокацию, введи ZIP код или нажми «Пропустить».",

        # Save messages
        "saved_to_history": "✅ Сохранено в истории!",
        "saved_no_location": "✅ Сохранено в истории (без местоположения)!",
        "stone_registered": "✅ Камень «{name}» зарегистрирован!",
        "location_label": "🗺 Местоположение: {location}",
        "zip_label": "📮 ZIP: {zip}",
        "coords_label": "📍 Координаты: {lat:.4f}, {lon:.4f}",

        # Map
        "map_caption": "🗺 Карта перемещений\n🟢 старт → 🔴 финиш",
        "interactive_map": "🗺 Интерактивная карта",

        # My stones
        "my_stones": "🪨 Твои камни:\n",
        "no_stones": (
            "У тебя пока нет зарегистрированных камней.\n\n"
            "Отправь фото камня, чтобы зарегистрировать!"
        ),
        "page_info": "📄 Страница {page}/{total} (камней: {count})",
        "btn_prev_page": "⬅️ Назад",
        "btn_next_page": "Вперёд ➡️",

        # Info command
        "info_usage": "Использование: /info <id>\nПример: /info 5",
        "info_not_found": "❌ Камень #{id} не найден.",

        # Delete
        "delete_usage": "Использование: /delete <id>\nПример: /delete 5",
        "delete_not_found": "❌ Камень #{id} не найден или не принадлежит тебе.",
        "delete_confirm": "Удалить камень «{name}» (ID: {id})?\n\n⚠️ Это действие необратимо!",
        "delete_success": "✅ Камень «{name}» удалён.",
        "delete_cancelled": "Удаление отменено.",
        "btn_confirm_delete": "🗑 Да, удалить",
        "btn_cancel_delete": "❌ Отмена",

        # Errors
        "error_photo": "❌ Произошла ошибка при обработке фото. Попробуйте снова.",
        "error_generic": "❌ Произошла ошибка. Попробуйте снова.",
        "cancelled": "Операция отменена.",
    },
}
