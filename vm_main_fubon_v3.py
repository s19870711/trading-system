#!/usr/bin/env python3
"""
Fubon Neo SDK Bridge API - v3.2.0
VM: 35.185.145.204:8080
v3.2.0: 新增 /admin/exec 與 /admin/git-pull 端點，支援遠端部署
"""

import os
import json
import shlex
import logging
import subprocess
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ==================== 環境變數 ====================
FUBON_USER_ID = os.getenv("FUBON_USER_ID", "")
FUBON_PASSWORD = os.getenv("FUBON_PASSWORD", "")
FUBON_CERT_PATH = os.getenv("FUBON_CERT_PATH", "")
FUBON_CERT_PASSWORD = os.getenv("FUBON_CERT_PASSWORD", "")
FUBON_SIMULATION = os.getenv("FUBON_SIMULATION", "true").lower() == "true"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "nebula_admin_2026")
PORT = int(os.getenv("PORT", "8080"))

CMDS = ["echo","cat","ls","ps","df","free","uptime","tail","head","grep","curl","python3","pip3","pip","pkill","sleep","nohup","uvicorn","systemctl","sed","awk","wc","find","mkdir","cp","mv","chmod","env","which","ping","date","hostname","ss","lsof","git","bash","sh","wget","tee","touch","rm"]

# ==================== 全域變數 ====================
sdk = None
sdk_account_stock = None
sdk_account_futures = None
sdk_logged_in = False
sdk_error = None

# ==================== SDK 初始化 ====================
def init_sdk():
    global sdk, sdk_account_stock, sdk_account_futures, sdk_logged_in, sdk_error
    try:
        from fubon_neo.sdk import FubonSDK
        logger.info(f"初始化 FubonSDK (simulation={FUBON_SIMULATION})")
        sdk = FubonSDK(simulation=FUBON_SIMULATION)
        if not FUBON_USER_ID or not FUBON_PASSWORD or not FUBON_CERT_PATH:
            sdk_error = "缺少登入憑證: FUBON_USER_ID / FUBON_PASSWORD / FUBON_CERT_PATH 未設定"
            logger.error(sdk_error)
            return
        logger.info(f"嘗試登入: user_id={FUBON_USER_ID}, cert={FUBON_CERT_PATH}")
        result = sdk.login(user_id=FUBON_USER_ID, password=FUBON_PASSWORD, cert_path=FUBON_CERT_PATH, cert_password=FUBON_CERT_PASSWORD if FUBON_CERT_PASSWORD else None)
        if not result or not result.data:
            sdk_error = "登入失敗：未取得帳戶資料"
            logger.error(sdk_error)
            return
        accounts = result.data
        logger.info(f"登入成功，共 {len(accounts)} 個帳戶")
        for acc in accounts:
            acc_type = getattr(acc, "account_type", "").lower()
            logger.info(f"  帳戶: {getattr(acc, 'account_id', '?')} 類型: {acc_type}")
            if "future" in acc_type or "fut" in acc_type:
                sdk_account_futures = acc
            else:
                sdk_account_stock = acc
        if not sdk_account_stock and accounts:
            sdk_account_stock = accounts[0]
        if not sdk_account_futures and len(accounts) > 1:
            sdk_account_futures = accounts[1]
        elif not sdk_account_futures and accounts:
            sdk_account_futures = accounts[0]
        sdk_logged_in = True
        sdk_error = None
        logger.info("SDK 登入完成 ✓")
    except ImportError:
        sdk_error = "fubon_neo 套件未安裝"
        logger.error(sdk_error)
    except Exception as e:
        sdk_error = str(e)
        logger.error(f"SDK 初始化失敗: {e}")

# ==================== FastAPI Lifespan ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_sdk()
    yield

app = FastAPI(title="Fubon Neo SDK Bridge", version="3.2.0", lifespan=lifespan)

def now_cst() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ==================== Request Models ====================
class StockOrderReq(BaseModel):
    symbol: str
    action: str
    quantity: int
    price_type: str = "limit"
    price: Optional[float] = None

class FuturesOrderReq(BaseModel):
    symbol: str
    action: str
    quantity: int
    price_type: str = "limit"
    price: Optional[float] = None

class CancelOrderReq(BaseModel):
    order_id: str

class ExecReq(BaseModel):
    cmd: str
    timeout: Optional[int] = 60

