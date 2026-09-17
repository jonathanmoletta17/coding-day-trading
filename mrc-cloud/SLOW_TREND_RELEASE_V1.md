# SLOW_TREND_BREAKOUT_V1 — PAPER Release Manifest

Status: `PAPER_PRIMARY_RUNNING / PROSPECTIVE_AUDIT_ACTIVE / DEMO_D0_PASS / REAL_MONEY_BLOCKED`

## Frozen strategy contract

- Markets: BTC-USDT-SWAP, ETH-USDT-SWAP (OKX public market data)
- Trend: EMA20 vs EMA50 on confirmed 4H candles, max last 120 confirmed bars
- Trigger: confirmed 1H close beyond prior Donchian20
- Donchian excludes the current breakout candle
- ATR: Wilder ATR14 recomputed on the last 40 confirmed 1H bars
- Stop: 1.5 ATR
- Target: 2R (3 ATR from entry)
- Max hold: 72h
- Max chase: 0.50 ATR
- PAPER risk: 0.25% current equity per trade
- PAPER sizing: `qty = risk_usdt / (1.5 * ATR)`; no implicit 1x-notional cap in the research-parity PAPER model
- Daily realized-loss entry lock: 1% of initial PAPER equity, UTC day
- Portfolio: maximum one global open position
- Tie precedence: BTC before ETH on exact same-time tie
- Strict reentry: next signal timestamp must be greater than previous exit timestamp
- Costs: generic 6 bps round trip research/PAPER accounting model
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

Cost sensitivity observed in research:
- 6 bps: +0.051R/trade
- 10 bps: +0.010R/trade
- 15 bps: -0.041R/trade

These are historical research results, not a guarantee of future profitability.

## Runtime release

Pinned PAPER runtime commit:
`54873a834653a491d402c9261a46804f5397844b`

Runtime files are downloaded by exact commit SHA, not by a moving branch.

Current architecture:
- Public control cockpit: `trend_v1:app` on port 8080
- Slow PAPER sidecar: `slow_app_v2:app` on private port 8081
- Slow DB: `/data/mrc_slow_staging_v3.sqlite3`
- Persistent Railway volume: mounted at `/data`
- Slow database filename is isolated from the public control database
- No private exchange API keys are required or used by the slow PAPER runtime

## Causal 1m replay / restart recovery

Open-position recovery no longer depends on the latest 300 one-minute candles.

Runtime behavior:
- short recent windows may use `/api/v5/market/candles`
- longer recovery windows page backwards through `/api/v5/market/history-candles`
- OKX history pages are deduplicated and sorted chronologically
- coverage is verified minute-by-minute, including internal gaps
- replay starts from persisted `last_check_ms`
- replay is bounded by the 72h max-hold deadline
- historical closed bars are evaluated before any current ticker STOP check
- events after the 72h deadline cannot win before the time stop
- on a 1m bar that straddles the exact deadline, STOP remains the conservative outcome when touched; TARGET cannot win after deadline

Live public-data smoke test completed on Railway:
- instrument: BTC-USDT-SWAP
- window: 72h of 1m candles
- bars reconstructed: 4,320
- OKX history pages: 44
- continuity: PASS
- result: `LIVE_72H_REPLAY_PASS`

## Prospective audit

The runtime persists one unique `decision_event` for each genuinely new confirmed 1H close and market. Event identity is deterministic by strategy + symbol + close timestamp, so restart/replay cannot create duplicate audit rows.

Audit endpoint:
`/api/audit`

It reports prospectively observed:
- decision-event count
- breakout-plan count
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

No decisions before activation of this audit are backfilled. This preserves prospective evidence integrity.

## Research ↔ runtime evidence boundary

The strategy layer is kept in parity, but the prospective execution layer is intentionally causal and is not the same historical fill simulator:

- research entry proxy: next 1H open
- PAPER entry: first executable-side quote after confirmed signal (`ask` LONG / `bid` SHORT)
- research ambiguity: STOP wins when stop and target coexist inside one 1H bar
- PAPER: confirmed 1m replay; STOP wins when both coexist inside the same 1m bar
- incomplete current minute: PAPER may trigger protective STOP from bid/ask, but TARGET requires closed causal 1m evidence
- stale-signal guard: PAPER rejects operationally delayed signals older than 20 minutes; this is not a researched alpha filter
- time-stop fill is resolved prospectively from causal 1m runtime data around 72h rather than reusing the historical bar proxy

Full boundary document:
`SLOW_TREND_RESEARCH_RUNTIME_PARITY.md`

Historical and prospective metrics must always be reported separately.

## Validation completed

Core / replay suite:
- `24/24 PASS`

Open-position restart suite:
- `3/3 RESTART REPLAY PASS`
- OPEN trade survives process restart
- persisted `last_check_ms` is reused as replay start
- contiguous replay can deterministically close the recovered trade

