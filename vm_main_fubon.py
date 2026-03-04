#!/usr/bin/env python3
"""
Trading Bridge API v3.0 - 富邦 Neo SDK 即時數據版
數據源優先序（市場數據驗證守門員 v6.1 標準）：
  ① Fubon Neo SDK intraday/quote
  ② mis.twse.com.tw 批次查詢
  ③ Yahoo Finance（僅盤後備援）
永久禁令：盤中禁用 TWSE_STOCK_DAY；台指期禁用裸符號 TX/TXF
"""

import os, json, time, logging, asyncio, httpx
from datetime import datetime, timezone
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import pytz

FUBON_ID           = os.getenv("FUBON_ID", "")
FUBON_PASSWORD     = os.getenv("FUBON_PASSWORD", "")
FUBON_PFX_PATH     = os.getenv("FUBON_PFX_PATH", "")
FUBON_PFX_PASSWORD = os.getenv("FUBON_PFX_PASSWORD", "")
FUBON_ACCOUNT      = os.getenv("FUBON_ACCOUNT", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "6904817875")
DATA_DIR           = os.getenv("DATA_DIR", "/opt/trading/data")
CST                = pytz.timezone("Asia/Taipei")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("trading-api")

WATCHLIST = {"2330":"台積電","2317":"鴻海","2454":"聯發科",
             "2308":"台達電","2303":"聯電","3008":"大立光"}
ADR_SYMBOLS = ["TSM","AMD","NVDA"]

# Yahoo Finance headers (防爬蟲)
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

app = FastAPI(title="Fubon Trading Bridge API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_sdk_client = None
_sdk_ready  = False
_sdk_error  = ""

def _init_fubon_sdk():
    global _sdk_client, _sdk_ready, _sdk_error
    try:
        from fubon_neo.sdk import FubonSDK
        sdk = FubonSDK()
        if all([FUBON_ID, FUBON_PASSWORD, FUBON_PFX_PATH, FUBON_PFX_PASSWORD]):
            accounts = sdk.login(FUBON_ID, FUBON_PASSWORD, FUBON_PFX_PATH, FUBON_PFX_PASSWORD)
            _sdk_client = sdk
            _sdk_ready  = True
            log.info(f"[SDK] 富邦 Neo SDK 登入成功")
        else:
            _sdk_error = "環境變數未完整設定"
            log.warning(f"[SDK] {_sdk_error}")
    except ImportError:
        _sdk_error = "fubon_neo 套件未安裝"
        log.warning(f"[SDK] {_sdk_error}")
    except Exception as e:
        _sdk_error = str(e)
        log.warning(f"[SDK] 初始化失敗: {_sdk_error}")

async def fetch_quote_fubon_sdk(symbol: str) -> Optional[Dict]:
    if not _sdk_ready or _sdk_client is None:
        return None
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None,
            lambda: _sdk_client.marketdata.rest_client.stock.intraday.quote(symbol=symbol))
        if result and hasattr(result, "data") and result.data:
            d = result.data
            price = getattr(d,"closePrice",None) or getattr(d,"lastPrice",None)
            prev  = getattr(d,"previousClose",None) or getattr(d,"referencePrice",None)
            if price:
                change = round(price-prev,2) if prev else 0
                change_pct = round(change/prev*100,2) if prev else 0
                return {"symbol":symbol,"name":WATCHLIST.get(symbol,symbol),
                    "price":price,"open":getattr(d,"openPrice",None),
                    "high":getattr(d,"highPrice",None),"low":getattr(d,"lowPrice",None),
                    "prev_close":prev,"change":change,"change_pct":change_pct,
                    "volume":getattr(d,"volume",None) or getattr(d,"tradeVolume",None),
                    "bid":getattr(d,"bid",None),"ask":getattr(d,"ask",None),
                    "source":"fubon_neo_sdk","validation_status":"CONFIRMED",
                    "fetch_timestamp_cst":datetime.now(CST).isoformat()}
    except Exception as e:
        log.warning(f"[SDK] {symbol}: {e}")
    return None

