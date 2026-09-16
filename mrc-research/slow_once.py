from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import app

STRATEGY = 'SLOW_TREND_BREAKOUT_V1'
END = datetime(2026, 9, 16, 18, 30, tzinfo=timezone.utc)
DAYS = 365
WARMUP_DAYS = 14
STOP_ATR = 1.5
TARGET_R = 2.0
MAX_CHASE = 0.5
MAX_HOLD_MS = 72 * 3600 * 1000


def build_candidates(symbol: str, b1: list[dict[str, float | int]], b4: list[dict[str, float | int]], research_start_ms: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    j = -1
    for i in range(40, len(b1) - 1):
        sig = b1[i]
        sig_ct = int(sig['ct'])
        if int(sig['t']) < research_start_ms:
            continue
        while j + 1 < len(b4) and int(b4[j + 1]['ct']) <= sig_ct:
            j += 1
        if j < 49:
            continue
        prev20 = b1[i - 20:i]
        hi = max(float(x['h']) for x in prev20)
        lo = min(float(x['l']) for x in prev20)
        side = 'L' if float(sig['c']) > hi else 'S' if float(sig['c']) < lo else None
        if side is None:
            continue
        h4w = b4[max(0, j - 119):j + 1]
        closes = [float(x['c']) for x in h4w]
        e20 = app.ema(closes, 20)
        e50 = app.ema(closes, 50)
        if side == 'L' and not e20 > e50:
            continue
        if side == 'S' and not e20 < e50:
            continue
        a = app.atr(b1[i - 39:i + 1], 14)
        if a <= 0:
            continue
        eb = b1[i + 1]
        entry = float(eb['o'])
        entry_t = int(eb['t'])
        chase = abs(entry - float(sig['c'])) / a
        if chase > MAX_CHASE:
            continue
        stop = entry - STOP_ATR * a if side == 'L' else entry + STOP_ATR * a
        target = entry + TARGET_R * STOP_ATR * a if side == 'L' else entry - TARGET_R * STOP_ATR * a
        deadline = entry_t + MAX_HOLD_MS
        exit_t = None
        exit_px = None
        outcome = None
        k = i + 1
        while k < len(b1) and int(b1[k]['t']) <= deadline:
            bar = b1[k]
            if side == 'L':
                stop_hit = float(bar['l']) <= stop
                target_hit = float(bar['h']) >= target
            else:
                stop_hit = float(bar['h']) >= stop
                target_hit = float(bar['l']) <= target
            if stop_hit or target_hit:
                exit_t = int(bar['t'])
                if stop_hit:
                    outcome, exit_px = 'STOP', stop
                else:
                    outcome, exit_px = 'TARGET', target
                break
            k += 1
        if outcome is None:
            if not b1 or int(b1[-1]['t']) < deadline:
                continue
            while k < len(b1) and int(b1[k]['t']) < deadline:
                k += 1
            if k >= len(b1):
                continue
            outcome, exit_t, exit_px = 'TIME', int(b1[k]['t']), float(b1[k]['o'])
        risk_unit = STOP_ATR * a
        gross_r = ((float(exit_px) - entry) * (1.0 if side == 'L' else -1.0)) / risk_unit
        cost_r = (entry + float(exit_px)) * (app.COST / 2.0) / risk_unit
        out.append({
            'symbol': symbol,
            'signal_t': int(sig['t']),
            'entry_t': entry_t,
            'exit_t': int(exit_t),
            'side': side,
            'outcome': outcome,
            'entry': entry,
            'exit': float(exit_px),
            'atr': a,
            'chase_atr': chase,
            'net_r': gross_r - cost_r,
            'gross_r': gross_r,
            'cost_r': cost_r,
            'ema20': e20,
            'ema50': e50,
        })
    return out


async def monitor():
    while True:
        await asyncio.sleep(10)
        print('SLOW_RESEARCH_PROGRESS=' + json.dumps(app.STATE.get('progress', {}), separators=(',', ':'), default=str), flush=True)


async def main():
    research_start = END - timedelta(days=DAYS)
    fetch_start = research_start - timedelta(days=WARMUP_DAYS)
    start_ms = int(fetch_start.timestamp() * 1000)
    research_start_ms = int(research_start.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    app.STATE['progress'] = {}
    client = app.OKXHistory()
    mon = asyncio.create_task(monitor())
    try:
        all_candidates = []
        counts = {}
        for symbol, inst in app.MAP.items():
            r1 = await client.fetch_range(inst, '1H', start_ms, end_ms)
            r4 = await client.fetch_range(inst, '4H', start_ms, end_ms)
            b1 = [app.parse_bar(x, 60) for x in r1]
            b4 = [app.parse_bar(x, 240) for x in r4]
            cs = build_candidates(symbol, b1, b4, research_start_ms)
            all_candidates.extend(cs)
            counts[symbol] = {
                'bars_1h': len(b1),
                'bars_4h': len(b4),
                'raw_candidates': len(cs),
                'first_1h': app.iso_ms(int(b1[0]['t'])) if b1 else None,
                'last_1h': app.iso_ms(int(b1[-1]['t'])) if b1 else None,
            }
            print('SLOW_SYMBOL_DONE=' + json.dumps({symbol: counts[symbol]}, separators=(',', ':')), flush=True)
        portfolio = app.simulate(all_candidates, long_only=False)
        selected = portfolio.get('selected') or []
        btc = app.simulate([x for x in all_candidates if x['symbol'] == 'BTC'])
        eth = app.simulate([x for x in all_candidates if x['symbol'] == 'ETH'])
        result = {
            'strategy': STRATEGY,
            'source': 'OKX official public history-candles',
            'research_window': {'start': research_start.isoformat(), 'end': END.isoformat(), 'days': DAYS},
            'protocol': {
                'signal': '1H Donchian20 confirmed breakout',
                'trend': '4H EMA20/EMA50, max 120 confirmed 4H bars',
                'atr': 'Wilder ATR14 over last 40 confirmed 1H bars',
                'stop': '1.5 ATR',
                'target': '2R = 3 ATR',
                'max_hold': '72h',
                'chase': '<=0.5 ATR',
                'cost': app.COST,
                'risk': app.RISK_PCT,
                'portfolio': 'one global position, BTC tie priority, strict next entry > prior exit, 1% initial-equity daily lock',
                'ambiguity': 'STOP wins same-bar stop/target conflict',
            },
            'source_counts': counts,
            'raw_candidate_count': len(all_candidates),
            'portfolio': app.summarize_without_trades(portfolio),
            'btc_only': app.summarize_without_trades(btc),
            'eth_only': app.summarize_without_trades(eth),
            'selected_by_side': app.group_metrics(selected, 'side'),
            'selected_by_quarter': app.group_metrics(selected, 'quarter'),
            'selected_by_symbol': app.group_metrics(selected, 'symbol'),
        }
        print('SLOW_RESEARCH_RESULT=' + json.dumps(result, separators=(',', ':'), default=str), flush=True)
    finally:
        mon.cancel()
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