Pre-testnet execution adapter suite:
- `12/12 DEMO ADAPTER PASS`
- deterministic <=32-character alphanumeric `clOrdId`
- LIVE/real-money gate hard-blocked
- explicit DEMO enable required
- kill switch enforced
- missing secrets fail closed
- account/instrument verification required
- PAPER base quantity is not reused directly as derivative `sz`
- base quantity converts through `ctVal`, `lotSz`, `minSz`
- unsupported contract metadata fails closed
- net/long-short position-mode payload handling tested
- OKX REST signature generation tested
- `x-simulated-trading: 1` header tested
- ambiguous submission requires query-before-retry

Additional runtime checks:
- BTC feed readiness: PASS
- ETH feed readiness: PASS
- causal confirmed-candle handling: PASS
- 4H incomplete-candle exclusion: PASS
- maximum 120-bar 4H EMA window parity: PASS
- Donchian current-candle exclusion: PASS
- conservative same-1m STOP/TP conflict handling: PASS (STOP wins)
- fresh-boot stale-signal protection: PASS
- deterministic signal identity: PASS
- decision-event idempotency: PASS
- daily-loss lock logic: PASS
- strict reentry rule: PASS
- one-global-position database enforcement: PASS
- first partial-minute contamination guard: PASS
- incomplete-minute STOP-only ticker guard: PASS
- research-parity stop-risk sizing without notional cap: PASS
- store restart persistence: PASS
- persistent Railway volume restart proof: PASS
- runtime reports `durable_storage=true`
- runtime reports exact pinned release SHA
- public port 8080 healthcheck remains healthy while the slow PAPER sidecar runs on 8081

Durability probe:
- probe id: `1d586d7c-2190-4d10-8cef-df931f6fe1d4`
- same probe id survived repeated deployments
- observed persistent boot counter reached at least `10`

## Current prospective evidence

Latest verified audit sample:
- decision events: 4
- breakout candidates: 0
- PAPER trades: 0
- closed trades: 0
- open position: false
- realized PnL: 0
- PAPER equity: 10000
- daily lock: false

Recent durable decisions:
- 13:00 UTC BTC: `WAIT_BREAKOUT`, 4H trend DOWN
- 13:00 UTC ETH: `BREAKOUT_WRONG_DIRECTION`, breakout LONG while 4H trend DOWN
- 14:00 UTC BTC: `WAIT_BREAKOUT`, 4H trend DOWN
- 14:00 UTC ETH: `WAIT_BREAKOUT`, 4H trend DOWN

This sample is operational evidence only; it is far too small for an efficacy conclusion.

## OKX Demo Trading execution readiness

Files prepared but not wired into PAPER runtime:
- `slow_execution_adapter_v1.py`
- `test_slow_execution_adapter_v1.py`
- `slow_okx_demo_diagnostic_v1.py`
- `OKX_DEMO_EXECUTION_RUNBOOK.md`

Demo gate status:
- D0 unauthenticated code/tests: PASS
- D1 authenticated read-only diagnostics: PENDING DEMO CREDENTIALS
- D2 quantity conversion + payload dry-run with live account metadata: PENDING D1
- D3 first tiny Demo Trading order: BLOCKED UNTIL D0-D2 GREEN + EXPLICIT HUMAN ENABLE
- D4 demo lifecycle/restart/reconciliation: PENDING D3
- R0 real money: BLOCKED

Required D1 private checks only:
- OKX server time
- account mode
- position mode
- BTC/ETH SWAP account instrument metadata
- no order submission

Credentials must be entered directly into protected Railway variables; never commit or paste them into source/chat.

## Gates before real-money execution

Real-money execution remains blocked until all of the following are independently validated:

1. Sufficient prospective PAPER sample and time-window replication.
2. Venue-specific fees, spread and slippage measured rather than assumed 6 bps.
3. Legitimate execution venue/server-region compatibility.
4. Demo/testnet authenticated execution validation through D4.
5. Contract-size conversion from coin quantity to venue contract units validated with live demo metadata.
6. Idempotent client order IDs and duplicate-order prevention validated against the venue.
7. Protective order design and behavior validated in Demo Trading.
8. Private order/account stream and reconciliation after reconnect/restart.
9. Kill switch and maximum-loss controls validated under failure scenarios.
10. Secret provisioning through secure environment variables only; never commit or paste exchange secrets into source/chat.
11. Explicit human approval before any separate real-money project phase.

## Rollback

If the slow sidecar causes operational issues, the public control can be run alone with:

`uvicorn trend_v1:app --host 0.0.0.0 --port ${PORT:-8080}`

The slow strategy database is isolated from the control database by filename and should not be deleted during rollback.

## Governance

- `TREND_BREAKOUT_V1`: rejected research control; retained for comparison.
- `SLOW_TREND_BREAKOUT_V1`: PAPER primary candidate with prospective audit active, not LIVE-ready.
- No strategy parameter is to be changed post-result without defining a new challenger/version first.
- Execution-layer changes require documentation and new prospective validation even when strategy-layer rules remain frozen.
- Demo Trading success is execution evidence, not proof of trading edge.
