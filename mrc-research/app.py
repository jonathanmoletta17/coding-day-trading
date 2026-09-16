from __future__ import annotations

import asyncio
import math
import os
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

BASE = "https://www.okx.com"
MAP = {
    "BTC": "BTC-USDT-SWAP",
    "ETH": "ETH-USDT-SWAP",
}
DAYS = int(os.getenv("MRC_RESEARCH_DAYS", "365"))
COST = float(os.getenv("MRC_ROUNDTRIP_COST", "0.0006"))
RISK_PCT = float(os.getenv("MRC_RISK_PCT", "0.0025"))
EQ0 = float(os.getenv("MRC_PAPER_EQUITY", "10000"))
DAILY_LOCK_USDT = EQ0 * 0.01
STOP_ATR = 1.5
TARGET_R = 2.0
MAX_CHASE_ATR = 0.5
MAX_HOLD_MS = 24 * 3600 * 1000
STRATEGY = "TREND_BREAKOUT_V1"
PROTOCOL = {
    "trend": "1H EMA20 vs EMA50, using at most the last 120 confirmed 1H bars",
    "entry_signal": "confirmed 15m close breaks prior 20-bar Donchian in trend direction",
    "entry_proxy": "next 15m bar open",
    "atr": "Wilder ATR14 recomputed over the last 40 confirmed 15m bars, exactly like live helper",
    "stop": "1.5 ATR",
    "target": "2R = 3 ATR from entry",
    "chase_filter": "abs(next_open - signal_close) / ATR <= 0.5",
    "same_bar_conflict": "STOP wins if stop and target are both touched in one 15m bar",
    "time_stop": "24h; first 15m open at/after deadline if neither stop nor target was hit",
    "cost": COST,
    "portfolio": "one global position; BTC priority on exact entry-time ties; strict next entry > prior exit",
    "risk": RISK_PCT,
    "daily_lock": DAILY_LOCK_USDT,
}

STATE: dict[str, Any] = {
    "status": "STARTING",
    "strategy": STRATEGY,
    "days": DAYS,
    "started_at": None,
    "finished_at": None,
    "progress": {},
    "result": None,
    "error": None,
}
TASK: asyncio.Task | None = None
LOCK = asyncio.Lock()


def iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def day_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def quarter_utc(ms: int) -> str:
    d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def finite(x: Any, default: float = 0.0) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


def ema(xs: list[float], n: int) -> float:
    a = 2.0 / (n + 1.0)
    z = xs[0]
    for x in xs[1:]:
        z = a * x + (1.0 - a) * z
    return z


def atr(window: list[dict[str, float]], n: int = 14) -> float:
    trs: list[float] = []
    for i in range(1, len(window)):
        cur = window[i]
        prev = window[i - 1]
        trs.append(max(cur["h"] - cur["l"], abs(cur["h"] - prev["c"]), abs(cur["l"] - prev["c"])))
    if not trs:
        return 0.0
    z = sum(trs[:n]) / min(n, len(trs))
    for x in trs[n:]:
        z = ((n - 1.0) * z + x) / n
    return z


def parse_bar(row: list[Any], mins: int) -> dict[str, float | int]:
    ts = int(row[0])
    return {
        "t": ts,
        "o": finite(row[1]),
        "h": finite(row[2]),
        "l": finite(row[3]),
        "c": finite(row[4]),
        "ct": ts + mins * 60_000,
    }


