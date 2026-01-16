#!/bin/bash
set -e

# Kamyczki Bot Installation Script for Linux Mint / Ubuntu

APP_DIR="/opt/kamyczki-bot"
APP_USER="kamyczki"

echo "=== Kamyczki Bot Installation ==="

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
apt update
apt install -y python3.11 python3.11-venv python3.11-dev \
    postgresql postgresql-contrib \
    git curl

# Create user
if ! id "$APP_USER" &>/dev/null; then
    echo "Creating user $APP_USER..."
    useradd -r -s /bin/false $APP_USER
fi

# Clone or update repo
if [ -d "$APP_DIR" ]; then
    echo "Updating repository..."
    cd $APP_DIR
    git pull
else
    echo "Cloning repository..."
    git clone https://github.com/shn-moto/kamyczki-bot.git $APP_DIR
    cd $APP_DIR
fi

# Create virtual environment
echo "Setting up Python environment..."
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Setup PostgreSQL
echo "Setting up PostgreSQL..."
sudo -u postgres psql -c "CREATE USER kamyczki WITH PASSWORD 'kamyczki_secret';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE kamyczki_bot OWNER kamyczki;" 2>/dev/null || true
sudo -u postgres psql -d kamyczki_bot -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Run init SQL
sudo -u postgres psql -d kamyczki_bot -f $APP_DIR/init.sql

# Create .env if not exists
if [ ! -f "$APP_DIR/.env" ]; then
    echo "Creating .env file..."
    cp $APP_DIR/.env.example $APP_DIR/.env
    echo ""
    echo "!!! IMPORTANT: Edit $APP_DIR/.env and set TELEGRAM_BOT_TOKEN !!!"
    echo ""
fi

# Create logs directory
mkdir -p $APP_DIR/logs
chown -R $APP_USER:$APP_USER $APP_DIR

# Install systemd service
echo "Installing systemd service..."
cp $APP_DIR/deploy/kamyczki-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable kamyczki-bot

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "1. Edit /opt/kamyczki-bot/.env and set TELEGRAM_BOT_TOKEN"
echo "2. Start the bot: sudo systemctl start kamyczki-bot"
echo "3. Check status: sudo systemctl status kamyczki-bot"
echo "4. View logs: journalctl -u kamyczki-bot -f"
echo ""
