# Kamyczki Bot

Telegram бот для отслеживания раскрашенных камней (painted rocks). Камни регистрируются по фото, распознаются через CLIP эмбеддинги и хранятся в PostgreSQL с pgvector.

## Возможности

- Регистрация новых камней по фото
- Распознавание камней через CLIP эмбеддинги (ViT-B/32)
- Умный кроп камня с удалением фона (rembg)
- Отслеживание истории перемещений камней
- Геолокация или ZIP-код для определения местоположения
- PNG карта маршрута камня
- Интерактивная карта через Telegram Mini App

## Быстрый старт (Docker)

```bash
# Клонировать и настроить
git clone https://github.com/shn-moto/kamyczki-bot.git
cd kamyczki-bot
cp .env.example .env
nano .env  # установить TELEGRAM_BOT_TOKEN

# Запустить
docker compose up -d

# Посмотреть URL туннеля для Mini App
docker compose logs kamyczki-tunnel 2>&1 | grep https://

# Логи бота
docker compose logs -f kamyczki-bot
```

## Архитектура

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ cloudflared │────▶│     bot     │────▶│  postgres   │
│   HTTPS     │     │   :8080     │     │   pgvector  │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Технологии

- **Python 3.11** + python-telegram-bot
- **CLIP ViT-B/32** (open-clip-torch) — распознавание камней
- **rembg** (U2-Net) — удаление фона
- **PostgreSQL 16 + pgvector** — хранение эмбеддингов
- **FastAPI + Leaflet.js** — интерактивная карта (Mini App)
- **cloudflared** — HTTPS туннель для Telegram

## Документация

Подробная документация в [CLAUDE.md](CLAUDE.md).

## Лицензия

MIT
