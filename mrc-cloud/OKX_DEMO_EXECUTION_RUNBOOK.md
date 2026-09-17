# SLOW_TREND_BREAKOUT_V1 — OKX Demo Execution Runbook

Status: PRE-TESTNET / DEMO ONLY. Real-money execution is hard-blocked in code.

## Current validated baseline

- Strategy: `SLOW_TREND_BREAKOUT_V1`
- PAPER markets: `BTC-USDT-SWAP`, `ETH-USDT-SWAP`
- Risk per PAPER trade: 0.25%
- Daily realized loss lock: 1% of initial PAPER equity
- One global open position
- Persistent state: SQLite under `/data`
- Causal exit replay: confirmed 1m bars with paginated OKX history up to the 72h max-hold deadline
- Same-1m stop+target ambiguity: STOP wins
- Deadline-straddling 1m bar: STOP remains conservative; TARGET cannot win after the 72h deadline
- Real-money adapter gate: permanently blocked in `slow_execution_adapter_v1.py`

## Required human action before authenticated demo diagnostics

Create an OKX **Demo Trading** API key in the OKX Demo Trading area. Use demo credentials only.

Do not paste credentials into ChatGPT, GitHub, source code, issues, logs, or documentation.

Enter them directly as protected Railway service variables:

- `OKX_DEMO_API_KEY`
- `OKX_DEMO_SECRET_KEY`
- `OKX_DEMO_PASSPHRASE`

Do not create or add production API credentials at this stage.

## Gate sequence

### Gate D0 — unauthenticated code/tests

Required:

- core/replay test suite PASS
- restart-with-open-position test PASS
- demo adapter fail-closed test PASS
- 72h live public replay smoke PASS

No credentials required. No order submission.

### Gate D1 — authenticated demo diagnostics, READ ONLY

Run `slow_okx_demo_diagnostic_v1.py` in a non-public staging job.

It may call only:

- `GET /api/v5/public/time`
- `GET /api/v5/account/config`
- `GET /api/v5/account/instruments`

Expected output must confirm:

- request is Demo Trading (`x-simulated-trading: 1`)
- clock drift acceptable
- account mode identified
- position mode identified (`net_mode` or `long_short_mode`)
- BTC/ETH SWAP instruments are live
- `ctType`, `ctVal`, `ctValCcy`, `lotSz`, `minSz` captured
- `order_submission_performed=false`

No order may be placed at D1.

### Gate D2 — conversion + payload dry run

For a real PAPER candidate, convert PAPER base quantity into OKX contracts using live instrument metadata.

Fail closed when:

- instrument is not live
- contract type is unsupported
- `ctValCcy` cannot be mapped safely to the PAPER base quantity
- rounded contract quantity is below `minSz`
- quantity is not a valid multiple of `lotSz`
- account/position mode has not been verified

Generate deterministic `clOrdId`. Repeated attempts for the same signal must produce the same ID.

No order may be submitted at D2.

### Gate D3 — first Demo Trading order

Only after D0–D2 are green and a human explicitly enables Demo Trading execution.

Required controls:

- `mode=DEMO`
- explicit demo enable flag
- kill switch OFF
- demo secrets present
- verified account mode
- verified instrument metadata
- deterministic `clOrdId`
- request expiration policy
- `x-simulated-trading: 1`
- query-before-retry after any ambiguous timeout

First action should be one tiny demo order followed by reconciliation and cancellation/closure as applicable. This is simulated money only.

### Gate D4 — demo lifecycle validation

Must demonstrate:

- submit acknowledgement
- duplicate submission prevention
- partial-fill handling
- filled-state reconciliation
- cancel-by-order-id/client-order-id
- process restart while exchange order/position exists
- exchange-to-local state reconciliation after restart
- kill switch behavior
- rejected-order behavior
- network timeout behavior

### Gate R0 — real money

Blocked.

No promotion to real money based solely on successful Demo Trading execution. Prospective PAPER economic evidence and a separate human approval gate are required.

## Credential hygiene

- Never print secrets.
- Never expose authenticated diagnostic endpoints publicly.
- Use Railway protected variables.
- Rotate any credential accidentally exposed.
- Keep demo and production keys completely separate.
- Production credentials are outside the current approved scope.
