#!/bin/bash
# Get cloudflared tunnel URL and update .env

APP_DIR="/opt/kamyczki-bot"

# Wait for tunnel to start
sleep 5

# Get tunnel URL from logs
TUNNEL_URL=$(journalctl -u cloudflared --no-pager -n 50 | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)

if [ -z "$TUNNEL_URL" ]; then
    echo "ERROR: Could not get tunnel URL"
    exit 1
fi

echo "Tunnel URL: $TUNNEL_URL"

# Update .env
if [ -f "$APP_DIR/.env" ]; then
    sed -i "s|^WEBAPP_BASE_URL=.*|WEBAPP_BASE_URL=$TUNNEL_URL|" $APP_DIR/.env
    echo "Updated .env with new URL"

    # Restart bot to pick up new URL
    systemctl restart kamyczki-bot
    echo "Bot restarted"
else
    echo "ERROR: .env not found"
    exit 1
fi
