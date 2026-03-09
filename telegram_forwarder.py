#!/usr/bin/env python3
"""
telegram_forwarder.py — Telegram → Nebula Webhook Bridge v1.0.0
接收所有 Telegram update，轉發至 Nebula Webhook，並將回應推回 Telegram
監聽 port 8443（Telegram 支援的非 SSL port）
"""
import os, json, logging, asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Forwarder", version="1.0.0")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
NEBULA_WEBHOOK_URL  = os.environ.get(
    "NEBULA_WEBHOOK_URL",
    "https://api.nebula.gg/webhooks/triggers/trig_069af1d09f5e7119800051116fedbf7a/webhook"
)
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
FORWARD_TIMEOUT   = 55

def extract_chat_id(update: dict):
    if "message" in update:
        return update["message"]["chat"]["id"]
    if "callback_query" in update:
        return update["callback_query"]["message"]["chat"]["id"]
    if "edited_message" in update:
        return update["edited_message"]["chat"]["id"]
    return None

async def send_telegram_message(chat_id, text, parse_mode="Markdown"):
    if not TELEGRAM_BOT_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{TELEGRAM_API_BASE}/sendMessage", json={
                "chat_id": chat_id, "text": text,
                "parse_mode": parse_mode, "disable_web_page_preview": True
            })
            if r.status_code != 200:
                await client.post(f"{TELEGRAM_API_BASE}/sendMessage",
                                  json={"chat_id": chat_id, "text": text})
            return True
    except Exception as e:
        logger.error(f"send_telegram_message error: {e}")
        return False

async def answer_callback_query(cq_id: str, text: str = ""):
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{TELEGRAM_API_BASE}/answerCallbackQuery",
                              json={"callback_query_id": cq_id, "text": text})
    except Exception as e:
        logger.warning(f"answerCallbackQuery error: {e}")

@app.post("/webhook")
async def receive_update(request: Request):
    try:
        update = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)

    update_id = update.get("update_id", "?")
    logger.info(f"update_id={update_id}")

    # 立即 ack callback_query，消除 Telegram 轉圈圈
    if "callback_query" in update:
        cq_id = update["callback_query"].get("id", "")
        asyncio.create_task(answer_callback_query(cq_id, "⏳ 處理中..."))

    chat_id = extract_chat_id(update)

    try:
        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT) as client:
            resp = await client.post(NEBULA_WEBHOOK_URL, json={
                "telegram_update": update,
                "chat_id": chat_id,
                "source": "telegram_forwarder_v1"
            }, headers={"Content-Type": "application/json"})
            logger.info(f"Nebula status={resp.status_code}")

            if resp.status_code == 200 and chat_id:
                try:
                    data = resp.json()
                    reply = (data.get("reply_text") or data.get("message")
                             or data.get("response") or data.get("text"))
                    if reply:
                        asyncio.create_task(send_telegram_message(chat_id, str(reply)))
                except Exception:
                    pass

    except httpx.TimeoutException:
        logger.warning(f"Nebula timeout update_id={update_id}")
        if chat_id:
            asyncio.create_task(send_telegram_message(
                chat_id, "⚠️ 系統回應超時（>55s），請稍後重試。"))
    except Exception as e:
        logger.error(f"Forward error: {e}")

    return JSONResponse({"ok": True})

@app.get("/health")
async def health():
    return {
        "status": "running",
        "service": "telegram-forwarder",
        "version": "1.0.0",
        "nebula_webhook": NEBULA_WEBHOOK_URL[:60] + "...",
        "bot_token_set": bool(TELEGRAM_BOT_TOKEN)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8443, log_level="info")