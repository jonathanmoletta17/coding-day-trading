from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

BASE = "https://www.okx.com"
DB_PATH = os.getenv("MRC_DB_PATH", "/data/mrc_cloud.sqlite3")
if not Path(DB_PATH).parent.exists():
    DB_PATH = "/tmp/mrc_cloud.sqlite3"
CACHE_DIR = Path(os.getenv("MRC_RESEARCH_CACHE", "/data/research_cache"))
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    CACHE_DIR = Path("/tmp/research_cache")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

MAP = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP"}
M15 = 15 * 60 * 1000
H1 = 60 * 60 * 1000
START_EQ = float(os.getenv("MRC_PAPER_EQUITY", "10000"))
RISK_PCT = min(float(os.getenv("MRC_RISK_PCT", "0.0025")), 0.005)
COST = float(os.getenv("MRC_ROUNDTRIP_COST", "0.0006"))
DAILY_LOCK_USD = START_EQ * 0.01
STOP_ATR = 1.5
TARGET_R = 2.0
MAX_CHASE = 0.5
MAX_HOLD_BARS = 96
STRATEGY = "TREND_BREAKOUT_V1"
DEFAULT_START = os.getenv("MRC_RESEARCH_START", "2026-05-13T00:00:00+00:00")
DEFAULT_END = os.getenv("MRC_RESEARCH_END", "2026-09-15T00:00:00+00:00")


def iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def parse_dt(s: str) -> datetime:
    x = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if x.tzinfo is None:
        x = x.replace(tzinfo=timezone.utc)
    return x.astimezone(timezone.utc)


def f(x: Any, default: float = 0.0) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


def ema(xs: list[float], n: int) -> float:
    a = 2 / (n + 1)
    z = xs[0]
    for x in xs[1:]:
        z = a * x + (1 - a) * z
    return z


def atr(bs: list[dict[str, float]], n: int = 14) -> float:
    tr = [
        max(bs[i]["h"] - bs[i]["l"], abs(bs[i]["h"] - bs[i - 1]["c"]), abs(bs[i]["l"] - bs[i - 1]["c"]))
        for i in range(1, len(bs))
    ]
    if not tr:
        return 0.0
    z = sum(tr[:n]) / min(n, len(tr))
    for x in tr[n:]:
        z = ((n - 1) * z + x) / n
    return z


