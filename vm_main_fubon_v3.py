#!/usr/bin/env python3
"""
Fubon Neo SDK Bridge API - v3.1.1
VM: 104.199.185.65:8080
v3.1.1: /admin/reinit 新增 git_pull 參數，支援遠端程式碼更新
"""

import os
import json
import logging
import subprocess
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

FUBON_USER_ID = os.getenv("FUBON_USER_ID", "")
FUBON_PASSWORD = os.getenv("FUBON_PASSWORD", "")
FUBON_CERT_PATH = os.getenv("FUBON_CERT_PATH", "")
FUBON_CERT_PASSWORD = os.getenv("FUBON_CERT_PASSWORD", "")
FUBON_SIMULATION = os.getenv("FUBON_SIMULATION", "true").lower() == "true"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "nebula_admin_2026")
PORT = int(os.getenv("PORT", "8080"))

sdk = None
sdk_account_stock = None
sdk_account_futures = None
sdk_logged_in = False
sdk_error = None

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
            sdk_error = "登入失敗：未取得帳號資料"
            logger.error(sdk_error)
            return
        accounts = result.data
        logger.info(f"登入成功，共 {len(accounts)} 個帳號")
        for acc in accounts:
            acc_type = getattr(acc, "account_type", "").lower()
            logger.info(f"  帳號: {getattr(acc, 'account_id', '?')} 類型: {acc_type}")
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Fubon Bridge v3.1.1 啟動 ===")
    init_sdk()
    yield
    if sdk and sdk_logged_in:
        try:
            sdk.logout()
            logger.info("SDK 登出完成")
        except Exception:
            pass

app = FastAPI(title="Fubon Neo SDK Bridge", version="3.1.1", description="富邦 Neo SDK REST Bridge — 股票+期貨下單、即時報價、帳戶查詢", lifespan=lifespan)

class StockOrderRequest(BaseModel):
    symbol: str
    action: str
    quantity: int
    price: Optional[float] = None
    order_type: str = "LIMIT"
    time_in_force: str = "ROD"
    market_type: str = "COMMON"
    user_def: Optional[str] = None

class FuturesOrderRequest(BaseModel):
    symbol: str
    action: str
    quantity: int
    price: Optional[float] = None
    order_type: str = "LIMIT"
    time_in_force: str = "ROD"
    session: str = "DAY"
    user_def: Optional[str] = None

class CancelOrderRequest(BaseModel):
    order_id: str
    market: str = "STOCK"

def require_sdk():
    if not sdk_logged_in:
        raise HTTPException(status_code=503, detail=f"SDK 未登入: {sdk_error}")

def require_admin(x_admin_secret: Optional[str]):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

def ts():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

@app.get("/health")
def health():
    return {"status": "healthy" if sdk_logged_in else "degraded", "version": "3.1.1", "simulation": FUBON_SIMULATION, "sdk_available": sdk is not None, "sdk_logged_in": sdk_logged_in, "sdk_error": sdk_error, "stock_account": getattr(sdk_account_stock, "account_id", None), "futures_account": getattr(sdk_account_futures, "account_id", None), "timestamp": ts()}

@app.post("/admin/reinit")
def admin_reinit(x_admin_secret: Optional[str] = Header(None), git_pull: bool = False):
    require_admin(x_admin_secret)
    
    if git_pull:
        logger.info("執行 git pull...")
        r = subprocess.run("cd /opt/trading-api && git pull origin main 2>&1", shell=True, capture_output=True, text=True, timeout=30)
        git_output = r.stdout.strip()
        logger.info(f"git pull: {git_output}")
        # 背景重啟進程
        subprocess.Popen("sleep 1 && systemctl restart trading-api 2>/dev/null || pkill -f 'uvicorn.*vm_main_fubon_v3'", shell=True)
        return {"ok": True, "git_pull": True, "git_output": git_output, "message": "git pull 完成，服務重啟中", "timestamp": ts()}
    
    init_sdk()
    return {"ok": True, "sdk_logged_in": sdk_logged_in, "sdk_error": sdk_error}