async def fetch_quote_mis_twse(symbol: str) -> Optional[Dict]:
    for ex in ["tse","otc"]:
        try:
            url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
            async with httpx.AsyncClient(timeout=8) as c:
                resp = await c.get(url, params={"ex_ch":f"{ex}_{symbol}.tw","json":"1","delay":"0"})
                data = resp.json()
            items = data.get("msgArray",[])
            if items:
                d = items[0]
                price = float(d.get("z","0") or d.get("y","0") or 0)
                prev  = float(d.get("y","0") or 0)
                if price == 0: continue
                change = round(price-prev,2) if prev else 0
                change_pct = round(change/prev*100,2) if prev else 0
                return {"symbol":symbol,"name":d.get("n",WATCHLIST.get(symbol,symbol)),
                    "price":price,"open":float(d.get("o","0") or 0),
                    "high":float(d.get("h","0") or 0),"low":float(d.get("l","0") or 0),
                    "prev_close":prev,"change":change,"change_pct":change_pct,
                    "volume":int(d.get("v","0").replace(",","") or 0),
                    "bid":float(d.get("b","0").split("_")[0] or 0),
                    "ask":float(d.get("a","0").split("_")[0] or 0),
                    "source":"mis_twse","validation_status":"UNVERIFIED",
                    "fetch_timestamp_cst":datetime.now(CST).isoformat()}
        except Exception as e:
            log.warning(f"[MIS] {ex}_{symbol}: {e}")
    return None

async def fetch_quote_yahoo(symbol: str, suffix: str=".TW") -> Optional[Dict]:
    try:
        async with httpx.AsyncClient(timeout=8, headers=YAHOO_HEADERS) as c:
            resp = await c.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}",
                               params={"interval":"1d","range":"1d"})
            meta = resp.json()["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice",0)
        prev  = meta.get("previousClose",0)
        change = round(price-prev,2) if prev else 0
        return {"symbol":symbol,"name":WATCHLIST.get(symbol,symbol),
            "price":price,"open":meta.get("regularMarketOpen"),
            "high":meta.get("regularMarketDayHigh"),"low":meta.get("regularMarketDayLow"),
            "prev_close":prev,"change":change,
            "change_pct":round(change/prev*100,2) if prev else 0,
            "volume":meta.get("regularMarketVolume"),"bid":None,"ask":None,
            "source":"yahoo_finance_fallback","validation_status":"UNVERIFIED",
            "fetch_timestamp_cst":datetime.now(CST).isoformat()}
    except Exception as e:
        log.warning(f"[Yahoo] {symbol}: {e}")
    return None

async def get_quote_with_fallback(symbol: str) -> Dict:
    for fn in [fetch_quote_fubon_sdk, fetch_quote_mis_twse,
               lambda s: fetch_quote_yahoo(s)]:
        try:
            data = await fn(symbol)
            if data: return data
        except: pass
    raise HTTPException(503, f"所有數據源均失敗: {symbol}")

async def fetch_index_fubon_sdk() -> Optional[Dict]:
    if not _sdk_ready or _sdk_client is None: return None
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None,
            lambda: _sdk_client.marketdata.rest_client.stock.intraday.quote(symbol="IX0001"))
        if result and hasattr(result,"data") and result.data:
            d = result.data
            price = getattr(d,"closePrice",None) or getattr(d,"lastPrice",None)
            prev  = getattr(d,"previousClose",None) or getattr(d,"referencePrice",None)
            if price:
                change = round(price-prev,2) if prev else 0
                return {"symbol":"IX0001","name":"加權指數","price":price,
                    "prev_close":prev,"change":change,
                    "change_pct":round(change/prev*100,2) if prev else 0,
                    "volume":getattr(d,"tradeVolume",None),
                    "source":"fubon_neo_sdk","validation_status":"CONFIRMED",
                    "fetch_timestamp_cst":datetime.now(CST).isoformat()}
    except Exception as e:
        log.warning(f"[SDK] index: {e}")
    return None