# ==================== 路由 1: 根端點 ====================
@app.get("/")
async def root():
    return {
        "service": "Fubon Neo SDK Bridge API",
        "version": "3.2.0",
        "timestamp": now_cst(),
        "sdk_status": "logged_in" if sdk_logged_in else "not_logged_in",
        "simulation": FUBON_SIMULATION,
        "error": sdk_error
    }

# ==================== 路由 2: 健康檢查 ====================
@app.get("/health")
async def health():
    return {
        "ok": sdk_logged_in,
        "timestamp": now_cst(),
        "simulation": FUBON_SIMULATION,
        "sdk_logged_in": sdk_logged_in,
        "version": "3.2.0",
        "error": sdk_error
    }

# ==================== 路由 3: Admin 重新初始化 ====================
@app.post("/admin/reinit")
async def admin_reinit(x_admin_secret: Optional[str] = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="無效的 Admin Secret")
    logger.info("收到 /admin/reinit 請求，重新初始化 SDK")
    init_sdk()
    return {
        "ok": True,
        "sdk_logged_in": sdk_logged_in,
        "timestamp": now_cst(),
        "error": sdk_error
    }

# ==================== 路由 NEW: /admin/exec ====================
@app.post("/admin/exec")
async def admin_exec(req: ExecReq, x_admin_secret: Optional[str] = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="無效的 Admin Secret")
    try:
        parts = shlex.split(req.cmd)
        base = os.path.basename(parts[0])
        if base not in CMDS:
            raise HTTPException(403, f"指令不在白名單: {base}")
        r = subprocess.run(req.cmd, shell=True, capture_output=True, text=True, timeout=req.timeout)
        logger.info(f"admin_exec: {req.cmd} -> rc={r.returncode}")
        return {"stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "returncode": r.returncode, "timestamp": now_cst()}
    except subprocess.TimeoutExpired:
        raise HTTPException(408, f"指令逾時 {req.timeout}s")
    except Exception as e:
        raise HTTPException(500, f"執行失敗: {e}")

# ==================== 路由 NEW: /admin/git-pull ====================
@app.post("/admin/git-pull")
async def admin_git_pull(x_admin_secret: Optional[str] = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="無效的 Admin Secret")
    try:
        r = subprocess.run(
            "cd /opt/trading-api && git pull origin main 2>&1",
            shell=True, capture_output=True, text=True, timeout=30
        )
        logger.info(f"git pull result: {r.stdout}")
        # 背景重啟服務
        subprocess.Popen("sleep 2 && systemctl restart trading-api", shell=True)
        return {"ok": True, "git_output": r.stdout.strip(), "message": "git pull 完成，服務將在2秒後重啟", "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"git pull 失敗: {e}")

# ==================== 路由 4: 查詢帳戶 ====================
@app.get("/api/accounts")
async def get_accounts():
    if not sdk_logged_in:
        raise HTTPException(503, "SDK 未登入")
    return {
        "stock_account": getattr(sdk_account_stock, "account_id", None) if sdk_account_stock else None,
        "futures_account": getattr(sdk_account_futures, "account_id", None) if sdk_account_futures else None,
        "timestamp": now_cst()
    }

# ==================== 路由 5: 查詢股票部位 ====================
@app.get("/api/positions/stock")
async def get_stock_positions():
    if not sdk_logged_in or not sdk_account_stock:
        raise HTTPException(503, "股票帳戶未登入")
    try:
        positions = sdk.stock.get_positions(sdk_account_stock)
        data = positions.data if positions else []
        return {"positions": [p.__dict__ if hasattr(p, "__dict__") else str(p) for p in data], "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"查詢失敗: {e}")

# ==================== 路由 6: 查詢期貨部位 ====================
@app.get("/api/positions/futures")
async def get_futures_positions():
    if not sdk_logged_in or not sdk_account_futures:
        raise HTTPException(503, "期貨帳戶未登入")
    try:
        positions = sdk.futopt.get_positions(sdk_account_futures)
        data = positions.data if positions else []
        return {"positions": [p.__dict__ if hasattr(p, "__dict__") else str(p) for p in data], "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"查詢失敗: {e}")

# ==================== 路由 7: 查詢股票餘額 ====================
@app.get("/api/balance/stock")
async def get_stock_balance():
    if not sdk_logged_in or not sdk_account_stock:
        raise HTTPException(503, "股票帳戶未登入")
    try:
        balance = sdk.stock.get_balance(sdk_account_stock)
        data = balance.data.__dict__ if balance and hasattr(balance.data, "__dict__") else str(balance.data) if balance else None
        return {"balance": data, "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"查詢失敗: {e}")

# ==================== 路由 8: 查詢期貨餘額 ====================
@app.get("/api/balance/futures")
async def get_futures_balance():
    if not sdk_logged_in or not sdk_account_futures:
        raise HTTPException(503, "期貨帳戶未登入")
    try:
        balance = sdk.futopt.get_balance(sdk_account_futures)
        data = balance.data.__dict__ if balance and hasattr(balance.data, "__dict__") else str(balance.data) if balance else None
        return {"balance": data, "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"查詢失敗: {e}")

# ==================== 路由 9: 股票下單 ====================
@app.post("/api/order/stock")
async def order_stock(req: StockOrderReq):
    if not sdk_logged_in or not sdk_account_stock:
        raise HTTPException(503, "股票帳戶未登入")
    try:
        from fubon_neo.constant import Action, PriceType
        action_map = {"buy": Action.Buy, "sell": Action.Sell}
        price_type_map = {"limit": PriceType.Limit, "market": PriceType.Market}
        action_enum = action_map.get(req.action.lower())
        price_type_enum = price_type_map.get(req.price_type.lower())
        if not action_enum or not price_type_enum:
            raise ValueError(f"無效參數: action={req.action}, price_type={req.price_type}")
        from fubon_neo.sdk import Order
        order = Order(
            buy_sell=action_enum,
            symbol=req.symbol,
            quantity=req.quantity,
            price=req.price if price_type_enum == PriceType.Limit else None,
            price_type=price_type_enum,
            order_type="stock"
        )
        result = sdk.stock.place_order(sdk_account_stock, order)
        if not result or not result.data:
            raise HTTPException(500, f"下單失敗: {result}")
        logger.info(f"股票下單成功: {req.symbol} {req.action} {req.quantity}")
        return {"ok": True, "order_id": getattr(result.data, "order_id", None), "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"下單失敗: {e}")

# ==================== 路由 10: 期貨下單 ====================
@app.post("/api/order/futures")
async def order_futures(req: FuturesOrderReq):
    if not sdk_logged_in or not sdk_account_futures:
        raise HTTPException(503, "期貨帳戶未登入")
    try:
        from fubon_neo.constant import Action, PriceType
        action_map = {"buy": Action.Buy, "sell": Action.Sell}
        price_type_map = {"limit": PriceType.Limit, "market": PriceType.Market}
        action_enum = action_map.get(req.action.lower())
        price_type_enum = price_type_map.get(req.price_type.lower())
        if not action_enum or not price_type_enum:
            raise ValueError(f"無效參數: action={req.action}, price_type={req.price_type}")
        from fubon_neo.sdk import Order
        order = Order(
            buy_sell=action_enum,
            symbol=req.symbol,
            quantity=req.quantity,
            price=req.price if price_type_enum == PriceType.Limit else None,
            price_type=price_type_enum,
            order_type="futures"
        )
        result = sdk.futopt.place_order(sdk_account_futures, order)
        if not result or not result.data:
            raise HTTPException(500, f"下單失敗: {result}")
        logger.info(f"期貨下單成功: {req.symbol} {req.action} {req.quantity}")
        return {"ok": True, "order_id": getattr(result.data, "order_id", None), "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"下單失敗: {e}")

# ==================== 路由 11: 取消委託 ====================
@app.post("/api/order/cancel")
async def cancel_order(req: CancelOrderReq):
    if not sdk_logged_in:
        raise HTTPException(503, "SDK 未登入")
    try:
        result = sdk.stock.cancel_order(sdk_account_stock, req.order_id)
        if not result:
            raise HTTPException(500, f"取消失敗: {result}")
        logger.info(f"取消委託成功: {req.order_id}")
        return {"ok": True, "order_id": req.order_id, "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"取消失敗: {e}")

# ==================== 路由 12: 查詢報價 ====================
@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str):
    if not sdk_logged_in:
        raise HTTPException(503, "SDK 未登入")
    try:
        quote = sdk.marketdata.rest_client.stock.intraday.quote(symbol=symbol)
        data = quote.data.__dict__ if quote and hasattr(quote.data, "__dict__") else str(quote.data) if quote else None
        return {"quote": data, "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"查詢失敗: {e}")

# ==================== 主程式進入點 ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)