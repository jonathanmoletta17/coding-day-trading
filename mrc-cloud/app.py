from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

SYMBOLS = tuple(x.strip().upper() for x in os.getenv("MRC_SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if x.strip())
MARKETS = {
    "BTCUSDT": {"inst": "BTC-USDT-SWAP", "ccy": "BTC"},
    "ETHUSDT": {"inst": "ETH-USDT-SWAP", "ccy": "ETH"},
}
POLL = max(5, int(os.getenv("MRC_POLL_SECONDS", "15")))
START_EQ = float(os.getenv("MRC_PAPER_EQUITY", "10000"))
RISK_PCT = min(max(float(os.getenv("MRC_RISK_PCT", "0.0025")), 0.0), 0.005)
COST = max(float(os.getenv("MRC_ROUNDTRIP_COST", "0.0006")), 0.0)
TOKEN = os.getenv("MRC_DASHBOARD_TOKEN", "").strip()
DB = os.getenv("MRC_DB_PATH", "/data/mrc_cloud.sqlite3")
if not Path(DB).parent.exists():
    DB = "/tmp/mrc_cloud.sqlite3"

BASE = "https://www.okx.com"
HOUR = 3_600_000
FIFTEEN = 900_000
FIVE = 300_000
SOURCE = "OKX public REST / perpetual swaps"
STRATEGY = "OF-BOUNDARY-OKX-causal-v3"


def iso(ms: int | float | None = None) -> str:
    if ms is None:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc).isoformat()


def f(x: Any, default: float = 0.0) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


@dataclass
class Plan:
    symbol: str
    signal_id: str
    event_id: str
    side: str
    decision: str
    confidence: int
    score: float
    entry: float
    stop: float
    target: float
    risk_usdt: float
    qty: float
    rr: float
    chase_r: float
    reason: str
    created_at: str


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript(
            '''
            CREATE TABLE IF NOT EXISTS events(
                event_id TEXT PRIMARY KEY,
                symbol TEXT,
                kind TEXT,
                side TEXT,
                payload TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS signals(
                signal_id TEXT PRIMARY KEY,
                event_id TEXT,
                symbol TEXT,
                side TEXT,
                decision TEXT,
                score REAL,
                confidence INTEGER,
                entry REAL,
                stop REAL,
                target REAL,
                risk_usdt REAL,
                qty REAL,
                payload TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS trades(
                trade_id TEXT PRIMARY KEY,
                signal_id TEXT,
                symbol TEXT,
                side TEXT,
                entry REAL,
                stop REAL,
                target REAL,
                qty REAL,
                risk_usdt REAL,
                opened_at TEXT,
                closed_at TEXT,
                exit REAL,
                outcome TEXT,
                pnl_usdt REAL,
                r_net REAL
            );
            '''
        )
        self.c.commit()

    def event(self, e: dict[str, Any]) -> bool:
        fresh = not self.c.execute("SELECT 1 FROM events WHERE event_id=?", (e["event_id"],)).fetchone()
        self.c.execute(
            "INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)",
            (e["event_id"], e["symbol"], e["kind"], e.get("side", ""), json.dumps(e), iso()),
        )
        self.c.commit()
        return fresh

    def signal(self, p: Plan) -> bool:
        if self.c.execute("SELECT 1 FROM signals WHERE signal_id=?", (p.signal_id,)).fetchone():
            return False
        self.c.execute(
            "INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                p.signal_id,
                p.event_id,
                p.symbol,
                p.side,
                p.decision,
                p.score,
                p.confidence,
                p.entry,
                p.stop,
                p.target,
                p.risk_usdt,
                p.qty,
                json.dumps({**asdict(p), "source": SOURCE, "strategy": STRATEGY}),
                p.created_at,
            ),
        )
        self.c.commit()
        return True

    def openpos(self, symbol: str) -> dict[str, Any] | None:
        row = self.c.execute(
            "SELECT * FROM trades WHERE symbol=? AND outcome='OPEN' ORDER BY opened_at DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return dict(row) if row else None

    def open(self, p: Plan) -> None:
        if self.openpos(p.symbol):
            return
        tid = "paper_" + p.signal_id
        self.c.execute(
            '''
            INSERT OR IGNORE INTO trades(
                trade_id,signal_id,symbol,side,entry,stop,target,qty,risk_usdt,
                opened_at,outcome,pnl_usdt,r_net
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0)
            ''',
            (
                tid,
                p.signal_id,
                p.symbol,
                p.side,
                p.entry,
                p.stop,
                p.target,
                p.qty,
                p.risk_usdt,
                iso(),
                "OPEN",
            ),
        )
        self.c.commit()

    def close(self, tid: str, px: float, outcome: str) -> None:
        row = self.c.execute("SELECT * FROM trades WHERE trade_id=?", (tid,)).fetchone()
        if not row or row["outcome"] != "OPEN":
            return
        d = dict(row)
        sign = 1 if d["side"] == "LONG" else -1
        gross = (px - d["entry"]) * sign * d["qty"]
        fees = (d["entry"] + px) * d["qty"] * (COST / 2)
        pnl = gross - fees
        r_net = pnl / d["risk_usdt"] if d["risk_usdt"] else 0
        self.c.execute(
            "UPDATE trades SET closed_at=?,exit=?,outcome=?,pnl_usdt=?,r_net=? WHERE trade_id=?",
            (iso(), px, outcome, pnl, r_net, tid),
        )
        self.c.commit()

    def eq(self) -> float:
        row = self.c.execute(
            "SELECT COALESCE(SUM(pnl_usdt),0) z FROM trades WHERE outcome!='OPEN'"
        ).fetchone()
        return START_EQ + float(row["z"] or 0)

    def recent(self, table: str, n: int = 20) -> list[dict[str, Any]]:
        order = "created_at" if table in ("events", "signals") else "COALESCE(closed_at,opened_at)"
        return [
            dict(x)
            for x in self.c.execute(
                f"SELECT * FROM {table} ORDER BY {order} DESC LIMIT ?", (n,)
            ).fetchall()
        ]

    def metrics(self) -> dict[str, Any]:
        rows = [dict(x) for x in self.c.execute("SELECT * FROM trades WHERE outcome!='OPEN'").fetchall()]
        vals = [f(x["r_net"]) for x in rows]
        n = len(vals)
        pos = sum(x for x in vals if x > 0)
        neg = -sum(x for x in vals if x < 0)
        return {
            "closed_trades": n,
            "paper_equity": round(self.eq(), 2),
            "net_pnl_usdt": round(self.eq() - START_EQ, 2),
            "expectancy_r": round(sum(vals) / n, 4) if n else 0,
            "win_rate": round(sum(x > 0 for x in vals) / n, 4) if n else 0,
            "profit_factor": round(pos / neg, 3) if neg else None,
        }


store = Store(DB)
STATE: dict[str, Any] = {
    "started_at": iso(),
    "heartbeat": 0.0,
    "symbols": {},
    "last_error": None,
    "mode": "PAPER",
    "strategy": STRATEGY,
    "source": SOURCE,
    "feed_ready": False,
}
LOCK = asyncio.Lock()


class OKX:
    def __init__(self):
        self.h = httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "MRC-Cloud/3.0", "Accept": "application/json"},
        )

    async def g(self, path: str, **q: Any) -> list[Any]:
        r = await self.h.get(BASE + path, params=q)
        r.raise_for_status()
        payload = r.json()
        if str(payload.get("code", "")) != "0":
            raise RuntimeError(f"OKX {path} code={payload.get('code')} msg={payload.get('msg')}")
        return payload.get("data") or []

    async def snap(self, symbol: str) -> dict[str, Any]:
        m = MARKETS.get(symbol)
        if not m:
            raise ValueError(f"unsupported symbol {symbol}")
        inst = m["inst"]
        ccy = m["ccy"]
        candles, ticker, taker, oi, ls, funding = await asyncio.gather(
            self.g("/api/v5/market/candles", instId=inst, bar="15m", limit=20),
            self.g("/api/v5/market/ticker", instId=inst),
            self.g("/api/v5/rubik/stat/taker-volume", ccy=ccy, instType="CONTRACTS", period="5m"),
            self.g("/api/v5/rubik/stat/contracts/open-interest-volume", ccy=ccy, period="5m"),
            self.g("/api/v5/rubik/stat/contracts/long-short-account-ratio", ccy=ccy, period="5m"),
            self.g("/api/v5/public/funding-rate", instId=inst),
        )
        if not ticker:
            raise RuntimeError(f"OKX ticker empty for {inst}")
        return {
            "k": candles,
            "b": ticker[0],
            "t": taker,
            "o": oi,
            "l": ls,
            "p": funding[0] if funding else {},
            "inst": inst,
            "ccy": ccy,
        }

    async def close(self):
        await self.h.aclose()