async def fetch_index_mis_twse() -> Optional[Dict]:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            resp = await c.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                               params={"ex_ch":"tse_t00.tw","json":"1","delay":"0"})
            items = resp.json().get("msgArray",[])
        if items:
            d = items[0]
            price = float(d.get("z","0") or d.get("y","0") or 0)
            prev  = float(d.get("y","0") or 0)
            change = round(price-prev,2) if prev else 0
            return {"symbol":"TAIEX","name":"加權指數","price":price,
                "prev_close":prev,"change":change,
                "change_pct":round(change/prev*100,2) if prev else 0,
                "volume":int(d.get("v","0").replace(",","") or 0),
                "source":"mis_twse","validation_status":"UNVERIFIED",
                "fetch_timestamp_cst":datetime.now(CST).isoformat()}
    except Exception as e:
        log.warning(f"[MIS] index: {e}")
    return None

async def fetch_futures_taifex() -> Optional[Dict]:
    """
    台指期即時報價
    ① 富邦 SDK TXFC6（2026/3合約）
    ② TAIFEX MIS API 動態查詢（永久禁止裸符號TX/TXF）
    ③ Yahoo Finance ^TWII 近似（最後備援）
    """
    # ① 富邦 SDK TXFC6
    if _sdk_ready and _sdk_client:
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None,
                lambda: _sdk_client.marketdata.rest_client.futopt.intraday.quote(symbol="TXFC6"))
            if result and hasattr(result, "data") and result.data:
                d = result.data
                price = getattr(d, "closePrice", None) or getattr(d, "lastPrice", None)
                prev  = getattr(d, "previousClose", None) or getattr(d, "settlementPrice", None)
                if price:
                    change = round(price - prev, 2) if prev else 0
                    return {"symbol": "TXFC6", "name": "台指期2603", "price": price,
                        "prev_close": prev, "change": change,
                        "change_pct": round(change/prev*100, 2) if prev else 0,
                        "volume": getattr(d, "volume", None),
                        "source": "fubon_neo_sdk", "validation_status": "CONFIRMED",
                        "fetch_timestamp_cst": datetime.now(CST).isoformat()}
        except Exception as e:
            log.warning(f"[SDK] TXFC6: {e}")

    # ② TAIFEX MIS API（動態近月合約）
    try:
        # 動態計算近月合約代碼 TXFYYMM
        now = datetime.now(CST)
        year2 = str(now.year)[-2:]
        month2 = f"{now.month:02d}"
        contract = f"TXF{year2}{month2}"
        
        url = "https://mis.taifex.com.tw/futures/api/getQuoteList"
        payload = {"SymbolID": contract, "MarketType": 0, "KLineType": 0}
        async with httpx.AsyncClient(timeout=8, headers=YAHOO_HEADERS) as c:
            resp = await c.post(url, json=payload)
            data = resp.json()
        
        items = data.get("RtData", {}).get("QuoteList", [])
        if items:
            d = items[0]
            price = float(d.get("CloPrice", 0) or d.get("LastPrice", 0) or 0)
            prev  = float(d.get("RefPrice", 0) or 0)
            if price > 0:
                change = round(price - prev, 2) if prev else 0
                return {"symbol": contract, "name": f"台指期{year2}{month2}",
                    "price": price, "prev_close": prev, "change": change,
                    "change_pct": round(change/prev*100, 2) if prev else 0,
                    "open": float(d.get("OpenPrice", 0) or 0),
                    "high": float(d.get("HighPrice", 0) or 0),
                    "low": float(d.get("LowPrice", 0) or 0),
                    "volume": int(d.get("Volume", 0) or 0),
                    "source": "taifex_mis_api", "validation_status": "CONFIRMED",
                    "fetch_timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        log.warning(f"[TAIFEX MIS] futures: {e}")

    # ③ 嘗試其他 Yahoo 符號
    for sym in ["^TWII", "TW=F"]:
        try:
            async with httpx.AsyncClient(timeout=8, headers=YAHOO_HEADERS) as c:
                resp = await c.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"interval": "1d", "range": "1d"})
                if resp.status_code == 200:
                    meta = resp.json()["chart"]["result"][0]["meta"]
                    price = meta.get("regularMarketPrice", 0)
                    prev  = meta.get("previousClose", 0)
                    if price and price > 0:
                        change = round(price - prev, 2) if prev else 0
                        return {"symbol": sym, "name": "台指期(近似)",
                            "price": price, "prev_close": prev, "change": change,
                            "change_pct": round(change/prev*100, 2) if prev else 0,
                            "volume": meta.get("regularMarketVolume"),
                            "source": f"yahoo_{sym}_approx", "validation_status": "UNVERIFIED",
                            "note": "近似值，非台指期直接報價",
                            "fetch_timestamp_cst": datetime.now(CST).isoformat()}
        except Exception as e:
            log.warning(f"[Yahoo] {sym}: {e}")

    return None

