from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import slow_v1 as live
import research_v1 as research


def _simulate_live_parity(cands, use_daily_lock: bool):
    cands = sorted(cands, key=lambda x: (x.entry_t, x.priority))
    equity = research.START_EQ
    peak_eq = equity
    max_dd_pct = 0.0
    cum_r = peak_r = 0.0
    max_dd_r = 0.0
    open_until = -1
    open_symbol = None
    day_pnl = {}
    lock_dates = set()
    executed = []
    skip_open = skip_lock = loss_streak = max_loss_streak = 0
    for c in cands:
        blocked_same_poll = c.entry_t == open_until and open_symbol == "ETHUSDT" and c.symbol == "BTCUSDT"
        if c.entry_t < open_until or blocked_same_poll:
            skip_open += 1
            continue
        dkey = research.day_key(c.entry_t)
        if use_daily_lock and day_pnl.get(dkey, 0.0) <= -research.DAILY_LOCK_USD:
            skip_lock += 1
            lock_dates.add(dkey)
            continue
        risk_usd = equity * research.RISK_PCT
        stopdist = abs(c.entry - c.stop)
        qty = min(risk_usd / stopdist if stopdist else 0.0, equity / c.entry if c.entry else 0.0)
        sign = 1 if c.side == "LONG" else -1
        gross = (c.exit_px - c.entry) * sign * qty
        fees = (c.entry + c.exit_px) * qty * (research.COST / 2)
        pnl = gross - fees
        r_net = pnl / risk_usd if risk_usd else 0.0
        equity += pnl
        peak_eq = max(peak_eq, equity)
        max_dd_pct = min(max_dd_pct, equity / peak_eq - 1 if peak_eq else 0)
        cum_r += r_net
        peak_r = max(peak_r, cum_r)
        max_dd_r = min(max_dd_r, cum_r - peak_r)
        close_day = research.day_key(c.exit_t)
        day_pnl[close_day] = day_pnl.get(close_day, 0.0) + pnl
        if r_net < 0:
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0
        executed.append({"symbol": c.symbol, "side": c.side, "entry_t": c.entry_t, "exit_t": c.exit_t, "entry": c.entry, "exit": c.exit_px, "outcome": c.outcome, "chase_atr": c.chase_atr, "risk_usd": risk_usd, "qty": qty, "pnl_usd": pnl, "r_net": r_net, "equity_after": equity})
        open_until = c.exit_t
        open_symbol = c.symbol
    by_asset = {s: research.metric_block([x for x in executed if x["symbol"] == s]) for s in research.MAP}
    months = sorted({research.month_key(x["exit_t"]) for x in executed})
    by_month = {m: research.metric_block([x for x in executed if research.month_key(x["exit_t"]) == m]) for m in months}
    result = research.metric_block(executed)
    result.update({"final_equity": round(equity, 2), "net_pct": round((equity / research.START_EQ - 1) * 100, 4), "max_drawdown_pct": round(max_dd_pct * 100, 4), "max_drawdown_r": round(max_dd_r, 4), "max_consecutive_losses": max_loss_streak, "skipped_open_position": skip_open, "skipped_daily_lock": skip_lock, "daily_lock_dates": sorted(lock_dates), "per_asset": by_asset, "monthly": by_month})
    return result


research.simulate = _simulate_live_parity
app = live.app
app.include_router(research.router)
_original_lifespan = app.router.lifespan_context


def _research_done(task: asyncio.Task):
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        print(f"research_task_error {type(exc).__name__}: {exc}", flush=True)
        return
    latest = research.db.latest() or {}
    if latest.get("status") == "DONE":
        r = latest.get("result") or {}
        m = r.get("with_daily_lock") or {}
        summary = {"status": "DONE", "raw": r.get("raw_candidates"), "trades": m.get("trades"), "expectancy_r": m.get("expectancy_r"), "pf": m.get("profit_factor"), "total_r": m.get("total_r"), "net_pct": m.get("net_pct"), "max_dd_pct": m.get("max_drawdown_pct"), "monthly": m.get("monthly"), "per_asset": m.get("per_asset")}
        print("research_done " + json.dumps(summary, separators=(",", ":")), flush=True)
    else:
        print("research_finished_non_done " + json.dumps(latest, default=str)[:2000], flush=True)


@asynccontextmanager
async def _combined_lifespan(app_obj):
    async with _original_lifespan(app_obj):
        task = research.service.start(force=False)
        task.add_done_callback(_research_done)
        try:
            yield
        finally:
            if task and not task.done():
                task.cancel()


app.router.lifespan_context = _combined_lifespan