@app.get("/api/quote/stock/{symbol}")
def quote_stock(symbol: str):
    require_sdk()
    try:
        result = sdk.marketdata.rest_client.stock.intraday.quote(symbol)
        return {"ok": True, "symbol": symbol, "data": result, "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stocks/realtime")
def stocks_realtime(symbols: List[str]):
    require_sdk()
    results = {}
    errors = {}
    for sym in symbols:
        try:
            r = sdk.marketdata.rest_client.stock.intraday.quote(sym)
            results[sym] = r
        except Exception as e:
            errors[sym] = str(e)
    return {"ok": len(errors) == 0, "data": results, "errors": errors, "timestamp": ts()}

@app.get("/api/index/realtime")
def index_realtime():
    require_sdk()
    try:
        result = sdk.marketdata.rest_client.stock.intraday.quote("IX0001")
        return {"ok": True, "symbol": "IX0001", "data": result, "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/futures/realtime")
def futures_realtime():
    require_sdk()
    try:
        from fubon_neo.constant import FutOptMarketType
        result = sdk.futopt.get_order_results(sdk_account_futures, FutOptMarketType.Future)
        return {"ok": True, "data": str(result), "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/order/stock")
def place_stock_order(req: StockOrderRequest):
    require_sdk()
    try:
        from fubon_neo.sdk import Order
        from fubon_neo.constant import BSAction, PriceType, MarketType, TimeInForce, OrderType
        buy_sell = BSAction.Buy if req.action.upper() == "BUY" else BSAction.Sell
        price_type = {"LIMIT": PriceType.Limit, "MARKET": PriceType.Market}.get(req.order_type.upper(), PriceType.Limit)
        market_type = {"COMMON": MarketType.Common, "ODD_LOT": MarketType.OddLot, "AFTER_MARKET": MarketType.AfterMarket}.get(req.market_type.upper(), MarketType.Common)
        tif = {"ROD": TimeInForce.ROD, "IOC": TimeInForce.IOC, "FOK": TimeInForce.FOK}.get(req.time_in_force.upper(), TimeInForce.ROD)
        order = Order(buy_sell=buy_sell, symbol=req.symbol, price=str(req.price) if req.price else "0", quantity=req.quantity, market_type=market_type, price_type=price_type, time_in_force=tif, order_type=OrderType.Stock, user_def=req.user_def or "")
        result = sdk.stock.place_order(sdk_account_stock, order)
        return {"ok": True, "order_id": getattr(result, "order_id", None), "data": str(result), "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/order/futures")
def place_futures_order(req: FuturesOrderRequest):
    require_sdk()
    try:
        from fubon_neo.sdk import Order
        from fubon_neo.constant import BSAction, FuturesPriceType, FuturesTimeInForce, FuturesOrderType, FuturesMarketType
        buy_sell = BSAction.Buy if req.action.upper() == "BUY" else BSAction.Sell
        price_type = {"LIMIT": FuturesPriceType.Limit, "MARKET": FuturesPriceType.Market}.get(req.order_type.upper(), FuturesPriceType.Limit)
        session = {"DAY": FuturesMarketType.DayTrade, "NIGHT": FuturesMarketType.NightTrade}.get(req.session.upper(), FuturesMarketType.DayTrade)
        tif = {"ROD": FuturesTimeInForce.ROD, "IOC": FuturesTimeInForce.IOC, "FOK": FuturesTimeInForce.FOK}.get(req.time_in_force.upper(), FuturesTimeInForce.ROD)
        order = Order(buy_sell=buy_sell, symbol=req.symbol, price=str(req.price) if req.price else "0", quantity=req.quantity, market_type=session, price_type=price_type, time_in_force=tif, order_type=FuturesOrderType.Futures, user_def=req.user_def or "")
        result = sdk.futopt.place_order(sdk_account_futures, order)
        return {"ok": True, "order_id": getattr(result, "order_id", None), "data": str(result), "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/order/cancel")