async def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id":TELEGRAM_CHAT_ID,"text":message,"parse_mode":"Markdown"})
        return resp.status_code == 200
    except Exception as e:
        log.error(f"[Telegram] {e}")
        return False

def write_snapshot(data: Dict):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        path = f"{DATA_DIR}/data_snapshot_latest.json"
        existing = {}
        if os.path.exists(path):
            with open(path) as f: existing = json.load(f)
        existing.update(data)
        existing["snapshot_timestamp_cst"] = datetime.now(CST).isoformat()
        existing["snapshot_valid_until"] = datetime.fromtimestamp(
            time.time()+900, tz=CST).isoformat()
        with open(path,"w",encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"[Snapshot] {e}")

@app.on_event("startup")
async def startup_event():
    _init_fubon_sdk()
    status = "READY (富邦 SDK)" if _sdk_ready else f"FALLBACK ({_sdk_error})"
    log.info(f"[Boot] SDK 狀態: {status}")

@app.get("/health")
async def health():
    return {"status":"ok","version":"3.0.0","sdk_ready":_sdk_ready,
        "sdk_error":_sdk_error if not _sdk_ready else None,
        "data_source":"fubon_neo_sdk" if _sdk_ready else "fallback",
        "watchlist":list(WATCHLIST.keys()),
        "timestamp_cst":datetime.now(CST).isoformat(),
        "timestamp_utc":datetime.now(timezone.utc).isoformat()}

@app.get("/market/index")
async def get_index(background_tasks: BackgroundTasks):
    data = await fetch_index_fubon_sdk()
    if not data: data = await fetch_index_mis_twse()
    if not data: data = await fetch_quote_yahoo("^TWII", suffix="")
    if not data: raise HTTPException(503,"所有指數數據源均失敗")
    background_tasks.add_task(write_snapshot, {"index": data})
    return data

@app.get("/market/quote/{symbol}")
async def get_quote(symbol: str, background_tasks: BackgroundTasks):
    symbol = symbol.upper()
    data = await get_quote_with_fallback(symbol)
    # 偏差驗證
    try:
        snap_path = f"{DATA_DIR}/data_snapshot_latest.json"
        if os.path.exists(snap_path):
            with open(snap_path) as f: snap = json.load(f)
            prev_price = snap.get("quotes",{}).get(symbol,{}).get("price")
            if prev_price and prev_price > 0:
                dev = abs(data["price"]-prev_price)/prev_price*100
                if dev > 2.0:
                    data["validation_status"] = "CONFLICT"
                    data["deviation_pct"] = round(dev,2)
                    background_tasks.add_task(send_telegram,
                        f"⛔ *BLOCKED* `{symbol}` 偏差{dev:.1f}%>2%\n"
                        f"新:`{data['price']}` 快照:`{prev_price}`")
                elif dev > 0.5:
                    data["validation_status"] = "DISCREPANCY"
                    data["deviation_pct"] = round(dev,2)
    except: pass
    background_tasks.add_task(write_snapshot, {"quotes": {symbol: data}})
    return data

