#!/usr/bin/env python3
"""富邦 Neo SDK Bridge API v4.0 — 機構級重構 2026-03-06"""

import os, sys, logging, subprocess, shlex
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fubon-bridge")

sdk = None
sdk_error = None
sdk_ready = False
accounts = []

CMDS = ["echo","cat","ls","ps","df","free","uptime","tail","head","grep","curl","python3","pip3","pkill","sleep","nohup","uvicorn","systemctl","sed","awk","wc","find","mkdir","cp","mv","chmod","env","which","ping","date","hostname","ss","lsof"]

def now_cst():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S CST")

def init_sdk():
    global sdk, sdk_error, sdk_ready, accounts
    u = os.environ.get("FUBON_USER_ID", "")
    p = os.environ.get("FUBON_PASSWORD", "")
    c = os.environ.get("FUBON_CERT_PATH", "")
    if not all([u, p, c]):
        sdk_error = "ENV未設定: FUBON_USER_ID/FUBON_PASSWORD/FUBON_CERT_PATH"
        logger.warning(f"[SDK] {sdk_error}")
        return
    try:
        from fubon_neo.sdk import FubonSDK
        sdk = FubonSDK()
        r = sdk.login(u, p, c)
        if r and hasattr(r, "data") and r.data:
            accounts = r.data
            sdk_ready = True
            logger.info(f"[SDK] 登入成功 {len(accounts)} 帳號")
        else:
            sdk_error = f"登入失敗: {r}"
            logger.error(f"[SDK] {sdk_error}")
    except ImportError as e:
        sdk_error = f"SDK套件未安裝: {e}"
        logger.error(f"[SDK] {sdk_error}")
    except Exception as e:
        sdk_error = f"SDK異常: {type(e).__name__}: {e}"
        logger.error(f"[SDK] {sdk_error}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[API] 啟動，初始化SDK...")
    init_sdk()
    logger.info(f"[API] 就緒 sdk_ready={sdk_ready} error={sdk_error}")
    yield
    logger.info("[API] 關閉")

app = FastAPI(title="富邦Neo SDK Bridge API", version="4.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ExecReq(BaseModel):
    cmd: str
    timeout: Optional[int] = 30

class OrderReq(BaseModel):
    symbol: str
    side: str
    qty: int
    price: Optional[float] = None
    order_type: str = "LIMIT"

@app.get("/")
async def root():
    return {"service": "富邦Neo SDK Bridge API", "version": "4.0.0", "status": "online", "timestamp": now_cst()}

@app.get("/health")
async def health():
    return {"status": "healthy", "sdk_ready": sdk_ready, "sdk_error": sdk_error, "accounts": len(accounts), "python": sys.version.split()[0], "timestamp": now_cst()}

@app.post("/exec")
async def exec_cmd(req: ExecReq):
    try:
        parts = shlex.split(req.cmd)
    except Exception as e:
        raise HTTPException(400, f"解析失敗: {e}")
    if not parts:
        raise HTTPException(400, "空指令")
    if os.path.basename(parts[0]) not in CMDS:
        raise HTTPException(403, f"指令不在白名單: {parts[0]}")
    try:
        r = subprocess.run(req.cmd, shell=True, capture_output=True, text=True, timeout=req.timeout)
        return {"stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "returncode": r.returncode, "timestamp": now_cst()}
    except subprocess.TimeoutExpired:
        raise HTTPException(408, f"超時 {req.timeout}s")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/sdk/status")
async def sdk_status():
    return {"sdk_ready": sdk_ready, "sdk_error": sdk_error, "accounts": [str(a) for a in accounts], "timestamp": now_cst()}

@app.post("/sdk/reconnect")
async def sdk_reconnect():
    global sdk, sdk_error, sdk_ready, accounts
    sdk = None; sdk_error = None; sdk_ready = False; accounts = []
    init_sdk()
    return {"sdk_ready": sdk_ready, "sdk_error": sdk_error, "timestamp": now_cst()}

@app.post("/order/place")
async def place_order(req: OrderReq):
    if not sdk_ready:
        raise HTTPException(503, f"SDK未就緒: {sdk_error}")
    try:
        from fubon_neo.sdk import BSAction, PriceType, TimeInForce
        bs = BSAction.Buy if req.side.upper() == "BUY" else BSAction.Sell
        pt = PriceType.Market if req.order_type == "MARKET" else PriceType.Limit
        o = sdk.stock.place_order(accounts[0], req.symbol, bs, req.qty, req.price or 0, pt, TimeInForce.ROD)
        return {"success": True, "order_id": getattr(o, "order_no", None), "detail": str(o), "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"委託失敗: {type(e).__name__}: {e}")

@app.get("/quote/{symbol}")
async def get_quote(symbol: str):
    if not sdk_ready:
        raise HTTPException(503, f"SDK未就緒: {sdk_error}")
    try:
        q = sdk.marketdata.intraday.quote(symbol=symbol)
        return {"symbol": symbol, "data": q.data if hasattr(q, "data") else str(q), "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"報價失敗: {e}")

@app.get("/positions")
async def get_positions():
    if not sdk_ready:
        raise HTTPException(503, f"SDK未就緒: {sdk_error}")
    try:
        pos = sdk.stock.get_positions(accounts[0])
        return {"positions": [str(p) for p in (pos.data or [])], "timestamp": now_cst()}
    except Exception as e:
        raise HTTPException(500, f"持倉失敗: {e}")

@app.get("/market/snapshot")
async def market_snapshot():
    import json, pathlib
    p = pathlib.Path("/opt/trading-api/data/data_snapshot_latest.json")
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:
            return {"error": str(e), "timestamp": now_cst()}
    return {"error": "快照不存在", "timestamp": now_cst()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False, log_level="info")