def cancel_order(req: CancelOrderRequest):
    require_sdk()
    try:
        if req.market.upper() == "FUTURES":
            result = sdk.futopt.cancel_order(sdk_account_futures, req.order_id)
        else:
            result = sdk.stock.cancel_order(sdk_account_stock, req.order_id)
        return {"ok": True, "data": str(result), "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/stock")
def get_stock_orders():
    require_sdk()
    try:
        result = sdk.stock.get_order_results(sdk_account_stock)
        orders = result.data if hasattr(result, "data") else []
        return {"ok": True, "count": len(orders), "data": [str(o) for o in orders], "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/futures")
def get_futures_orders():
    require_sdk()
    try:
        from fubon_neo.constant import FutOptMarketType
        result = sdk.futopt.get_order_results(sdk_account_futures, FutOptMarketType.Future)
        orders = result.data if hasattr(result, "data") else []
        return {"ok": True, "count": len(orders), "data": [str(o) for o in orders], "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/positions/stock")
def get_stock_positions():
    require_sdk()
    try:
        result = sdk.stock.get_inventories(sdk_account_stock)
        positions = result.data if hasattr(result, "data") else []
        return {"ok": True, "count": len(positions), "data": [str(p) for p in positions], "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/positions/futures")
def get_futures_positions():
    require_sdk()
    try:
        result = sdk.futopt.get_position(sdk_account_futures)
        positions = result.data if hasattr(result, "data") else []
        return {"ok": True, "count": len(positions), "data": [str(p) for p in positions], "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/balance/stock")
def get_stock_balance():
    require_sdk()
    try:
        result = sdk.stock.get_account_balance(sdk_account_stock)
        return {"ok": True, "data": str(result.data) if result.data else None, "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/balance/futures")
def get_futures_balance():
    require_sdk()
    try:
        result = sdk.futopt.get_account_balance(sdk_account_futures)
        return {"ok": True, "data": str(result.data) if result.data else None, "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/market/snapshot")
def market_snapshot():
    require_sdk()
    symbols = ["2330", "2317", "2454", "2308", "2303", "3008"]
    snapshot = {}
    for sym in symbols:
        try:
            r = sdk.marketdata.rest_client.stock.intraday.quote(sym)
            snapshot[sym] = {"price": getattr(r, "closePrice", None) or getattr(r, "lastPrice", None), "source": "fubon_sdk", "timestamp": ts()}
        except Exception as e:
            snapshot[sym] = {"error": str(e), "source": "fubon_sdk"}
    return {"ok": True, "snapshot": snapshot, "timestamp": ts()}

@app.get("/market/snapshot/var")
def market_snapshot_var():
    return market_snapshot()

def get_near_month_contract() -> str:
    """動態計算台指期近月合約代碼（TXFX0 格式，X=月份字母A-L，0=年份末位）"""
    from datetime import date, timedelta
    now = date.today()
    # 找當月第三個週三（結算日）
    first_day = now.replace(day=1)
    first_weekday = first_day.weekday()  # 0=Monday
    days_to_wed = (2 - first_weekday) % 7
    first_wed = first_day + timedelta(days=days_to_wed)
    third_wed = first_wed + timedelta(weeks=2)
    # 若今天已過結算日，用下個月
    if now > third_wed:
        if now.month == 12:
            target = now.replace(year=now.year + 1, month=1, day=1)
        else:
            target = now.replace(month=now.month + 1, day=1)
    else:
        target = now
    month_code = chr(ord('A') + target.month - 1)  # A=1月, B=2月, ..., L=12月
    year_digit = str(target.year)[-1]
    return f"TXF{month_code}{year_digit}"

@app.get("/market/futures/taifex")
def futures_taifex():
    require_sdk()
    try:
        symbol = get_near_month_contract()
        r = sdk.marketdata.rest_client.futopt.intraday.quote(symbol)
        return {"ok": True, "symbol": symbol, "price": getattr(r, "closePrice", None) or getattr(r, "lastPrice", None), "data": str(r), "source": "fubon_sdk_futopt", "timestamp": ts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{symbol} query failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