class OKXHistory:
    def __init__(self) -> None:
        self.h = httpx.AsyncClient(timeout=20, headers={"User-Agent": "MRC-Research/1.0"})

    async def page(self, inst: str, bar: str, after: int | None = None) -> list[list[Any]]:
        q: dict[str, str] = {"instId": inst, "bar": bar, "limit": "300"}
        if after is not None:
            q["after"] = str(after)
        r = await self.h.get(BASE + "/api/v5/market/history-candles", params=q)
        r.raise_for_status()
        j = r.json()
        if str(j.get("code")) != "0":
            raise RuntimeError(f"OKX code={j.get('code')} msg={j.get('msg')}")
        return j.get("data") or []

    async def fetch_range(self, inst: str, bar: str, start_ms: int, end_ms: int) -> list[list[Any]]:
        out: dict[int, list[Any]] = {}
        cursor: int | None = None
        calls = 0
        while True:
            rows = await self.page(inst, bar, cursor)
            calls += 1
            if not rows:
                break
            ts_values = [int(x[0]) for x in rows]
            for row in rows:
                ts = int(row[0])
                if start_ms <= ts <= end_ms and len(row) >= 9 and str(row[8]) == "1":
                    out[ts] = row
            oldest = min(ts_values)
            async with LOCK:
                STATE["progress"][f"{inst}:{bar}"] = {
                    "calls": calls,
                    "rows_kept": len(out),
                    "oldest_seen": iso_ms(oldest),
                }
            if oldest <= start_ms:
                break
            if cursor is not None and oldest >= cursor:
                raise RuntimeError(f"pagination stalled {inst} {bar} at {oldest}")
            cursor = oldest
            await asyncio.sleep(0.13)
        return [out[k] for k in sorted(out)]

    async def close(self) -> None:
        await self.h.aclose()


