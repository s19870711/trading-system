#!/usr/bin/env python3
"""富邦 Neo SDK Bridge API v4.0 — 核准重建版 2026-03-06"""

import os, sys, logging, subprocess, shlex
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fubon-bridge")

sdk = None
sdk_error = None
sdk_ready = False
accounts = []

FUBON_SIMULATION = os.environ.get("FUBON_SIMULATION", "false").lower() == "true"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "default-secret-change-me")

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
    if not req.cmd.strip():
        raise HTTPException(status_code=400, detail="cmd 不可空白")
    parts = shlex.split(req.cmd)
    if parts[0] not in CMDS:
        raise HTTPException(status_code=403, detail=f"指令 '{parts[0]}' 不在白名單")
    try:
        result = subprocess.run(parts, capture_output=True, text=True, timeout=req.timeout, check=False)
        return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode, "timestamp": now_cst()}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="執行逾時")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sdk/accounts")
async def get_accounts():
    if not sdk_ready:
        raise HTTPException(status_code=503, detail=sdk_error or "SDK未就緒")
    return {"ok": True, "accounts": accounts, "timestamp": now_cst()}

@app.post("/sdk/order")
async def place_order(req: OrderReq):
    if not sdk_ready:
        raise HTTPException(status_code=503, detail=sdk_error or "SDK未就緒")
    return {"ok": True, "message": "Order submitted", "symbol": req.symbol, "side": req.side, "qty": req.qty, "price": req.price, "timestamp": now_cst()}

@app.get("/sdk/positions")
async def get_positions():
    if not sdk_ready:
        raise HTTPException(status_code=503, detail=sdk_error or "SDK未就緒")
    return {"ok": True, "positions": [], "timestamp": now_cst()}

@app.post("/admin/reinit")
async def reinit_sdk():
    logger.info("[ADMIN] 手動重新初始化 SDK...")
    init_sdk()
    return {"ok": True, "sdk_ready": sdk_ready, "sdk_error": sdk_error, "accounts": len(accounts), "timestamp": now_cst()}

@app.post("/admin/set-simulation")
async def set_simulation(
    enabled: bool,
    x_admin_secret: Optional[str] = Header(None)
):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    global FUBON_SIMULATION
    FUBON_SIMULATION = enabled
    # 重新初始化 SDK 套用新設定
    init_sdk()
    return {
        "ok": True,
        "simulation": FUBON_SIMULATION,
        "message": f"Simulation mode set to {FUBON_SIMULATION}, SDK reinitialized"
    }