def bar(x: list[Any]) -> dict[str, Any]:
    ot = int(x[0])
    return {
        "ot": ot,
        "o": f(x[1]),
        "h": f(x[2]),
        "l": f(x[3]),
        "c": f(x[4]),
        "ct": ot + FIFTEEN - 1,
        "confirmed": str(x[8]) == "1",
    }


def detect_event(symbol: str, raw: dict[str, Any], now: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    bars = sorted(
        [bar(x) for x in raw["k"] if len(x) >= 9 and str(x[8]) == "1"],
        key=lambda z: z["ot"],
    )
    bars = [x for x in bars if x["ct"] <= now]
    current_hour = (now // HOUR) * HOUR
    previous_hour = current_hour - HOUR
    prev = [x for x in bars if previous_hour <= x["ot"] < current_hour]
    cur = [x for x in bars if current_hour <= x["ot"] < current_hour + HOUR]
    ctx = {
        "current_hour": iso(current_hour),
        "previous_hour": iso(previous_hour),
        "closed_current_bars": len(cur),
        "source": raw["inst"],
    }
    if len(prev) != 4:
        return None, {**ctx, "status": "WARMING", "reason": f"need 4 prior-hour bars, got {len(prev)}"}
    hi = max(x["h"] for x in prev)
    lo = min(x["l"] for x in prev)
    R = hi - lo
    ctx |= {"prev_high": hi, "prev_low": lo, "range_r": R}
    if R <= 0:
        return None, {**ctx, "status": "INVALID_RANGE"}
    for x in cur:
        up = x["h"] > hi
        dn = x["l"] < lo
        if not (up or dn):
            continue
        eid = f"{symbol}:{current_hour}:okx"
        if up and dn:
            return (
                {
                    "event_id": eid,
                    "symbol": symbol,
                    "kind": "AMBIGUOUS",
                    "side": "",
                    "R": R,
                    "signal_ms": x["ct"],
                    "bar": x,
                    "prev_high": hi,
                    "prev_low": lo,
                    "source": raw["inst"],
                },
                {**ctx, "status": "AMBIGUOUS"},
            )
        if up:
            kind = "ACCEPTANCE" if x["c"] > hi else "REJECTION"
            side = "LONG"
            boundary = hi
        else:
            kind = "ACCEPTANCE" if x["c"] < lo else "REJECTION"
            side = "SHORT"
            boundary = lo
        event = {
            "event_id": eid,
            "symbol": symbol,
            "kind": kind,
            "side": side,
            "R": R,
            "boundary": boundary,
            "signal_ms": x["ct"],
            "bar": x,
            "prev_high": hi,
            "prev_low": lo,
            "source": raw["inst"],
        }
        return event, {**ctx, "status": kind, "side": side, "signal_at": iso(x["ct"])}
    return None, {**ctx, "status": "WAIT_BOUNDARY_TEST"}


def completed_rows(rows: list[Any], cutoff_ms: int | None) -> list[list[Any]]:
    cutoff = int(cutoff_ms or time.time() * 1000)
    out: list[list[Any]] = []
    for row in rows or []:
        try:
            ts = int(row[0])
            if ts + FIVE <= cutoff:
                out.append(row)
        except Exception:
            continue
    return sorted(out, key=lambda r: int(r[0]))


def flow(raw: dict[str, Any], side: str | None = None, cutoff_ms: int | None = None) -> dict[str, float | int | None | str]:
    direction = 1 if side == "LONG" else -1 if side == "SHORT" else 0
    taker = completed_rows(raw.get("t") or [], cutoff_ms)
    oi = completed_rows(raw.get("o") or [], cutoff_ms)
    ls = completed_rows(raw.get("l") or [], cutoff_ms)

    buy = f(taker[-1][1]) if taker else 0.0
    sell = f(taker[-1][2]) if taker else 0.0
    ratio = buy / sell if sell > 0 else (1.0 if buy == 0 else 999.0)
    taker_log = math.log(max(ratio, 1e-9))

    oi_now = f(oi[-1][1]) if oi else 0.0
    oi_prev = f(oi[-2][1]) if len(oi) > 1 else oi_now
    doi = oi_now / oi_prev - 1 if oi_prev else 0.0

    ls_now = f(ls[-1][1], 1.0) if ls else 1.0
    ls_prev = f(ls[-2][1], ls_now) if len(ls) > 1 else ls_now
    dls = ls_now / ls_prev - 1 if ls_prev else 0.0

    funding = f((raw.get("p") or {}).get("fundingRate"))
    latest_ts = max([int(x[-1][0]) for x in (taker, oi, ls) if x], default=0)
    return {
        "taker_ratio": ratio,
        "buy_volume": buy,
        "sell_volume": sell,
        "taker_log": taker_log,
        "aligned_taker_log": taker_log * direction if direction else 0.0,
        "oi": oi_now,
        "doi": doi,
        "long_short_ratio": ls_now,
        "dls": dls,
        "aligned_dls": dls * direction if direction else 0.0,
        "funding": funding,
        "aligned_funding": funding * direction if direction else 0.0,
        "flow_bucket_ts": latest_ts or None,
        "flow_bucket_time": iso(latest_ts) if latest_ts else None,
        "causal_cutoff_ms": cutoff_ms,
    }


def plan(e: dict[str, Any], raw: dict[str, Any], eq: float, now: int) -> Plan:
    side = e["side"]
    fl = flow(raw, side, e["signal_ms"])
    score = 0.75
    why = ["acceptance close outside previous UTC-hour boundary"]

    if fl["aligned_taker_log"] > math.log(1.10):
        score += 1.0
        why.append("completed 5m taker flow strongly aligned")
    elif fl["aligned_taker_log"] > 0:
        score += 0.4
        why.append("completed 5m taker flow mildly aligned")
    else:
        score -= 0.5
        why.append("completed 5m taker flow opposed")

    if fl["doi"] > 0:
        score += 0.75
        why.append("open interest expanding")
    else:
        score -= 0.25
        why.append("open interest not expanding")

    if fl["aligned_dls"] > 0:
        score += 0.4
        why.append("long/short ratio change aligned")
    elif fl["aligned_dls"] < 0:
        score -= 0.2
        why.append("long/short ratio change opposed")

    bid = f(raw["b"].get("bidPx"))
    ask = f(raw["b"].get("askPx"))
    entry = ask if side == "LONG" else bid
    R = e["R"]
    boundary = e["boundary"]
    chase = (entry - boundary) / R if side == "LONG" else (boundary - entry) / R
    age_min = (now - e["signal_ms"]) / 60000

    decision = side if score >= 1.75 and chase <= 0.20 and age_min <= 20 else "NO_TRADE"
    if chase > 0.20:
        why.append("entry too extended from boundary")
    if age_min > 20:
        why.append("stale event")
    if score < 1.75:
        why.append("order-flow score below threshold")

    stop = boundary - 0.25 * R if side == "LONG" else boundary + 0.25 * R
    risk = eq * RISK_PCT
    per_unit = abs(entry - stop)
    qty = min(risk / per_unit if per_unit else 0, eq / entry if entry else 0)
    target = entry + 1.5 * per_unit if side == "LONG" else entry - 1.5 * per_unit
    signal_id = hashlib.sha256(
        (e["event_id"] + str(e["signal_ms"]) + ":okx-causal-v3").encode()
    ).hexdigest()[:24]
    confidence = max(1, min(99, int(50 + 15 * (score - 1.5))))
    why.append(
        f"TI={fl['taker_ratio']:.3f} dOI={fl['doi']*100:.3f}% "
        f"dLS={fl['dls']*100:.3f}%"
    )
    return Plan(
        e["symbol"],
        signal_id,
        e["event_id"],
        side,
        decision,
        confidence,
        round(score, 3),
        entry,
        stop,
        target,
        risk,
        qty,
        1.5,
        chase,
        "; ".join(why),
        iso(),
    )


def manage(symbol: str, raw: dict[str, Any]) -> None:
    p = store.openpos(symbol)
    if not p:
        return
    bid = f(raw["b"].get("bidPx"))
    ask = f(raw["b"].get("askPx"))
    if p["side"] == "LONG":
        if bid <= p["stop"]:
            store.close(p["trade_id"], bid, "STOP")
        elif bid >= p["target"]:
            store.close(p["trade_id"], bid, "TARGET")
    else:
        if ask >= p["stop"]:
            store.close(p["trade_id"], ask, "STOP")
        elif ask <= p["target"]:
            store.close(p["trade_id"], ask, "TARGET")


def state_valid(v: dict[str, Any]) -> bool:
    if not v or v.get("error"):
        return False
    b = v.get("book") or {}
    c = v.get("context") or {}
    return (
        f(b.get("bid")) > 0
        and f(b.get("ask")) > 0
        and f(c.get("prev_high")) > 0
        and f(c.get("prev_low")) > 0
        and c.get("status") not in (None, "DATA_ERROR", "WARMING")
    )


async def loop():
    client = OKX()
    try:
        while True:
            now = int(time.time() * 1000)
            errors: list[str] = []
            for symbol in SYMBOLS:
                try:
                    raw = await client.snap(symbol)
                    manage(symbol, raw)
                    e, ctx = detect_event(symbol, raw, now)
                    display_flow = flow(
                        raw,
                        e["side"] if e and e.get("side") else None,
                        e["signal_ms"] if e else now,
                    )
                    pd = None
                    if e:
                        store.event(e)
                        if e["kind"] == "ACCEPTANCE":
                            p = plan(e, raw, store.eq(), now)
                            pd = asdict(p)
                            if store.signal(p) and p.decision in ("LONG", "SHORT"):
                                store.open(p)
                        elif e["kind"] == "REJECTION":
                            pd = {
                                "decision": "NO_TRADE",
                                "reason": "rejection recorded for research",
                            }
                    symbol_state = {
                        "source": raw["inst"],
                        "context": ctx,
                        "event": e,
                        "plan": pd,
                        "flow": display_flow,
                        "book": {
                            "bid": f(raw["b"].get("bidPx")),
                            "ask": f(raw["b"].get("askPx")),
                            "last": f(raw["b"].get("last")),
                            "ts": int(raw["b"].get("ts") or 0),
                        },
                        "position": store.openpos(symbol),
                        "error": None,
                        "updated_at": iso(),
                    }
                    async with LOCK:
                        STATE["symbols"][symbol] = symbol_state
                except Exception as ex:
                    msg = f"{type(ex).__name__}: {ex}"
                    errors.append(f"{symbol}: {msg}")
                    print(f"poll_error {symbol}: {msg}", flush=True)
                    async with LOCK:
                        STATE["symbols"][symbol] = {
                            "source": MARKETS.get(symbol, {}).get("inst", symbol),
                            "context": {"status": "DATA_ERROR"},
                            "event": None,
                            "plan": None,
                            "flow": {},
                            "book": {},
                            "position": store.openpos(symbol),
                            "error": msg,
                            "updated_at": iso(),
                        }
            async with LOCK:
                STATE["heartbeat"] = time.time()
                STATE["metrics"] = store.metrics()
                STATE["last_error"] = " | ".join(errors) if errors else None
                STATE["feed_ready"] = all(
                    symbol in STATE["symbols"] and state_valid(STATE["symbols"][symbol])
                    for symbol in SYMBOLS
                )
            await asyncio.sleep(POLL)
    finally:
        await client.close()


TASK = None


@asynccontextmanager
async def life(app):
    global TASK
    TASK = asyncio.create_task(loop())
    yield
    TASK.cancel()


app = FastAPI(title="MRC Cloud Cockpit", version="3.0", lifespan=life)


@app.middleware("http")
async def auth(req: Request, call_next):
    if not TOKEN or req.url.path in ("/healthz", "/readyz"):
        return await call_next(req)
    h = req.headers.get("authorization", "")
    ok = False
    if h.startswith("Basic "):
        try:
            u, p = base64.b64decode(h[6:]).decode().split(":", 1)
            ok = u == "mrc" and p == TOKEN
        except Exception:
            pass
    if not ok:
        return PlainTextResponse(
            "Authentication required",
            401,
            headers={"WWW-Authenticate": "Basic realm=MRC"},
        )
    return await call_next(req)


@app.get("/healthz")
async def health():
    age = time.time() - STATE.get("heartbeat", 0)
    live = TASK is not None and not TASK.done() and age < max(90, POLL * 4)
    return JSONResponse(
        {
            "ok": live,
            "feed_ready": STATE.get("feed_ready", False),
            "heartbeat_age_s": round(age, 1),
            "source": SOURCE,
            "last_error": STATE.get("last_error"),
        },
        status_code=200 if live else 503,
    )


@app.get("/readyz")
async def ready():
    async with LOCK:
        symbols = json.loads(json.dumps(STATE.get("symbols", {}), default=str))
        hb = STATE.get("heartbeat", 0)
    checks = {s: state_valid(symbols.get(s, {})) for s in SYMBOLS}
    ready_state = bool(hb) and all(checks.values())
    return JSONResponse(
        {
            "ready": ready_state,
            "source": SOURCE,
            "checks": checks,
            "symbols": list(SYMBOLS),
            "last_error": STATE.get("last_error"),
        },
        status_code=200 if ready_state else 503,
    )


@app.get("/api/state")
async def state():
    async with LOCK:
        x = json.loads(json.dumps(STATE, default=str))
    x["recent_signals"] = store.recent("signals")
    x["recent_trades"] = store.recent("trades")
    x["recent_events"] = store.recent("events")
    x["metrics"] = store.metrics()
    return x


HTML = '''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MRC Cloud Cockpit</title>
<style>
:root{color-scheme:dark}
body{margin:0;background:#071019;color:#eaf2f8;font:14px system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:22px;border-bottom:1px solid #203347;background:#09131d;position:sticky;top:0;z-index:2}
.wrap{max-width:1400px;margin:auto;padding:22px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}
.metrics{grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}
.card{background:#0e1a26;border:1px solid #203347;border-radius:14px;padding:16px}
.big{font-size:28px;font-weight:800;margin-top:5px}
.row{display:flex;justify-content:space-between;gap:16px;margin:7px 0}
.muted{color:#86a1b8}
.long{color:#37d67a}.short{color:#ff5d73}.warn{color:#ffc857}.ok{color:#37d67a}.bad{color:#ff5d73}
.banner{padding:12px 14px;border-radius:10px;margin-bottom:14px;background:#26151a;border:1px solid #6d2b38;color:#ffb9c3;display:none}
.badge{font-size:11px;padding:4px 8px;border:1px solid #294158;border-radius:999px;color:#9fc7e7}
hr{border:0;border-top:1px solid #203347;margin:12px 0}
table{width:100%;border-collapse:collapse;background:#0e1a26;border-radius:12px;overflow:hidden}
td,th{padding:9px;border-bottom:1px solid #203347;text-align:left;font-size:12px}
h3{margin-top:22px}
</style>
</head>
<body>
<header>
  <div style="display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap">
    <div><b style="font-size:22px">MRC Cloud Cockpit</b><div class="muted">OKX public perpetual data • PAPER ONLY</div></div>
    <div id="status" class="badge">starting…</div>
  </div>
</header>
<main class="wrap">
  <div id="banner" class="banner"></div>
  <div id="m" class="grid metrics"></div>
  <h3>Live decisions</h3>
  <div id="s" class="grid"></div>
  <h3>Paper trades</h3>
  <div id="t"></div>
</main>
<script>
const finite=x=>Number.isFinite(Number(x));
const n=(x,d=2)=>finite(x)?Number(x).toLocaleString('en-US',{maximumFractionDigits:d}):'—';
const pct=(x,d=3)=>finite(x)?`${n(Number(x)*100,d)}%`:'—';

async function go(){
  try{
    const r=await fetch('/api/state',{cache:'no-store'});
    if(!r.ok) throw new Error(`state HTTP ${r.status}`);
    const x=await r.json(),m=x.metrics||{};
    const status=document.querySelector('#status');
    status.textContent=x.feed_ready?'FEED READY':'FEED NOT READY';
    status.className='badge '+(x.feed_ready?'ok':'bad');

    const banner=document.querySelector('#banner');
    if(x.last_error){
      banner.style.display='block';
      banner.textContent='Market-data error: '+x.last_error;
    }else banner.style.display='none';

    document.querySelector('#m').innerHTML=`
      <div class=card><span class=muted>Paper equity</span><div class=big>$${n(m.paper_equity)}</div></div>
      <div class=card><span class=muted>Closed trades</span><div class=big>${m.closed_trades||0}</div></div>
      <div class=card><span class=muted>Expectancy</span><div class=big>${n(m.expectancy_r,3)}R</div></div>
      <div class=card><span class=muted>Feed</span><div class=big style="font-size:20px">${x.feed_ready?'READY':'WAIT'}</div><div class=muted>${x.source||'—'}</div></div>`;

    let h='';
    for(const [k,v] of Object.entries(x.symbols||{})){
      const c=v.context||{},p=v.plan||{},q=v.flow||{},b=v.book||{};
      const err=v.error;
      const d=err?'DATA_ERROR':(p.decision||c.status||'WAIT');
      const cls=d==='LONG'?'long':d==='SHORT'?'short':err?'bad':'warn';
      const mid=finite(b.bid)&&finite(b.ask)?(Number(b.bid)+Number(b.ask))/2:null;
      h+=`<div class=card>
        <div class=row><b>${k}</b><b class=${cls}>${d}</b></div>
        <div class=big>${n(mid)}</div>
        <div class=row><span class=muted>Source</span><span>${v.source||'—'}</span></div>
        ${err?`<div class=bad style="margin:10px 0">${err}</div>`:''}
        <div class=row><span>Event</span><span>${c.status||'—'}</span></div>
        <div class=row><span>Prev-hour range</span><span>${n(c.prev_low)} → ${n(c.prev_high)}</span></div>
        <div class=row><span>Score</span><span>${n(p.score,2)} / ${finite(p.confidence)?n(p.confidence,0)+'%':'—'}</span></div>
        <div class=row><span>Taker B/S</span><span>${n(q.taker_ratio,3)}</span></div>
        <div class=row><span>ΔOI 5m</span><span>${pct(q.doi,3)}</span></div>
        <div class=row><span>Long/Short</span><span>${n(q.long_short_ratio,3)}</span></div>
        <div class=row><span>Funding</span><span>${pct(q.funding,4)}</span></div>
        <div class=row><span class=muted>Flow bucket</span><span>${q.flow_bucket_time?new Date(q.flow_bucket_time).toLocaleTimeString(): '—'}</span></div>
        ${finite(p.entry)?`<hr>
          <div class=row><span>Entry</span><b>${n(p.entry)}</b></div>
          <div class=row><span>Stop</span><b>${n(p.stop)}</b></div>
          <div class=row><span>Target</span><b>${n(p.target)}</b></div>
          <div class=row><span>Risk</span><b>$${n(p.risk_usdt)}</b></div>
          <div class=muted>${p.reason||''}</div>`:''}
      </div>`;
    }
    document.querySelector('#s').innerHTML=h||'<div class=muted>Waiting for first market snapshot…</div>';

    const a=x.recent_trades||[];
    document.querySelector('#t').innerHTML=a.length?
      '<table><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Outcome</th><th>P&L</th><th>R</th></tr>'+ 
      a.map(z=>`<tr><td>${z.closed_at||z.opened_at||'—'}</td><td>${z.symbol}</td><td>${z.side}</td><td>${z.outcome}</td><td>$${n(z.pnl_usdt)}</td><td>${n(z.r_net,3)}</td></tr>`).join('')+
      '</table>':'<div class=muted>No paper trades yet.</div>';
  }catch(e){
    const banner=document.querySelector('#banner');
    banner.style.display='block';
    banner.textContent='Dashboard error: '+e.message;
    document.querySelector('#status').textContent='ERROR';
    document.querySelector('#status').className='badge bad';
  }
}
go();
setInterval(go,10000);
</script>
</body>
</html>'''


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML
