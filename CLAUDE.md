# kamyczki-bot

Telegram бот для отслеживания раскрашенных камней (painted rocks). Камни регистрируются по фото, распознаются через CLIP эмбеддинги и хранятся в PostgreSQL с pgvector.

## Архитектура

### Режимы работы

Бот поддерживает два режима ML-обработки (переключается через `USE_LOCAL_ML`):

1. **Local ML** (`USE_LOCAL_ML=true`) — CLIP + rembg запускаются локально
2. **Modal Serverless** (`USE_LOCAL_ML=false`) — ML через Modal.com API (дорого из-за GPU)

### Варианты деплоя

1. **Локальный сервер** (основной) — `docker-compose.local.yml` + Neon PostgreSQL
2. **Cloud Run** (бэкап) — CPU-only, auto-scaling, холодный старт ~2 мин

```
src/
├── main.py              # Точка входа (polling mode)
├── main_webhook.py      # Webhook mode для Docker/Cloud Run
├── config.py            # Pydantic Settings (.env)
├── bot/
│   └── handlers.py      # Telegram ConversationHandler + /search
├── database/
│   ├── models.py        # SQLAlchemy: Stone, StoneHistory, UserSettings
│   └── connection.py    # AsyncPG connection + pool settings
├── i18n/
│   ├── __init__.py      # Экспорт функций локализации
│   └── translations.py  # Переводы (PL, EN, RU)
├── services/
│   ├── clip_service.py  # CLIP ViT-B/32 + rembg кроп + encode_text_query
│   ├── ml_service.py    # Унифицированный API (local/modal)
│   ├── modal_client.py  # Клиент для Modal API
│   ├── map_service.py   # Генерация PNG карты (staticmap)
│   ├── geocoding.py     # Nominatim reverse/forward geocoding
│   └── exif.py          # Извлечение GPS из EXIF
└── web/
    ├── routes.py        # API endpoints для Mini App (/api prefix)
    └── static/
        ├── index.html   # Telegram Mini App (Leaflet.js)
        ├── map.js       # Инициализация карты
        └── style.css    # Стили

# Корневые файлы
├── docker-compose.local.yml   # Основной деплой (CPU)
├── docker-compose.gpu.yml     # GPU override для GTX 1070
├── Dockerfile.local           # CPU образ
├── Dockerfile.gpu             # GPU образ с CUDA
├── wait-for-tunnel.sh         # Автополучение URL туннеля
├── .env.local.example         # Шаблон переменных окружения
└── requirements.txt           # Python зависимости
```

## Основной флоу

### Существующий камень:
1. Фото → `context.user_data.clear()` → **rembg кроп** → CLIP детекция
2. Поиск по эмбеддингу (cosine similarity >= 0.82)
3. **Миниатюра кропа** + "Камень найден!" + кнопки: геолокация / ZIP / пропустить
4. Геолокация или ZIP код → геокодинг → добавление в историю
5. "Сохранено!" + **PNG карта** + **кнопка интерактивной карты (Mini App)**

### Новый камень:
1. Фото → **rembg кроп** → CLIP детекция → эмбеддинг
2. **Миниатюра кропа** + "Новый камень!" → ввод имени → описание (опционально)
3. Геолокация или ZIP код → регистрация в БД → **вывод ID камня**

### Текстовый поиск (/search):
1. Запрос → **перевод на английский** (GoogleTranslator) → CLIP encode_text
2. Поиск по cosine similarity (порог 0.25)
3. Вывод топ-5 результатов с фото и similarity score

## Умный кроп камня

- **rembg** (U2-Net) — удаление фона для выделения камня
- `smart_crop_stone()` в clip_service.py:
  - Удаляет фон через rembg
  - Находит bounding box непрозрачных пикселей
  - Кропит оригинал с padding 20px
  - Возвращает кроп + миниатюру 200x200
- Эмбеддинг создаётся из кропнутого изображения (лучше качество поиска)
- Миниатюра отправляется пользователю для визуальной проверки

## Текстовый поиск (CLIP text-to-image)

- **Команда:** `/search <описание>` (например: `/search синяя бабочка`)
- **Перевод:** Автоматический перевод на английский через `deep-translator` (GoogleTranslator)
  - CLIP обучен на английских текстах, перевод улучшает качество поиска
- **Порог similarity:** 0.25 (ниже чем для image-to-image, т.к. text-to-image менее точный)
- **Результат:** Топ-5 камней с фото и процентом сходства

```python
# handlers.py
def translate_to_english(text: str) -> str:
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source="auto", target="en")
    return translator.translate(text)
```

## Карта перемещений

- **staticmap** — генерация PNG карты с OSM тайлами
- Маркеры: 🟢 старт, 🔵 промежуточные, 🔴 финиш
- Линия маршрута между точками
- Автоматический зум под все точки
- Отправляется как фото в конце флоу (после добавления в историю)

**Почему PNG, а не HTML:** Telegram не рендерит интерактивный HTML, а iOS Safari блокирует CDN-ресурсы в локальных HTML файлах.

## Telegram Mini App (интерактивная карта)

