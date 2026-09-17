# SLOW_TREND_BREAKOUT_V1 — Research ↔ PAPER Runtime Parity

Purpose: prevent historical research evidence from being mixed with prospective PAPER execution evidence.

## Strategy-layer parity

The following rules are frozen and matched by the PAPER runtime:

- universe: BTC-USDT-SWAP then ETH-USDT-SWAP
- confirmed 1H Donchian20 breakout, excluding the current signal candle from the channel
- confirmed 4H EMA20/EMA50 trend, maximum last 120 confirmed 4H bars
- Wilder ATR14 recomputed over the last 40 confirmed 1H bars
- stop distance: 1.5 ATR
- target: 2R = 3 ATR
- max chase: 0.50 ATR
- risk sizing: `risk_usdt = current_equity * 0.0025`, `qty = risk_usdt / (1.5 * ATR)`
- generic round-trip accounting cost: 6 bps
- maximum one global open position
- deterministic BTC priority before ETH for an exact same decision time
- strict next eligible signal timestamp must be greater than the prior exit timestamp
- daily realized-loss entry lock: 1% of initial PAPER equity, UTC day
- time-hold intent: 72h
- no ADX/RSI/ML/order-flow gate in this release

## Deliberate execution-layer differences

These are not strategy optimizations and must not be used to rewrite historical research results.

1. **Entry price proxy**
   - Historical research: next 1H bar open.
   - Prospective PAPER: first available executable-side quote after the confirmed 1H signal (`ask` for LONG, `bid` for SHORT).
   - The same 0.50 ATR chase ceiling still applies.

2. **Intrabar exit resolution**
   - Historical research: 1H OHLC path is unknown; if stop and target are both touched in the same 1H bar, STOP wins.
   - Prospective PAPER: confirmed 1m bars are replayed causally. If stop and target are both touched in the same 1m bar, STOP wins. A target touched in an earlier confirmed minute may therefore precede a later stop within the same hour.

3. **Incomplete current minute**
   - PAPER may use current bid/ask only to trigger a protective STOP.
   - PAPER does not declare TARGET from an incomplete minute; target requires causal closed-1m evidence.

4. **Signal-age guard**
   - Historical research naturally enters at its next-bar proxy.
   - PAPER rejects a signal older than 20 minutes after downtime/operational delay. This is an operational stale-signal guard, not a researched alpha filter.

5. **Time-stop execution price**
   - Historical research uses its bar-based time-exit proxy.
   - PAPER resolves the 72h time stop using causal runtime data around the deadline. This is an execution-layer approximation and must be evaluated prospectively.

## Evidence policy

Historical research and prospective PAPER must be reported in separate blocks.

Historical metrics remain the previously frozen research results. Prospective PAPER metrics are generated only from durable runtime records after audit activation. No prospective event is backfilled from historical data.

A future change to any strategy-layer rule requires a new challenger/version. A change limited to execution mechanics must be documented as a new execution profile and validated prospectively before authenticated execution is considered.

## Current safety boundary

`SLOW_TREND_BREAKOUT_V1` remains PAPER-only. No exchange private credentials, authenticated orders, or real-money execution are authorized by this document.