def month_key(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def day_key(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


@dataclass
class Candidate:
    symbol: str
    priority: int
    signal_t: int
    entry_t: int
    side: str
    entry: float
    stop: float
    target: float
    atr: float
    exit_t: int
    exit_px: float
    outcome: str
    chase_atr: float


class ResearchDB:
    def __init__(self, path: str):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.execute("""CREATE TABLE IF NOT EXISTS research_runs(run_id TEXT PRIMARY KEY,strategy TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,status TEXT NOT NULL,result_json TEXT,error TEXT,created_at TEXT NOT NULL,finished_at TEXT)""")
        self.c.commit()

    def start(self, run_id: str, start: str, end: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.c.execute("INSERT OR REPLACE INTO research_runs VALUES(?,?,?,?,?,?,?,?,?)", (run_id, STRATEGY, start, end, "RUNNING", None, None, now, None))
        self.c.commit()

    def finish(self, run_id: str, result: dict[str, Any]) -> None:
        self.c.execute("UPDATE research_runs SET status='DONE',result_json=?,finished_at=? WHERE run_id=?", (json.dumps(result, separators=(",", ":")), datetime.now(timezone.utc).isoformat(), run_id))
        self.c.commit()

    def fail(self, run_id: str, err: str) -> None:
        self.c.execute("UPDATE research_runs SET status='ERROR',error=?,finished_at=? WHERE run_id=?", (err, datetime.now(timezone.utc).isoformat(), run_id))
        self.c.commit()

    def latest(self) -> dict[str, Any] | None:
        r = self.c.execute("SELECT * FROM research_runs ORDER BY created_at DESC LIMIT 1").fetchone()
        if not r:
            return None
        d = dict(r)
        if d.get("result_json"):
            try:
                d["result"] = json.loads(d.pop("result_json"))
            except Exception:
                pass
        return d


db = ResearchDB(DB_PATH)


class OKXHistory:
    def __init__(self):
        self.h = httpx.AsyncClient(timeout=20, headers={"User-Agent": "MRC-Research/1.0"})

    async def close(self) -> None:
        await self.h.aclose()

    async def _page(self, inst: str, bar: str, after: int) -> list[list[Any]]:
        r = await self.h.get(BASE + "/api/v5/market/history-candles", params={"instId": inst, "bar": bar, "after": str(after), "limit": "100"})
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0":
            raise RuntimeError(f"OKX history {j.get('code')} {j.get('msg')}")
        return j.get("data", [])

    async def fetch(self, inst: str, bar: str, start_ms: int, end_ms: int) -> list[dict[str, float]]:
        cache = CACHE_DIR / f"{inst}_{bar}_{start_ms}_{end_ms}.json"
        if cache.exists():
            try:
                return json.loads(cache.read_text())
            except Exception:
                pass
        cursor = end_ms + 1
        out: dict[int, dict[str, float]] = {}
        for _ in range(500):
            rows = await self._page(inst, bar, cursor)
            if not rows:
                break
            ts_vals: list[int] = []
            for r in rows:
                if len(r) < 9 or str(r[8]) != "1":
                    continue
                ts = int(r[0])
                ts_vals.append(ts)
                if start_ms <= ts < end_ms:
                    out[ts] = {"ot": ts, "o": f(r[1]), "h": f(r[2]), "l": f(r[3]), "c": f(r[4]), "v": f(r[5])}
            if not ts_vals:
                break
            oldest = min(ts_vals)
            if oldest <= start_ms:
                break
            cursor = oldest
            await asyncio.sleep(0.11)
        data = [out[k] for k in sorted(out)]
        try:
            cache.write_text(json.dumps(data, separators=(",", ":")))
        except Exception:
            pass
        return data


def continuity(bs: list[dict[str, float]], step: int) -> dict[str, Any]:
    if not bs:
        return {"rows": 0, "continuous": False, "missing": None}
    missing = 0
    dup = 0
    seen = set()
    for b in bs:
        if b["ot"] in seen:
            dup += 1
        seen.add(b["ot"])
    for a, b in zip(bs, bs[1:]):
        gap = int((b["ot"] - a["ot"]) // step) - 1
        if gap > 0:
            missing += gap
    expected = int((bs[-1]["ot"] - bs[0]["ot"]) // step) + 1
    return {"rows": len(bs), "expected": expected, "continuous": missing == 0 and dup == 0 and len(bs) == expected, "missing": missing, "duplicates": dup, "first": iso_ms(int(bs[0]["ot"])), "last": iso_ms(int(bs[-1]["ot"]))}


def candidates_for_symbol(symbol: str, priority: int, b15: list[dict[str, float]], b1h: list[dict[str, float]], signal_start: int, signal_end: int) -> list[Candidate]:
    h_close = [int(x["ot"] + H1) for x in b1h]
    out: list[Candidate] = []
    hp = 0
    for i in range(40, len(b15) - MAX_HOLD_BARS - 1):
        sig = b15[i]
        signal_t = int(sig["ot"] + M15)
        if signal_t < signal_start or signal_t >= signal_end:
            continue
        while hp + 1 < len(h_close) and h_close[hp + 1] <= signal_t:
            hp += 1
        if not h_close or h_close[hp] > signal_t:
            continue
        closes = [float(x["c"]) for x in b1h[max(0, hp - 119): hp + 1]]
        if len(closes) < 60:
            continue
        e20, e50 = ema(closes, 20), ema(closes, 50)
        prev = b15[i - 20:i]
        up, dn = max(float(x["h"]) for x in prev), min(float(x["l"]) for x in prev)
        side = "LONG" if sig["c"] > up else "SHORT" if sig["c"] < dn else None
        if not side or (side == "LONG" and not e20 > e50) or (side == "SHORT" and not e20 < e50):
            continue
        a = atr(b15[i - 39:i + 1], 14)
        if a <= 0:
            continue
        entry_bar = b15[i + 1]
        entry = float(entry_bar["o"])
        chase = abs(entry - float(sig["c"])) / a
        if chase > MAX_CHASE:
            continue
        sd = STOP_ATR * a
        stop = entry - sd if side == "LONG" else entry + sd
        target = entry + TARGET_R * sd if side == "LONG" else entry - TARGET_R * sd
        outcome, exit_px = "TIME", float(b15[i + MAX_HOLD_BARS]["c"])
        exit_t = int(b15[i + MAX_HOLD_BARS]["ot"] + M15)
        for j in range(i + 1, i + MAX_HOLD_BARS + 1):
            x = b15[j]
            hit_stop = x["l"] <= stop if side == "LONG" else x["h"] >= stop
            hit_target = x["h"] >= target if side == "LONG" else x["l"] <= target
            if hit_stop or hit_target:
                if hit_stop:
                    outcome, exit_px = "STOP", stop
                else:
                    outcome, exit_px = "TARGET", target
                exit_t = int(x["ot"] + M15)
                break
        out.append(Candidate(symbol, priority, signal_t, int(entry_bar["ot"]), side, entry, stop, target, a, exit_t, exit_px, outcome, chase))
    return out


def metric_block(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"trades": 0, "targets": 0, "stops": 0, "timeouts": 0, "expectancy_r": 0, "win_rate": 0, "profit_factor": None, "total_r": 0, "pnl_usd": 0}
    rs = [float(x["r_net"]) for x in trades]
    pos, neg = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    return {"trades": len(trades), "targets": sum(x["outcome"] == "TARGET" for x in trades), "stops": sum(x["outcome"] == "STOP" for x in trades), "timeouts": sum(x["outcome"] == "TIME" for x in trades), "expectancy_r": round(sum(rs) / len(rs), 5), "win_rate": round(sum(x > 0 for x in rs) / len(rs), 5), "profit_factor": round(pos / neg, 4) if neg else None, "total_r": round(sum(rs), 4), "pnl_usd": round(sum(float(x["pnl_usd"]) for x in trades), 2)}


def simulate(cands: list[Candidate], use_daily_lock: bool) -> dict[str, Any]:
    cands = sorted(cands, key=lambda x: (x.entry_t, x.priority))
    equity = START_EQ
    peak_eq = equity
    max_dd_pct = 0.0
    cum_r = peak_r = 0.0
    max_dd_r = 0.0
    open_until = -1
    day_pnl: dict[str, float] = {}
    lock_dates: set[str] = set()
    executed: list[dict[str, Any]] = []
    skip_open = skip_lock = loss_streak = max_loss_streak = 0
    for c in cands:
        if c.entry_t < open_until:
            skip_open += 1
            continue
        dkey = day_key(c.entry_t)
        if use_daily_lock and day_pnl.get(dkey, 0.0) <= -DAILY_LOCK_USD:
            skip_lock += 1
            lock_dates.add(dkey)
            continue
        risk_usd = equity * RISK_PCT
        stopdist = abs(c.entry - c.stop)
        qty = min(risk_usd / stopdist if stopdist else 0.0, equity / c.entry if c.entry else 0.0)
        sign = 1 if c.side == "LONG" else -1
        gross = (c.exit_px - c.entry) * sign * qty
        fees = (c.entry + c.exit_px) * qty * (COST / 2)
        pnl = gross - fees
        r_net = pnl / risk_usd if risk_usd else 0.0
        equity += pnl
        peak_eq = max(peak_eq, equity)
        max_dd_pct = min(max_dd_pct, equity / peak_eq - 1 if peak_eq else 0)
        cum_r += r_net
        peak_r = max(peak_r, cum_r)
        max_dd_r = min(max_dd_r, cum_r - peak_r)
        close_day = day_key(c.exit_t)
        day_pnl[close_day] = day_pnl.get(close_day, 0.0) + pnl
        if r_net < 0:
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0
        executed.append({"symbol": c.symbol, "side": c.side, "entry_t": c.entry_t, "exit_t": c.exit_t, "entry": c.entry, "exit": c.exit_px, "outcome": c.outcome, "chase_atr": c.chase_atr, "risk_usd": risk_usd, "qty": qty, "pnl_usd": pnl, "r_net": r_net, "equity_after": equity})
        open_until = c.exit_t
    by_asset = {s: metric_block([x for x in executed if x["symbol"] == s]) for s in MAP}
    months = sorted({month_key(x["exit_t"]) for x in executed})
    by_month = {m: metric_block([x for x in executed if month_key(x["exit_t"]) == m]) for m in months}
    result = metric_block(executed)
    result.update({"final_equity": round(equity, 2), "net_pct": round((equity / START_EQ - 1) * 100, 4), "max_drawdown_pct": round(max_dd_pct * 100, 4), "max_drawdown_r": round(max_dd_r, 4), "max_consecutive_losses": max_loss_streak, "skipped_open_position": skip_open, "skipped_daily_lock": skip_lock, "daily_lock_dates": sorted(lock_dates), "per_asset": by_asset, "monthly": by_month})
    return result


async def run_research(start_text: str = DEFAULT_START, end_text: str = DEFAULT_END) -> dict[str, Any]:
    start_dt, end_dt = parse_dt(start_text), parse_dt(end_text)
    signal_start, signal_end = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
    warm15 = int((start_dt - timedelta(days=2)).timestamp() * 1000)
    warm1h = int((start_dt - timedelta(days=7)).timestamp() * 1000)
    data_end = int((end_dt + timedelta(days=1, hours=1)).timestamp() * 1000)
    client = OKXHistory()
    all_cands: list[Candidate] = []
    integrity: dict[str, Any] = {}
    raw: dict[str, int] = {}
    try:
        for prio, (symbol, inst) in enumerate(MAP.items()):
            b15 = await client.fetch(inst, "15m", warm15, data_end)
            b1 = await client.fetch(inst, "1H", warm1h, signal_end)
            integrity[symbol] = {"15m": continuity(b15, M15), "1h": continuity(b1, H1)}
            cs = candidates_for_symbol(symbol, prio, b15, b1, signal_start, signal_end)
            raw[symbol] = len(cs)
            all_cands.extend(cs)
    finally:
        await client.close()
    with_lock, no_lock = simulate(all_cands, True), simulate(all_cands, False)
    return {"strategy": STRATEGY, "source": "OKX public BTC/ETH USDT perpetual swaps", "period": {"start": start_dt.isoformat(), "end_exclusive": end_dt.isoformat()}, "spec": {"trend": "1H EMA20 vs EMA50, max 120 fully closed bars", "trigger": "15m close beyond previous Donchian20 in trend direction", "atr": "Wilder ATR14 recomputed on last 40 confirmed 15m bars", "entry": "next 15m open (historical approximation of post-close executable price)", "stop": "1.5 ATR", "target": "2R / 3 ATR", "max_chase": "0.5 ATR", "max_hold": "24h", "cost": "6 bps round-trip", "risk": "0.25% current equity, 1x notional cap", "portfolio": "one global position, BTC tie priority", "ambiguity": "same 15m stop+target => STOP", "daily_lock": "-1% initial equity closed PnL per UTC day"}, "integrity": integrity, "raw_candidates": raw, "raw_candidates_total": len(all_cands), "with_daily_lock": with_lock, "without_daily_lock_control": no_lock, "generated_at": datetime.now(timezone.utc).isoformat()}


class ResearchService:
    def __init__(self):
        self.state: dict[str, Any] = {"status": "IDLE", "last": db.latest()}
        self.task: asyncio.Task | None = None

    async def run(self, force: bool = False) -> None:
        latest = db.latest()
        if not force and latest and latest.get("status") == "DONE" and latest.get("start_at") == DEFAULT_START and latest.get("end_at") == DEFAULT_END:
            self.state = {"status": "DONE", "last": latest}
            return
        run_id = f"{STRATEGY}:{DEFAULT_START}:{DEFAULT_END}"
        db.start(run_id, DEFAULT_START, DEFAULT_END)
        self.state = {"status": "RUNNING", "run_id": run_id}
        try:
            result = await run_research(DEFAULT_START, DEFAULT_END)
            db.finish(run_id, result)
            self.state = {"status": "DONE", "last": db.latest()}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            db.fail(run_id, f"{type(exc).__name__}: {exc}")
            self.state = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}", "last": db.latest()}

    def start(self, force: bool = False) -> asyncio.Task:
        if self.task and not self.task.done():
            return self.task
        self.task = asyncio.create_task(self.run(force))
        return self.task


service = ResearchService()
router = APIRouter()

@router.get("/api/research/baseline")
async def research_state():
    return {"runtime": service.state, "latest": db.latest()}

@router.post("/api/research/run")
async def research_run():
    service.start(force=True)
    return JSONResponse({"accepted": True, "status": "RUNNING"}, status_code=202)

RESEARCH_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MRC Baseline Research</title><style>body{margin:0;background:#06111a;color:#eef7ff;font:14px system-ui}.w{max-width:1100px;margin:auto;padding:24px}.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.c{background:#0d1c29;border:1px solid #203648;border-radius:14px;padding:16px}.b{font-size:25px;font-weight:800}.m{color:#8da9bc}.ok{color:#39df84}.bad{color:#ff6577}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #203648;text-align:left}</style></head><body><main class='w'><h1>Baseline Research · TREND_BREAKOUT_V1</h1><p class='m'>Same frozen strategy specification, historical OKX perp data, costs, one global position and daily lock.</p><div id='st' class='c'>Loading…</div><div id='cards' class='g' style='margin-top:14px'></div><h3>Per asset</h3><div id='assets' class='c'></div><h3>Monthly</h3><div id='months' class='c'></div><h3>Integrity</h3><div id='int' class='c'></div></main><script>const n=(x,d=3)=>Number.isFinite(Number(x))?Number(x).toFixed(d):'—';async function g(){let r=await fetch('/api/research/baseline',{cache:'no-store'}),x=await r.json(),z=x.latest||{},q=z.result||{};st.innerHTML=`Status: <b>${z.status||x.runtime?.status||'—'}</b>${z.error?`<div class=bad>${z.error}</div>`:''}`;if(!q.with_daily_lock)return;let m=q.with_daily_lock;cards.innerHTML=`<div class=c><span class=m>Trades</span><div class=b>${m.trades}</div></div><div class=c><span class=m>Expectancy</span><div class='b ${m.expectancy_r>0?'ok':'bad'}'>${n(m.expectancy_r)}R</div></div><div class=c><span class=m>Profit factor</span><div class=b>${n(m.profit_factor)}</div></div><div class=c><span class=m>Net</span><div class='b ${m.net_pct>0?'ok':'bad'}'>${n(m.net_pct,2)}%</div></div><div class=c><span class=m>Max DD</span><div class=b>${n(m.max_drawdown_pct,2)}%</div></div><div class=c><span class=m>Raw candidates</span><div class=b>${q.raw_candidates_total}</div></div>`;assets.innerHTML='<table><tr><th>Asset</th><th>Trades</th><th>Expectancy</th><th>PF</th><th>Total R</th></tr>'+Object.entries(m.per_asset||{}).map(([k,v])=>`<tr><td>${k}</td><td>${v.trades}</td><td>${n(v.expectancy_r)}</td><td>${n(v.profit_factor)}</td><td>${n(v.total_r)}</td></tr>`).join('')+'</table>';months.innerHTML='<table><tr><th>Month</th><th>Trades</th><th>Expectancy</th><th>PF</th><th>Total R</th></tr>'+Object.entries(m.monthly||{}).map(([k,v])=>`<tr><td>${k}</td><td>${v.trades}</td><td>${n(v.expectancy_r)}</td><td>${n(v.profit_factor)}</td><td>${n(v.total_r)}</td></tr>`).join('')+'</table>';int.innerHTML=`<pre>${JSON.stringify(q.integrity,null,2)}</pre>`}g();setInterval(g,5000)</script></body></html>"""

@router.get("/research", response_class=HTMLResponse)
async def research_page():
    return RESEARCH_HTML