- **FastAPI** web сервер (uvicorn)
- **Leaflet.js** для интерактивной карты с OSM тайлами
- Кнопка "🗺 Интерактивная карта" открывает Mini App в Telegram
- API endpoint: `GET /api/stones/{stone_id}/map-data`
- Static files: `/static/index.html`
- Требует HTTPS для работы в Telegram
- **Динамический URL:** берётся из `WEBHOOK_URL` env (установленный wait-for-tunnel.sh) или из `settings.webapp_base_url`

### Изоляция event loop

**ВАЖНО:** FastAPI работает в отдельном потоке со своим event loop. Использование `get_async_session()` из бота вызовет ошибку "Task got Future attached to a different loop".

Решение в `routes.py`: отдельный engine и session maker с параметрами стабильности:
```python
_web_engine = create_async_engine(
    settings.db_url,
    pool_pre_ping=True,    # Проверяет соединение перед запросом
    pool_recycle=300,      # Пересоздает соединение каждые 5 минут
    pool_size=5,
    max_overflow=5
)
```

## Геокодинг

- **Nominatim API** (OpenStreetMap)
- Reverse geocoding: GPS → адрес (`get_location_from_gps`)
- Forward geocoding: ZIP код → координаты (`get_coords_from_zip`)
- User-Agent: `kamyczki-bot/1.0`

## База данных

- **Neon.tech PostgreSQL** (serverless, внешняя БД)
- Таблица `stones`: id, name, description, photo_file_id, embedding(512), registered_by_user_id
- Таблица `stone_history`: id, stone_id, telegram_user_id, photo_file_id, lat, lon, zip_code, created_at
- Таблица `user_settings`: telegram_user_id, language, created_at, updated_at

### Подключение к Neon

```
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?ssl=require
```

### Стабильность соединений

Neon может закрывать idle соединения. Параметры в `connection.py`:
```python
engine = create_async_engine(
    settings.db_url,
    pool_pre_ping=True,       # Проверяет соединение перед каждым запросом
    pool_recycle=300,         # Пересоздает соединение каждые 5 минут
    pool_size=5,              # Базовое количество соединений
    max_overflow=10           # Дополнительные соединения при нагрузке
)
```

### Хранение фото

Фото камней хранятся на серверах Telegram. В БД сохраняется только `photo_file_id` — уникальный идентификатор файла. При `/info` бот отправляет фото по этому ID без локального хранения. Ограничение: `file_id` привязан к конкретному боту.

## Ключевые параметры

- `SIMILARITY_THRESHOLD = 0.82` (handlers.py) — порог для image-to-image поиска
- `TEXT_SEARCH_MIN_SIMILARITY = 0.25` (handlers.py) — порог для text-to-image поиска
- `STONES_PER_PAGE = 10` (handlers.py) — камней на странице в /mine
- CLIP модель: `ViT-B-32` pretrained `laion2b_s34b_b79k` — 512-dim vectors
- Stone detection threshold: `0.05` (clip_service.py)
- Web server port: `8080`

### Подбор порога similarity (image-to-image)

Тестирование на 22 камнях показало:
- **Идентичный камень** (разные фото): ~0.85-0.99
- **Разные камни**: ~0.50-0.82

| Порог | Результат |
|-------|-----------|
| 0.70 | False positives: похожий фон |
| 0.80 | False positives: яркие цвета |
| 0.88 | Пропускает матчи |
| 0.85 | Пропускает матчи |
| 0.84 | Пропускает матчи |
| **0.82** | ✅ Оптимальный баланс |

## Векторный поиск с HNSW индексом

**HNSW (Hierarchical Navigable Small World)** — алгоритм приближённого поиска ближайших соседей. Индекс создаётся автоматически в `init_db()`:

```sql
CREATE INDEX IF NOT EXISTS stones_embedding_hnsw_idx
ON stones USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Сложность поиска:** O(log n) вместо O(n).

### Особенности asyncpg + pgvector

SQLAlchemy ORM `order_by(Stone.embedding.cosine_distance(list))` не работает с asyncpg — параметр не передаётся корректно.

**Решение:** raw SQL с `text()` и явным приведением к `::vector`:
```python
embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
query = f"""
    SELECT *, 1 - (embedding <=> '{embedding_str}'::vector) as similarity
    FROM stones
    ORDER BY embedding <=> '{embedding_str}'::vector
    LIMIT 1
"""
result = await session.execute(text(query))
```

## Известные проблемы и решения

### NumPy 2.x несовместимость
torch и open-clip скомпилированы с NumPy 1.x. Решение: `numpy<2` в requirements.txt.

### uvloop конфликт с telegram bot
uvicorn[standard] включает uvloop, который патчит `asyncio.get_event_loop()` глобально. Решения:
- `loop="asyncio"` в `uvicorn.run()` (main_webhook.py)
- `asyncio.set_event_loop(asyncio.new_event_loop())` перед запуском

### Modal GPU слишком дорогой
Modal.com берёт деньги за idle GPU время в `scaledown_window`. При keep_warm=1 это ~$425/месяц. Решение: использовать локальный CPU сервер.

### Neon закрывает idle соединения
Решение: `pool_pre_ping=True` и `pool_recycle=300` в SQLAlchemy engine (см. "Стабильность соединений").

## Переменные окружения

```bash
# Обязательные
TELEGRAM_BOT_TOKEN=xxx
DATABASE_URL=postgresql+asyncpg://...