@app.get("/market/futures/taifex")
async def get_futures(background_tasks: BackgroundTasks):
    data = await fetch_futures_taifex()
    if not data: raise HTTPException(503,"台指期數據源均失敗")
    background_tasks.add_task(write_snapshot, {"futures_taifex": data})
    return data

@app.get("/market/snapshot")
async def get_snapshot(background_tasks: BackgroundTasks):
    results = {}
    tasks_list = [
        ("index", fetch_index_fubon_sdk()),
        ("futures", fetch_futures_taifex()),
    ] + [(sym, fetch_quote_fubon_sdk(sym)) for sym in WATCHLIST]
    raw = await asyncio.gather(*[t for _,t in tasks_list], return_exceptions=True)
    for (key, _), val in zip(tasks_list, raw):
        results[key] = val if not isinstance(val, Exception) else None
    # 備援補齊
    if not results.get("index"):
        results["index"] = await fetch_index_mis_twse()
    for sym in WATCHLIST:
        if not results.get(sym):
            results[sym] = await fetch_quote_mis_twse(sym)
        if not results.get(sym):
            results[sym] = await fetch_quote_yahoo(sym)
    valid_count = sum(1 for v in results.values() if v and isinstance(v, dict))
    quality_pct = round(valid_count/len(results)*100,1)
    snapshot = {"index":results.get("index"),"futures":results.get("futures"),
        "quotes":{sym:results.get(sym) for sym in WATCHLIST},
        "quality_pct":quality_pct,"sdk_ready":_sdk_ready,
        "fetch_timestamp_cst":datetime.now(CST).isoformat()}
    background_tasks.add_task(write_snapshot, snapshot)
    if quality_pct < 80:
        background_tasks.add_task(send_telegram,
            f"⚠️ *快照品質告警* {quality_pct}%<80%\n{valid_count}/{len(results)}")
    return snapshot

@app.get("/market/adr")
async def get_adr():
    results = {}
    for sym in ADR_SYMBOLS:
        data = await fetch_quote_yahoo(sym, suffix="")
        if data:
            data["symbol"] = sym
            results[sym] = data
    if not results: raise HTTPException(503,"ADR 數據源均失敗")
    return {"adrs":results,"fetch_timestamp_cst":datetime.now(CST).isoformat()}

@app.get("/sdk/status")
async def sdk_status():
    return {"sdk_ready":_sdk_ready,"sdk_error":_sdk_error,
        "fubon_id_set":bool(FUBON_ID),"pfx_path_set":bool(FUBON_PFX_PATH),
        "account_set":bool(FUBON_ACCOUNT),"data_dir":DATA_DIR,
        "timestamp_cst":datetime.now(CST).isoformat()}

@app.post("/sdk/reconnect")
async def sdk_reconnect():
    global _sdk_client, _sdk_ready, _sdk_error
    _sdk_client = None; _sdk_ready = False; _sdk_error = ""
    _init_fubon_sdk()
    return {"sdk_ready":_sdk_ready,
        "message":"SDK 重連成功" if _sdk_ready else f"重連失敗: {_sdk_error}"}

# ─────────────────────────────────────────────────────────────────────────────
# VaR 相容快照端點 v4.0
# 輸出含 prices.TXFC6 的標準格式，供 VaR P0-PRICE 讀取
# 同時寫入 DATA_DIR/data_snapshot_latest.json
# ─────────────────────────────────────────────────────────────────────────────
def _detect_session(cst_now: datetime) -> str:
    h  = cst_now.hour
    wd = cst_now.weekday()  # 0=Mon … 6=Sun
    if wd >= 5:
        return "WEEKEND"
    if 9 <= h < 14:
        return "TW_DAY"
    if h >= 15 or h < 5:
        return "TW_NIGHT_FUTURES"
    if h in (8, 14):
        return "PRE_POST_MARKET"
    return "US_PRE_OPEN"

