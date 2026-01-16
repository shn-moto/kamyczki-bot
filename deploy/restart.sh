#!/bin/bash
# Restart kamyczki-bot and cloudflared services

sudo systemctl restart cloudflared
sleep 3
echo "=== Cloudflared tunnel URL ==="
journalctl -u cloudflared --no-pager -n 20 | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1

sudo systemctl restart kamyczki-bot
echo ""
echo "=== Service status ==="
sudo systemctl status kamyczki-bot cloudflared --no-pager
