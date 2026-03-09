#!/bin/bash
# install_forwarder.sh — 一鍵部署 telegram_forwarder.py 到 VM
# 執行方式: bash install_forwarder.sh
set -e

DEPLOY_DIR="/opt/trading-api"
SERVICE_NAME="telegram-forwarder"
PYTHON_BIN=$(which python3)
PIP_BIN=$(which pip3)

echo "=== [1/6] 安裝依賴套件 ==="
$PIP_BIN install fastapi uvicorn httpx --quiet

echo "=== [2/6] 複製 forwarder 程式碼 ==="
cp /opt/trading-api/telegram_forwarder.py $DEPLOY_DIR/telegram_forwarder.py
chmod +x $DEPLOY_DIR/telegram_forwarder.py

echo "=== [3/6] 建立 systemd service ==="
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Telegram Forwarder — Nebula Webhook Bridge
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${DEPLOY_DIR}
EnvironmentFile=/opt/trading-api/.env
ExecStart=${PYTHON_BIN} -m uvicorn telegram_forwarder:app --host 0.0.0.0 --port 8443 --log-level info
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

echo "=== [4/6] 啟動 systemd service ==="
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

echo "=== [5/6] 等待服務啟動（5秒）==="
sleep 5

echo "=== [6/6] 健康檢查 ==="
STATUS=$(systemctl is-active ${SERVICE_NAME})
if [ "$STATUS" = "active" ]; then
    echo "✅ ${SERVICE_NAME} 運行中"
    curl -s http://localhost:8443/health | python3 -m json.tool
else
    echo "❌ ${SERVICE_NAME} 啟動失敗，查看 journal："
    journalctl -u ${SERVICE_NAME} --no-pager -n 30
    exit 1
fi

echo "=== 部署完成 ==="