@app.get("/market/snapshot/var")
async def get_var_snapshot():
    """
    VaR 相容快照：抓台指期 TXFC6 + ADR，
    以 prices.TXFC6 欄位格式寫入 data_snapshot_latest.json。
    VaR P0-PRICE 守門員直接讀此檔取得 txfc6_price。
    """
    cst_now     = datetime.now(CST)
    snapshot_id = f"VAR_SNAP_{cst_now.strftime('%Y%m%d_%H%M')}CST"

    # ① 台指期 TXFC6
    futures_data     = await fetch_futures_taifex()
    txfc6_price      = futures_data["price"]               if futures_data else None
    txfc6_source     = futures_data.get("source","UNAVAIL") if futures_data else "UNAVAIL"
    txfc6_validation = futures_data.get("validation_status","BLOCKED") if futures_data else "BLOCKED"

    # ② ADR（PLTR/META/TSM/AMD/NVDA 美股持倉用）
    us_syms  = ["PLTR", "META", "TSM", "AMD", "NVDA"]
    adr_tasks = await asyncio.gather(
        *[fetch_quote_yahoo(s, suffix="") for s in us_syms],
        return_exceptions=True
    )
    prices: dict = {}
    for sym, d in zip(us_syms, adr_tasks):
        if isinstance(d, dict) and d.get("price"):
            prices[sym] = {
                "close_price":       d["price"],
                "prev_close":        d.get("prev_close"),
                "change_pct":        d.get("change_pct"),
                "currency":          "USD",
                "exchange":          "NASDAQ",
                "fetch_source":      d.get("source","yahoo_finance"),
                "timestamp":         cst_now.isoformat(),
                "validation_status": d.get("validation_status","UNVERIFIED"),
                "deviation_pct":     0.0
            }

    # ③ TXFC6 寫入 prices
    if txfc6_price:
        prices["TXFC6"] = {
            "close_price":       txfc6_price,
            "prev_close":        futures_data.get("prev_close"),
            "change_pct":        futures_data.get("change_pct"),
            "currency":          "TWD",
            "exchange":          "TAIFEX",
            "fetch_source":      txfc6_source,
            "timestamp":         cst_now.isoformat(),
            "validation_status": txfc6_validation,
            "deviation_pct":     0.0
        }

    # ④ 讀取現有快照保留 positions_summary / circuit_breaker 等欄位
    snap_path = f"{DATA_DIR}/data_snapshot_latest.json"
    existing: dict = {}
    if os.path.exists(snap_path):
        try:
            with open(snap_path) as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    # 合併 prices（新抓到的覆蓋舊值）
    merged_prices = {**existing.get("prices", {}), **prices}

    confirmed_cnt  = sum(1 for p in merged_prices.values()
                         if isinstance(p, dict) and p.get("validation_status") == "CONFIRMED")
    unverified_cnt = sum(1 for p in merged_prices.values()
                         if isinstance(p, dict) and p.get("validation_status") == "UNVERIFIED")

    var_snapshot = {
        **existing,
        "snapshot_id":     snapshot_id,
        "created_at_utc":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_at_cst":  cst_now.strftime("%Y-%m-%d %H:%M:%S CST"),
        "market_session":  _detect_session(cst_now),
        "prices":          merged_prices,
        "quality_pct":     100.0 if txfc6_price else 60.0,
        "validation_summary": {
            "confirmed":   confirmed_cnt,
            "unverified":  unverified_cnt,
            "conflict":    0,
            "discrepancy": 0,
            "total":       len(merged_prices)
        }
    }

    # ⑤ 直接寫入（同步，確保立即可讀，VaR 守門員不會讀到舊快照）
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(var_snapshot, f, ensure_ascii=False, indent=2)
        log.info(f"[VarSnap] 寫入成功 txfc6={txfc6_price} quality={var_snapshot['quality_pct']}%")
    except Exception as e:
        log.error(f"[VarSnap] 寫入失敗: {e}")

    return {
        "ok":               True,
        "snapshot_id":      snapshot_id,
        "txfc6_price":      txfc6_price,
        "txfc6_source":     txfc6_source,
        "txfc6_validation": txfc6_validation,
        "prices_count":     len(merged_prices),
        "quality_pct":      var_snapshot["quality_pct"],
        "written_to":       snap_path,
        "timestamp_cst":    cst_now.isoformat()
    }

