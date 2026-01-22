#!/bin/sh

# Пытаемся получить URL туннеля из метрик cloudflared
echo "Waiting for Cloudflare tunnel to generate URL..."
MAX_RETRIES=10
COUNT=0

while [ $COUNT -lt $MAX_RETRIES ]; do
  # Запрашиваем метрики туннеля и ищем там строку с адресом .trycloudflare.com
  TUNNEL_URL=$(curl -s http://cloudflared:2000/metrics | grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' | head -n 1)
  
  if [ ! -z "$TUNNEL_URL" ]; then
    echo "Tunnel is up! URL: $TUNNEL_URL"
    # Передаем этот URL в переменную окружения, которую ждет ваш бот
    export WEBHOOK_URL="$TUNNEL_URL"
    # Запускаем бота
    exec python -m uvicorn src.main_webhook:app --host 0.0.0.0 --port 8080
    exit 0
  fi
  
  echo "Still waiting for URL (attempt $COUNT)..."
  sleep 3
  COUNT=$((COUNT+1))
done

echo "Failed to get tunnel URL. Starting bot anyway..."
exec python -m uvicorn src.main_webhook:app --host 0.0.0.0 --port 8080