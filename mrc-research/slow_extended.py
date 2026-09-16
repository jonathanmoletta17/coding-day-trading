from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import app
import slow_once

STRATEGY = 'SLOW_TREND_BREAKOUT_V1'
END = datetime(2026, 9, 16, 18, 30, tzinfo=timezone.utc)
DAYS = 1095
WARMUP_DAYS = 30
MARKETS = {
    'BTC': 'BTC-USDT-SWAP',
    'ETH': 'ETH-USDT-SWAP',
    'SOL': 'SOL-USDT-SWAP',
    'BNB': 'BNB-USDT-SWAP',
    'XRP': 'XRP-USDT-SWAP',
}
COSTS = [0.0006, 0.0010, 0.0015, 0.0020]


def no_selected(m: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in m.items() if k != 'selected'}


def clone_cost(rows: list[dict[str, Any]], cost: float) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        z = dict(r)
        unit = float(r['cost_r']) / app.COST if app.COST else 0.0
        z['net_r'] = float(r['gross_r']) - unit * cost
        z['cost_r'] = unit * cost
        out.append(z)
    return out


def since(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = int((END - timedelta(days=days)).timestamp() * 1000)
    return [x for x in rows if int(x['entry_t']) >= cutoff]


def yearly(selected: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for x in selected:
        y = datetime.fromtimestamp(int(x['entry_t']) / 1000, tz=timezone.utc).strftime('%Y')
        groups[y].append(x)
    return {k: app.base_metrics(v) for k, v in sorted(groups.items())}


async def monitor():
    while True:
        await asyncio.sleep(15)
        print('EXTENDED_PROGRESS=' + json.dumps(app.STATE.get('progress', {}), separators=(',', ':'), default=str), flush=True)


async def main():
    start = END - timedelta(days=DAYS)
    fetch_start = start - timedelta(days=WARMUP_DAYS)
    start_ms = int(fetch_start.timestamp() * 1000)
    research_start_ms = int(start.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    app.STATE['progress'] = {}
    client = app.OKXHistory()
    mon = asyncio.create_task(monitor())
    try:
        all_rows: list[dict[str, Any]] = []
        counts: dict[str, Any] = {}
        failures: dict[str, str] = {}
        for symbol, inst in MARKETS.items():
            try:
                r1 = await client.fetch_range(inst, '1H', start_ms, end_ms)
                r4 = await client.fetch_range(inst, '4H', start_ms, end_ms)
                b1 = [app.parse_bar(x, 60) for x in r1]
                b4 = [app.parse_bar(x, 240) for x in r4]
                cs = slow_once.build_candidates(symbol, b1, b4, research_start_ms)
                all_rows.extend(cs)
                counts[symbol] = {
                    'bars_1h': len(b1),
                    'bars_4h': len(b4),
                    'raw_candidates': len(cs),
                    'first_1h': app.iso_ms(int(b1[0]['t'])) if b1 else None,
                    'last_1h': app.iso_ms(int(b1[-1]['t'])) if b1 else None,
                }
                print('EXTENDED_SYMBOL_DONE=' + json.dumps({symbol: counts[symbol]}, separators=(',', ':')), flush=True)
            except Exception as exc:
                failures[symbol] = f'{type(exc).__name__}: {exc}'
                print('EXTENDED_SYMBOL_ERROR=' + json.dumps({symbol: failures[symbol]}, separators=(',', ':')), flush=True)

        core = [x for x in all_rows if x['symbol'] in ('BTC', 'ETH')]
        external = [x for x in all_rows if x['symbol'] in ('SOL', 'BNB', 'XRP')]
        core3 = app.simulate(core)
        core_selected = core3.get('selected') or []
        all3 = app.simulate(all_rows)
        all_selected = all3.get('selected') or []

        trailing = {}
        for d in (365, 730, 1095):
            trailing[str(d)] = {
                'core': no_selected(app.simulate(since(core, d))),
                'all_markets': no_selected(app.simulate(since(all_rows, d))),
            }

        by_asset = {}
        for symbol in MARKETS:
            rows = [x for x in all_rows if x['symbol'] == symbol]
            by_asset[symbol] = no_selected(app.simulate(rows)) if rows else {'n': 0, 'error': failures.get(symbol)}

        stress = {}
        for cost in COSTS:
            k = f'{cost*10000:.0f}bps'
            stress[k] = {
                'core': no_selected(app.simulate(clone_cost(core, cost))),
                'all_markets': no_selected(app.simulate(clone_cost(all_rows, cost))),
            }

        result = {
            'strategy': STRATEGY,
            'validation': '3-year unchanged-rule temporal extension + external market replication + transaction-cost stress',
            'source': 'OKX official public history-candles',
            'research_window': {'start': start.isoformat(), 'end': END.isoformat(), 'days': DAYS, 'warmup_days': WARMUP_DAYS},
            'frozen_rules': {
                'signal': '1H Donchian20 confirmed breakout',
                'trend': '4H EMA20/EMA50',
                'atr': 'Wilder ATR14 on last 40 confirmed 1H bars',
                'stop': '1.5 ATR',
                'target': '2R',
                'max_hold': '72h',
                'chase': '<=0.5 ATR',
                'risk': app.RISK_PCT,
                'base_cost': app.COST,
                'ambiguity': 'STOP wins same-bar conflict',
                'portfolio': 'one global position, strict next entry > previous exit, 1% initial-equity daily lock',
            },
            'source_counts': counts,
            'failures': failures,
            'raw_candidate_count': len(all_rows),
            'core_btc_eth_3y': no_selected(core3),
            'all_markets_3y': no_selected(all3),
            'core_by_side': app.group_metrics(core_selected, 'side'),
            'core_by_quarter': app.group_metrics(core_selected, 'quarter'),
            'core_by_year': yearly(core_selected),
            'all_by_year': yearly(all_selected),
            'by_asset_3y': by_asset,
            'trailing_windows': trailing,
            'cost_stress': stress,
            'external_replication_raw_candidates': len(external),
        }
        print('EXTENDED_RESEARCH_RESULT=' + json.dumps(result, separators=(',', ':'), default=str), flush=True)
    finally:
        mon.cancel()
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