def build_candidates(symbol: str, b15: list[dict[str, float | int]], b1h: list[dict[str, float | int]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    j = -1
    for i in range(40, len(b15) - 1):
        sig = b15[i]
        sig_ct = int(sig["ct"])
        while j + 1 < len(b1h) and int(b1h[j + 1]["ct"]) <= sig_ct:
            j += 1
        if j < 49:
            continue
        prev20 = b15[i - 20:i]
        hi = max(float(x["h"]) for x in prev20)
        lo = min(float(x["l"]) for x in prev20)
        side: str | None = None
        if float(sig["c"]) > hi:
            side = "L"
        elif float(sig["c"]) < lo:
            side = "S"
        if side is None:
            continue
        h1_window = b1h[max(0, j - 119):j + 1]
        closes = [float(x["c"]) for x in h1_window]
        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        if side == "L" and not (e20 > e50):
            continue
        if side == "S" and not (e20 < e50):
            continue
        a = atr(b15[i - 39:i + 1], 14)
        if a <= 0:
            continue
        entry_bar = b15[i + 1]
        entry = float(entry_bar["o"])
        entry_t = int(entry_bar["t"])
        chase = abs(entry - float(sig["c"])) / a
        if chase > MAX_CHASE_ATR:
            continue
        stop = entry - STOP_ATR * a if side == "L" else entry + STOP_ATR * a
        target = entry + TARGET_R * STOP_ATR * a if side == "L" else entry - TARGET_R * STOP_ATR * a
        deadline = entry_t + MAX_HOLD_MS
        exit_t: int | None = None
        exit_px: float | None = None
        outcome: str | None = None
        k = i + 1
        while k < len(b15) and int(b15[k]["t"]) <= deadline:
            bar = b15[k]
            if side == "L":
                stop_hit = float(bar["l"]) <= stop
                target_hit = float(bar["h"]) >= target
            else:
                stop_hit = float(bar["h"]) >= stop
                target_hit = float(bar["l"]) <= target
            if stop_hit or target_hit:
                exit_t = int(bar["t"])
                if stop_hit:
                    outcome = "STOP"
                    exit_px = stop
                else:
                    outcome = "TARGET"
                    exit_px = target
                break
            k += 1
        if outcome is None:
            if not b15 or int(b15[-1]["t"]) < deadline:
                continue
            while k < len(b15) and int(b15[k]["t"]) < deadline:
                k += 1
            if k >= len(b15):
                continue
            outcome = "TIME"
            exit_t = int(b15[k]["t"])
            exit_px = float(b15[k]["o"])
        risk_unit = STOP_ATR * a
        gross_r = ((exit_px - entry) * (1.0 if side == "L" else -1.0)) / risk_unit
        cost_r = (entry + exit_px) * (COST / 2.0) / risk_unit
        net_r = gross_r - cost_r
        out.append({
            "symbol": symbol,
            "signal_t": int(sig["t"]),
            "entry_t": entry_t,
            "exit_t": int(exit_t),
            "side": side,
            "outcome": outcome,
            "entry": entry,
            "exit": exit_px,
            "atr": a,
            "chase_atr": chase,
            "net_r": net_r,
            "gross_r": gross_r,
            "cost_r": cost_r,
            "ema20": e20,
            "ema50": e50,
        })
    return out


def bootstrap_ci(rs: list[float], draws: int = 4000) -> dict[str, float | None]:
    if not rs:
        return {"lo": None, "median": None, "hi": None, "p_mean_gt_0": None}
    rng = random.Random(20260916 + len(rs))
    n = len(rs)
    means: list[float] = []
    for _ in range(draws):
        means.append(sum(rs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    def q(p: float) -> float:
        idx = min(len(means) - 1, max(0, int(p * (len(means) - 1))))
        return means[idx]
    return {
        "lo": q(0.025),
        "median": q(0.5),
        "hi": q(0.975),
        "p_mean_gt_0": sum(x > 0 for x in means) / len(means),
    }


def base_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rs = [float(x["net_r"]) for x in rows]
    if not rs:
        return {"n": 0}
    pos = sum(x for x in rs if x > 0)
    neg = -sum(x for x in rs if x < 0)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return {
        "n": len(rows),
        "targets": sum(x["outcome"] == "TARGET" for x in rows),
        "stops": sum(x["outcome"] == "STOP" for x in rows),
        "times": sum(x["outcome"] == "TIME" for x in rows),
        "win_rate": sum(x > 0 for x in rs) / len(rs),
        "expectancy_r": statistics.fmean(rs),
        "median_r": statistics.median(rs),
        "total_r": sum(rs),
        "profit_factor": (pos / neg) if neg > 0 else None,
        "max_drawdown_r": max_dd,
        "bootstrap_95": bootstrap_ci(rs),
    }


def simulate(rows: list[dict[str, Any]], long_only: bool = False) -> dict[str, Any]:
    rows = sorted(rows, key=lambda x: (int(x["entry_t"]), 0 if x["symbol"] == "BTC" else 1))
    equity = EQ0
    day_pnl: dict[str, float] = defaultdict(float)
    selected: list[dict[str, Any]] = []
    realized: list[dict[str, Any]] = []
    open_trade: dict[str, Any] | None = None

    def settle(tr: dict[str, Any]) -> None:
        nonlocal equity
        pnl = float(tr["net_r"]) * float(tr["risk_usdt"])
        equity += pnl
        day_pnl[day_utc(int(tr["exit_t"]))] += pnl
        z = dict(tr)
        z["pnl_usdt"] = pnl
        z["equity_after"] = equity
        realized.append(z)

    for cand in rows:
        if long_only and cand["side"] != "L":
            continue
        if open_trade is not None and int(cand["entry_t"]) > int(open_trade["exit_t"]):
            settle(open_trade)
            open_trade = None
        if open_trade is not None:
            continue
        if day_pnl[day_utc(int(cand["entry_t"]))] <= -DAILY_LOCK_USDT:
            continue
        z = dict(cand)
        z["equity_entry"] = equity
        z["risk_usdt"] = equity * RISK_PCT
        selected.append(z)
        open_trade = z
    if open_trade is not None:
        settle(open_trade)

    eqs = [EQ0] + [float(x["equity_after"]) for x in realized]
    peak = EQ0
    max_dd_pct = 0.0
    for eq in eqs:
        peak = max(peak, eq)
        max_dd_pct = min(max_dd_pct, eq / peak - 1.0)

    m = base_metrics(selected)
    m.update({
        "ending_equity": equity,
        "return_pct": equity / EQ0 - 1.0,
        "max_drawdown_pct": max_dd_pct,
        "locked_days": [d for d, p in sorted(day_pnl.items()) if p <= -DAILY_LOCK_USDT],
        "selected": selected,
    })
    return m


def summarize_without_trades(m: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in m.items() if k != "selected"}


def group_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if key == "side":
            g = "LONG" if r["side"] == "L" else "SHORT"
        elif key == "quarter":
            g = quarter_utc(int(r["entry_t"]))
        elif key == "symbol":
            g = str(r["symbol"])
        else:
            g = str(r.get(key))
        groups[g].append(r)
    return {g: base_metrics(v) for g, v in sorted(groups.items())}


async def research() -> None:
    start_dt = datetime.now(timezone.utc) - timedelta(days=DAYS + 7)
    end_dt = datetime.now(timezone.utc)
    research_start = end_dt - timedelta(days=DAYS)
    start_ms = int(start_dt.timestamp() * 1000)
    research_start_ms = int(research_start.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    async with LOCK:
        STATE["status"] = "FETCHING"
        STATE["started_at"] = datetime.now(timezone.utc).isoformat()
    client = OKXHistory()
    try:
        all_candidates: list[dict[str, Any]] = []
        source_counts: dict[str, Any] = {}
        for symbol, inst in MAP.items():
            rows15 = await client.fetch_range(inst, "15m", start_ms, end_ms)
            rows1h = await client.fetch_range(inst, "1H", start_ms, end_ms)
            b15 = [parse_bar(x, 15) for x in rows15]
            b1h = [parse_bar(x, 60) for x in rows1h]
            # Keep warm-up bars, but only admit signals in the requested research window.
            candidates = [x for x in build_candidates(symbol, b15, b1h) if int(x["signal_t"]) >= research_start_ms]
            all_candidates.extend(candidates)
            source_counts[symbol] = {
                "bars_15m": len(b15),
                "bars_1h": len(b1h),
                "raw_candidates": len(candidates),
                "first_15m": iso_ms(int(b15[0]["t"])) if b15 else None,
                "last_15m": iso_ms(int(b15[-1]["t"])) if b15 else None,
            }
            async with LOCK:
                STATE["progress"][symbol] = source_counts[symbol]

        async with LOCK:
            STATE["status"] = "ANALYZING"

        baseline = simulate(all_candidates, long_only=False)
        selected = list(baseline.get("selected") or [])
        btc = simulate([x for x in all_candidates if x["symbol"] == "BTC"], long_only=False)
        eth = simulate([x for x in all_candidates if x["symbol"] == "ETH"], long_only=False)
        # Post-hoc shadow only. It is NOT a promotion candidate from this same sample.
        long_shadow = simulate(all_candidates, long_only=True)

        result = {
            "strategy": STRATEGY,
            "source": "OKX official public history-candles",
            "research_window": {
                "start": research_start.isoformat(),
                "end": end_dt.isoformat(),
                "days": DAYS,
            },
            "protocol": PROTOCOL,
            "source_counts": source_counts,
            "raw_candidate_count": len(all_candidates),
            "portfolio": summarize_without_trades(baseline),
            "btc_only": summarize_without_trades(btc),
            "eth_only": summarize_without_trades(eth),
            "selected_by_side": group_metrics(selected, "side"),
            "selected_by_quarter": group_metrics(selected, "quarter"),
            "selected_by_symbol": group_metrics(selected, "symbol"),
            "post_hoc_shadow": {
                "name": "LONG_ONLY_SHADOW",
                "warning": "Discovered from the 30-day sanity sample; descriptive only. Must be validated on untouched future/OOS data before any promotion.",
                "metrics": summarize_without_trades(long_shadow),
            },
            "recent_selected_trades": [
                {
                    "symbol": x["symbol"],
                    "side": "LONG" if x["side"] == "L" else "SHORT",
                    "entry_time": iso_ms(int(x["entry_t"])),
                    "exit_time": iso_ms(int(x["exit_t"])),
                    "outcome": x["outcome"],
                    "net_r": x["net_r"],
                }
                for x in selected[-20:]
            ],
        }
        async with LOCK:
            STATE["result"] = result
            STATE["status"] = "DONE"
            STATE["finished_at"] = datetime.now(timezone.utc).isoformat()
            STATE["error"] = None
    except Exception as exc:
        async with LOCK:
            STATE["status"] = "ERROR"
            STATE["error"] = f"{type(exc).__name__}: {exc}"
            STATE["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise
    finally:
        await client.close()


app = FastAPI(title="MRC Research Runner", version="1.0")


@app.on_event("startup")
async def startup() -> None:
    global TASK
    TASK = asyncio.create_task(research())


@app.get("/healthz")
async def health() -> JSONResponse:
    alive = TASK is not None and not TASK.done()
    status = STATE.get("status")
    ok = status in {"FETCHING", "ANALYZING", "DONE"} or alive
    return JSONResponse({"ok": ok, "status": status, "error": STATE.get("error")}, status_code=200 if ok else 503)


@app.get("/result")
async def result() -> dict[str, Any]:
    async with LOCK:
        return dict(STATE)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "MRC Research Runner",
        "strategy": STRATEGY,
        "status": STATE.get("status"),
        "result_endpoint": "/result",
    }
