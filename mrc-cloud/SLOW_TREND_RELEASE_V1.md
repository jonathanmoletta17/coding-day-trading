# SLOW_TREND_BREAKOUT_V1 — PAPER Release Manifest

Status: `PAPER_PRIMARY_RUNNING / PROSPECTIVE_AUDIT_ACTIVE / REAL_MONEY_BLOCKED`

## Frozen strategy contract

- Markets: BTC-USDT-SWAP, ETH-USDT-SWAP (OKX public market data)
- Trend: EMA20 vs EMA50 on confirmed 4H candles
- Trigger: confirmed 1H close beyond prior Donchian20
- Donchian excludes the current breakout candle
- ATR: Wilder ATR14 recomputed on the last 40 confirmed 1H bars
- Stop: 1.5 ATR
- Target: 2R (3 ATR from entry)
- Time stop: 72h
- Max chase: 0.50 ATR
- PAPER risk: 0.25% equity per trade
- Daily realized-loss lock: 1% of initial PAPER equity, UTC day
- Portfolio: maximum one global open position
- Tie precedence: BTC before ETH on exact same-time tie
- Costs: generic 6 bps round trip research/PAPER accounting model
- Same-1m stop/target ambiguity: STOP wins conservatively
- Order-flow / ADX / RSI / ML: not entry gates in this release

## Research evidence (BTC + ETH)

Three-year audit:
- Trades: 905
- Win rate: 37.35%
- Net expectancy: +0.051R/trade
- Profit factor: 1.077
- Total: +46.16R
- Max drawdown: -21.74R
- Bootstrap 95% expectancy interval included zero; edge is not statistically proven.

Latest 365-day audit:
- Trades: 284
- Net expectancy: +0.103R/trade
- Profit factor: 1.159
- Total: +29.24R
- Max drawdown: -19.94R

Cost sensitivity observed in research:
- 6 bps: +0.051R/trade
- 10 bps: +0.010R/trade
- 15 bps: -0.041R/trade

These are historical research results, not a guarantee of future profitability.

## Runtime release

Pinned runtime commit:
`7dd28d81084e026739dc136cccbc8bd9a090e706`

Runtime files are downloaded by exact commit SHA, not by a moving branch.

Current architecture:
- Public control cockpit: `trend_v1:app` on port 8080
- Slow PAPER sidecar: `slow_app_v2:app` on private port 8081
- Slow DB: `/data/mrc_slow_staging_v3.sqlite3`
- Persistent Railway volume: mounted at `/data`
- No private exchange API keys are required or used by the slow PAPER runtime.

## Prospective audit v4

The v4 runtime persists one unique `decision_event` for each genuinely new confirmed 1H close and market. Event identity is deterministic by strategy + symbol + close timestamp, so restart/replay cannot create duplicate audit rows.

The audit endpoint is:
`/api/audit`

It reports prospectively observed:
- decision-event count
- breakout-candidate count
- PAPER trades opened / currently open / closed
- wins and losses
- win rate
- net expectancy in R
- total net R
- net profit factor
- max drawdown in R
- average modeled cost in R
- average gross R
- realized PnL and PAPER equity
- current UTC-day realized PnL
- recent decisions and trades

No decisions before activation of this v4 audit are backfilled. This preserves prospective evidence integrity.

## Validation completed

- Deterministic engine/storage/audit tests: 10/10 PASS
- BTC feed readiness: PASS
- ETH feed readiness: PASS
- Causal confirmed-candle handling: PASS
- 4H incomplete-candle exclusion: PASS
- Donchian current-candle exclusion: PASS
- Conservative same-1m STOP/TP conflict handling: PASS (STOP wins)
- Fresh-boot stale-signal protection: PASS
- One new 1H close = one decision cycle: prospectively observed before v4
- Deterministic signal identity: PASS
- Decision-event idempotency: PASS
- Daily-loss lock logic: PASS
- Store restart persistence: PASS
- Persistent Railway volume restart proof: PASS
  - probe_id remained constant across restarts
  - boot_count observed 1 -> 2 -> 3 -> 4
- `/readyz`: BTC=true, ETH=true, coverage_gap=null
- Persistent runtime reports `durable_storage=true`
- Runtime reports exact pinned release SHA
- Public port 8080 healthcheck remained healthy while the slow PAPER sidecar ran on 8081

Durability probe id:
`1d586d7c-2190-4d10-8cef-df931f6fe1d4`

## Current limitations / gates before authenticated execution

Real-money execution remains blocked until all of the following are independently validated:

1. Sufficient prospective PAPER sample and time-window replication.
2. Venue-specific fees, spread and slippage measured rather than assumed 6 bps.
3. Legitimate execution venue/server-region compatibility.
4. Testnet or equivalent authenticated execution validation.
5. Contract-size conversion from coin quantity to venue contract units.
6. Idempotent client order IDs and duplicate-order prevention.
7. Server-side protective stop/TP where supported.
8. Private order/account stream and reconciliation after reconnect/restart.
9. Kill switch and maximum-loss controls validated under failure scenarios.
10. Secret provisioning through secure environment variables only; never commit or paste exchange secrets into source/chat.

## Rollback

If the slow sidecar causes operational issues, the public control can be run alone with:

`uvicorn trend_v1:app --host 0.0.0.0 --port ${PORT:-8080}`

The slow strategy database is isolated from the control database by filename and should not be deleted during rollback.

## Governance

- `TREND_BREAKOUT_V1`: rejected research control; retained for comparison.
- `SLOW_TREND_BREAKOUT_V1`: PAPER primary candidate with prospective audit active, not LIVE-ready.
- No parameter is to be changed post-result without defining a new challenger/version first.
