@echo off
cd /d D:\PRG\Pyton\kamyczki-bot

if not exist logs mkdir logs

echo Stopping all bot instances...
taskkill /f /im python.exe 2>nul
timeout /t 2 /nobreak >nul

echo Starting bot...
start "" /min cmd /c ".venv\Scripts\python.exe -m src.main >> logs\bot.log 2>&1"

echo.
echo Bot started in background.
echo Log: D:\PRG\Pyton\kamyczki-bot\logs\bot.log