# Режим работы
USE_LOCAL_ML=true          # true = локальный CLIP, false = Modal API
USE_WEBHOOK=true           # true = webhook mode, false = polling

# Опциональные (автоматически устанавливаются wait-for-tunnel.sh)
WEBHOOK_URL=https://xxx.trycloudflare.com  # Автоматически из метрик cloudflared
WEBAPP_BASE_URL=https://xxx.trycloudflare.com  # Fallback если WEBHOOK_URL не установлен

# Modal (если USE_LOCAL_ML=false)
MODAL_ENDPOINT_URL=https://xxx.modal.run
```

## Развертывание

### Локальный сервер (основной вариант)

```bash
# На сервере
cd /home/oem/PRG/kamyczki/kamyczki-bot
git pull

# Настроить .env.local (только TELEGRAM_BOT_TOKEN и DATABASE_URL)
cp .env.local.example .env.local
nano .env.local

# Запустить (URL туннеля получается автоматически!)
docker compose -f docker-compose.local.yml up -d --build

# Логи
docker logs kamyczki-bot-local --tail 50
```

**Автоматическое получение URL туннеля:**

`wait-for-tunnel.sh` автоматически получает URL из метрик cloudflared (порт 2000) и устанавливает `WEBHOOK_URL`:
```bash
TUNNEL_URL=$(curl -s http://cloudflared:2000/metrics | grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' | head -n 1)
export WEBHOOK_URL="$TUNNEL_URL"
```

**Архитектура:**
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ cloudflared │────▶│     bot     │────▶│    Neon     │
│ HTTPS:2000  │     │   :8080     │     │  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
      ↑                    │
  Telegram          wait-for-tunnel.sh
                    (читает URL из метрик)
```

### Cloud Run (бэкап)

```bash
# Деплой
gcloud run deploy kamyczki-bot-cpu \
  --source . \
  --region europe-central2 \
  --allow-unauthenticated \
  --set-env-vars "USE_LOCAL_ML=true,USE_WEBHOOK=true"

# Остановить (0 instances)
gcloud run services update kamyczki-bot-cpu --region europe-central2 --max-instances=0
```

### GPU версия (GTX 1070)

```bash
# С GPU override
docker compose -f docker-compose.local.yml -f docker-compose.gpu.yml up -d --build
```

**Требования:**
- nvidia-container-toolkit
- CUDA 11.8 совместимый драйвер

## Локализация (i18n)

- **Языки:** Polski (по умолчанию), English, Русский
- **Команда:** `/lang` — выбор языка через inline-кнопки
- **Хранение:** PostgreSQL (таблица `user_settings`) + in-memory кэш
- **Файлы:** `src/i18n/translations.py`

## Команды бота

- `/start` — приветствие
- `/help` — справка
- `/mine` — список камней пользователя с пагинацией (10 на страницу)
- `/search <описание>` — поиск камней по текстовому описанию
- `/info <id>` — информация о камне по ID (фото, карта)
- `/delete <id>` — удаление камня с подтверждением
- `/lang` — смена языка интерфейса
- `/cancel` — отмена текущей операции

## TODO / Идеи

- [x] ~~Кроп изображения до границ камня перед созданием эмбеддинга~~ (rembg)
- [x] ~~Telegram Mini App для интерактивной карты~~ (Leaflet.js + FastAPI + cloudflared)
- [x] ~~ZIP код как альтернатива геолокации~~ (для Telegram Desktop)
- [x] ~~Docker deployment~~ (docker-compose + cloudflared)
- [x] ~~Локализация (i18n)~~ (PL, EN, RU)
- [x] ~~Оптимизация поиска~~ (HNSW индекс, O(log n) вместо O(n))
- [x] ~~Сохранение языка пользователя в БД~~ (таблица user_settings)
- [x] ~~Serverless архитектура~~ (Neon DB + local server + Cloud Run backup)
- [x] ~~Текстовый поиск~~ (/search с переводом через GoogleTranslator)
- [x] ~~Автоматическое получение URL туннеля~~ (wait-for-tunnel.sh + cloudflared metrics)
- [x] ~~Стабильность соединений с БД~~ (pool_pre_ping, pool_recycle)
- [ ] GPU поддержка (GTX 1070) — Dockerfile.gpu требует доработки
- [ ] Голосовой поиск (speech-to-text → text search)
- [ ] Inline mode (@bot_name butterfly)

## Отброшенные идеи

- **Извлечение GPS из EXIF** — Telegram удаляет EXIF-метаданные из фото при загрузке
- **Modal.com GPU** — слишком дорого (~$425/месяц за keep_warm), CPU на Xeon быстрее чем Cloud Run
- **Локальная PostgreSQL в Docker** — перешли на Neon.tech для serverless
