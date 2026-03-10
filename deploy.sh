#!/bin/bash
cd /opt/trading-api
for f in data_snapshot_latest.json data_snapshot_night_latest.json; do
  [ -d "$f" ] && rm -rf "$f"
  [ -d "data/$f" ] && rm -rf "data/$f"
done
curl -fsSL "https://raw.githubusercontent.com/s19870711/trading-api/main/openclaw_telegram_handler.py" -o openclaw_telegram_handler.py
grep -q "TELEGRAM_BOT_TOKEN" .env 2>/dev/null || echo "TELEGRAM_BOT_TOKEN=8586820264:AAGXQVVLT3WQ1UwMNy-2QltxFHvIPvFkLdw" >> .env
grep -q "TELEGRAM_CHAT_ID" .env 2>/dev/null || echo "TELEGRAM_CHAT_ID=6904817875" >> .env
grep -q "DATA_DIR" .env 2>/dev/null || echo "DATA_DIR=/opt/trading-api/data" >> .env
pkill -f openclaw_telegram_handler || true
sleep 2
nohup python3 openclaw_telegram_handler.py > /tmp/openclaw_handler.log 2>&1 &
sleep 5
ps aux | grep openclaw_telegram_handler | grep -v grep && echo "SUCCESS" || echo "FAILED"
tail -20 /tmp/openclaw_handler.log