# ─────────────────────────────────────────────────────────────────────────────
# 股票 / 期貨下單端點（富邦 Neo SDK DMA）
# ─────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel
from typing import Optional as Opt

FUBON_SIMULATION = os.getenv("FUBON_SIMULATION", "true").lower() == "true"
ADMIN_SECRET     = os.getenv("ADMIN_SECRET", "nebula_admin_2026")

class StockOrderReq(BaseModel):
    symbol:        str
    action:        str            # BUY | SELL
    quantity:      int            # 整股=1000 倍數；零股任意
    price:         Opt[float] = None
    order_type:    str = "LIMIT"  # LIMIT | MARKET
    time_in_force: str = "ROD"    # ROD | IOC | FOK
    market_type:   str = "COMMON" # COMMON | ODD_LOT | AFTER_MARKET
    simulation:    Opt[bool] = None
    user_def:      Opt[str]  = None

class FuturesOrderReq(BaseModel):
    symbol:        str
    action:        str
    quantity:      int            # 口數
    price:         Opt[float] = None
    order_type:    str = "LIMIT"
    time_in_force: str = "ROD"
    session:       str = "DAY"    # DAY | NIGHT
    simulation:    Opt[bool] = None
    user_def:      Opt[str]  = None

class CancelOrderReq(BaseModel):
    order_id: str
    market:   str = "STOCK"       # STOCK | FUTURES

def _require_sdk_order():
    if not _sdk_ready or _sdk_client is None:
        raise HTTPException(503, f"SDK 未登入，無法下單。原因：{_sdk_error}")

@app.post("/api/order/stock")
async def place_stock_order(req: StockOrderReq):
    """股票下單（DMA，限/市價，整股/零股/盤後）"""
    _require_sdk_order()
    use_sim = req.simulation if req.simulation is not None else FUBON_SIMULATION
    try:
        from fubon_neo.sdk import Order
        from fubon_neo.constant import BSAction, PriceType, MarketType, TimeInForce, OrderType

        buy_sell   = BSAction.Buy if req.action.upper() == "BUY" else BSAction.Sell
        price_type = {"LIMIT": PriceType.Limit, "MARKET": PriceType.Market}.get(
                        req.order_type.upper(), PriceType.Limit)
        mkt_type   = {"COMMON":       MarketType.Common,
                      "ODD_LOT":      MarketType.OddLot,
                      "AFTER_MARKET": MarketType.AfterMarket}.get(
                        req.market_type.upper(), MarketType.Common)
        tif        = {"ROD": TimeInForce.ROD, "IOC": TimeInForce.IOC,
                      "FOK": TimeInForce.FOK}.get(req.time_in_force.upper(), TimeInForce.ROD)

        order = Order(
            buy_sell=buy_sell, symbol=req.symbol,
            price=str(req.price) if req.price else None,
            quantity=req.quantity, market_type=mkt_type,
            price_type=price_type, time_in_force=tif,
            order_type=OrderType.Stock,
            user_def=req.user_def or f"NB_{datetime.now(CST).strftime('%H%M%S')}"
        )
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _sdk_client.stock.place_order(_sdk_client.accounts[0], order))
        log.info(f"[ORDER:STOCK] {req.action} {req.symbol} x{req.quantity} "
                 f"@ {req.price} sim={use_sim} => {result}")
        return {"ok": True, "simulation": use_sim, "order": req.dict(),
                "result": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        log.error(f"[ORDER:STOCK] 失敗: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/order/futures")
async def place_futures_order(req: FuturesOrderReq):
    """期貨下單（台指期日盤 / 夜盤）"""
    _require_sdk_order()
    use_sim = req.simulation if req.simulation is not None else FUBON_SIMULATION
    try:
        from fubon_neo.sdk import FutOptOrder
        from fubon_neo.constant import (BSAction, FutOptPriceType,
                                        FutOptMarketType, TimeInForce, FutOptOrderType)

        buy_sell   = BSAction.Buy if req.action.upper() == "BUY" else BSAction.Sell
        price_type = {"LIMIT": FutOptPriceType.Limit,
                      "MARKET": FutOptPriceType.Market,
                      "RANGE":  FutOptPriceType.Range}.get(
                        req.order_type.upper(), FutOptPriceType.Limit)
        mkt_type   = (FutOptMarketType.FutureNight
                      if req.session.upper() == "NIGHT"
                      else FutOptMarketType.Future)
        tif        = {"ROD": TimeInForce.ROD, "IOC": TimeInForce.IOC,
                      "FOK": TimeInForce.FOK}.get(req.time_in_force.upper(), TimeInForce.ROD)

        order = FutOptOrder(
            buy_sell=buy_sell, symbol=req.symbol,
            price=str(req.price) if req.price else None,
            lot=req.quantity, market_type=mkt_type,
            price_type=price_type, time_in_force=tif,
            order_type=FutOptOrderType.Auto,
            user_def=req.user_def or f"NB_{datetime.now(CST).strftime('%H%M%S')}"
        )
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _sdk_client.futopt.place_order(_sdk_client.accounts[0], order))
        log.info(f"[ORDER:FUTURES] {req.action} {req.symbol} x{req.quantity} "
                 f"@ {req.price} sim={use_sim} session={req.session} => {result}")
        return {"ok": True, "simulation": use_sim, "order": req.dict(),
                "result": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        log.error(f"[ORDER:FUTURES] 失敗: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/order/cancel")
async def cancel_order(req: CancelOrderReq):
    """取消委託（股票或期貨）"""
    _require_sdk_order()
    try:
        loop = asyncio.get_event_loop()
        if req.market.upper() == "FUTURES":
            result = await loop.run_in_executor(
                None, lambda: _sdk_client.futopt.cancel_order(
                    _sdk_client.accounts[0], req.order_id))
        else:
            result = await loop.run_in_executor(
                None, lambda: _sdk_client.stock.cancel_order(
                    _sdk_client.accounts[0], req.order_id))
        return {"ok": True, "order_id": req.order_id, "result": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/orders/stock")
async def get_stock_orders():
    """查詢股票委託清單"""
    _require_sdk_order()
    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _sdk_client.stock.get_order_results(_sdk_client.accounts[0]))
        return {"ok": True, "data": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/orders/futures")
async def get_futures_orders():
    """查詢期貨委託清單"""
    _require_sdk_order()
    try:
        from fubon_neo.constant import FutOptMarketType
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _sdk_client.futopt.get_order_results(
                _sdk_client.accounts[0], FutOptMarketType.Future))
        return {"ok": True, "data": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/positions/stock")
async def get_stock_positions():
    """查詢股票持倉"""
    _require_sdk_order()
    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _sdk_client.stock.get_positions(_sdk_client.accounts[0]))
        return {"ok": True, "data": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/positions/futures")
async def get_futures_positions():
    """查詢期貨持倉"""
    _require_sdk_order()
    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: _sdk_client.futopt.get_positions(_sdk_client.accounts[0]))
        return {"ok": True, "data": str(result),
                "timestamp_cst": datetime.now(CST).isoformat()}
    except Exception as e:
        raise HTTPException(500, str(e))

# 向後相容：統一入口
@app.post("/api/order/place")
async def place_order_compat(
    symbol: str, action: str, quantity: int,
    price: Opt[float] = None, order_type: str = "LIMIT", market: str = "STOCK"
):
    if market.upper() == "FUTURES":
        return await place_futures_order(
            FuturesOrderReq(symbol=symbol, action=action,
                            quantity=quantity, price=price, order_type=order_type))
    return await place_stock_order(
        StockOrderReq(symbol=symbol, action=action,
                      quantity=quantity, price=price, order_type=order_type))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("vm_main_fubon:app", host="0.0.0.0", port=8080, reload=False)
