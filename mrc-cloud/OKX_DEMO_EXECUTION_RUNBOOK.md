# SLOW_TREND_BREAKOUT_V1 — OKX Demo Execution Runbook

Status: **D3 VALIDATED / D4 IN PROGRESS / DEMO ONLY**. Real-money execution remains hard-blocked.

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
- Official PAPER cost baseline: 6 bps round trip
- Operational cost stress scenarios: 10 bps and 15 bps
- Real-money adapter gate: permanently blocked in `slow_execution_adapter_v1.py`

## Credential policy

Only OKX **Demo Trading** credentials are permitted in the current execution scope.

Credentials must exist only as protected Railway service variables:

- `OKX_DEMO_API_KEY`
- `OKX_DEMO_SECRET_KEY`
- `OKX_DEMO_PASSPHRASE`

Never paste credentials into ChatGPT, GitHub, source code, issues, logs, documentation, screenshots or test fixtures.

Production API credentials are explicitly outside the current scope.

## Gate sequence

### Gate D0 — unauthenticated code/tests — PASS

Required and validated:

- core/replay test suite PASS
- restart-with-open-position test PASS
- demo adapter fail-closed test PASS
- causal replay safeguards PASS
- production-money route blocked

### Gate D1 — authenticated Demo diagnostics, READ ONLY — PASS

Validated Demo state:

- `x-simulated-trading: 1`
- `acctLv=2` Futures mode
- `net_mode`
- read + trade permission
- private BTC/ETH SWAP visibility
- live linear USDT-settled instruments
- contract metadata captured
- cross leverage readable and observed at 3x
- zero target positions and zero pending target orders before execution testing

No order is allowed at D1.

### Gate D2 — conversion + payload dry run — PASS

Fail-closed checks include:

- target instrument live/private available
- supported linear contract
- safe `ctVal` / base-quantity mapping
- valid `minSz` and `lotSz`
- verified account/position mode
- leverage state explicitly observed
- deterministic `clOrdId`
- target account flat
- no pending target order
- notional cap
- real-money route blocked

The final minimum D3 BTC size was `0.01` contracts, approximately US$7.65 notional at the test price.

No order is submitted at D2.

### Safe POST transport probe — PASS

Before D3, `POST /api/v5/trade/order` was authenticated using a deliberately expired `expTime`.

Expected/observed behavior:

- OKX received/authenticated the Demo POST
- request rejected with expiry code `50036`
- no live order created
- no fill
- no position
- no pending order

This proves POST transport/authentication while preserving zero exposure.

### Gate D3 — first Demo Trading round-trip — PASS

Validated attempt: `D3BTC260917B`.

Controls:

- `mode=DEMO`
- explicit one-shot arm token
- kill switch temporarily OFF only for the armed run
- diagnostic-only temporarily OFF only for the armed run
- Demo credentials present
- verified Futures/net mode
- verified BTC metadata
- 3x cross leverage observed; leverage was not mutated
- deterministic client order IDs
- expiring order requests
- query/reconciliation logic
- `x-simulated-trading: 1`

Observed lifecycle:

1. Open `0.01` BTC-USDT-SWAP contracts at average `76514.8`.
2. Confirm exchange position became `0.01`.
3. Submit `reduceOnly` close for `0.01`.
4. Close filled at average `76514.7`.
5. Reconcile final position to exactly `0`.
6. Independently retrieve both orders and both fills from OKX Demo history.
7. Emergency SAFE cleanup was not required.
8. Restore all safety locks immediately.
9. Run D2 again and prove flat/zero-pending state.

Observed total Demo round-trip transaction cost was about `10.01 bps` on the tiny test notional. This is calibration evidence only and does not change the V1 6 bps research baseline.

## Gate D4 — Demo lifecycle and fault validation — CURRENT GATE

D4 must be completed before any discussion of a broader Demo executor and long before R0.

Every D4 scenario must start from and return to:

- BTC/ETH target position = 0
- target pending orders = 0
- Demo-only credentials
- minimum practical test size
- bounded notional
- deterministic unique test ID
- final independent reconciliation

### D4.1 — duplicate/idempotency behavior

Validate both layers:

1. Local layer must refuse a second submission for an already-resolved deterministic intent.
2. Exchange layer must be queried by `clOrdId` before any retry after an ambiguous result.

Do not intentionally create duplicate market exposure merely to test exchange rejection. Prefer a resting/cancelable order or a deliberately non-executable probe where possible.

### D4.2 — resting order + cancel by `ordId`

Use a tiny Demo limit order far enough from market to remain resting.

Required proof:

- order acknowledged
- appears in pending orders
- cancel request by exchange `ordId` acknowledged
- final order state canceled
- pending order disappears
- no fill / no position

### D4.3 — resting order + cancel by `clOrdId`

Repeat with a distinct tiny resting order and cancel using deterministic `clOrdId`.

Required final state remains flat with no pending order.

### D4.4 — rejected order behavior

Use a request that is safely invalid and cannot create exposure, such as:

- deliberately expired `expTime`, or
- quantity below exchange minimum where deterministic rejection is verified.

Required:

- error captured structurally
- no retry storm
- no local position creation
- reconciliation confirms no exchange-side order/position

### D4.5 — ambiguous network timeout / query-before-retry

Test the local state machine without creating uncontrolled exposure.

Required behavior after a simulated/forced ambiguous client timeout:

1. mark submission result UNKNOWN, never FAILED-by-assumption;
2. query OKX by deterministic `clOrdId`;
3. if found, reconcile it and never resubmit;
4. if absent after bounded reconciliation, only then allow a controlled retry according to policy;
5. final state independently checked.

### D4.6 — kill switch

When kill switch is active:

- new opening submissions are blocked before POST;
- reconciliation/read operations remain available;
- reduce-only emergency flattening policy remains separately controlled;
- no production path can be enabled.

### D4.7 — restart reconciliation with resting exchange order

Preferred first restart test because it avoids intentionally carrying market exposure.

Procedure:

1. create tiny non-marketable Demo limit order;
2. confirm it is pending;
3. restart the reconciliation process/service;
4. process must discover the existing order from exchange state rather than submit another order;
5. cancel/reconcile it;
6. prove final pending=0 and position=0.

### D4.8 — restart reconciliation with exchange position

Only after D4.7 is proven.

If performed, exposure must be minimum-size Demo only, with an independent emergency flatten path prepared before opening.

Required:

- open tiny Demo position;
- restart local executor/reconciler;
- restarted process discovers the existing exchange position;
- no duplicate opening order;
- explicit reduce-only flatten;
- final independent flat-state proof.

### D4.9 — partial-fill handling

Partial fills are timing/liquidity dependent and must not be manufactured by unsafe market manipulation.

Two valid evidence paths:

- deterministic unit/integration tests covering partial-fill state transitions; and
- an organically observed Demo partial fill, if one occurs during bounded resting-order tests.

Do not increase order size materially just to force a partial fill.

## Forward PAPER evidence requirement

D3/D4 validates execution plumbing, not economic edge.

The strategy must continue prospective PAPER collection with:

- original 6 bps baseline retained
- 10 bps and 15 bps sensitivity reported analytically
- realized/observed Demo costs tracked separately
- no parameter retuning from one or a small number of Demo executions
- no promotion based solely on historical backtest or execution connectivity

## Gate R0 — real money — BLOCKED

No promotion to real money based solely on successful Demo execution.

A separate human decision, prospective economic evidence, production-specific operational controls, production credential isolation and a new risk review would all be required before R0 could even be considered.

## Credential and safety hygiene

- Never print secrets.
- Never expose authenticated diagnostic endpoints publicly.
- Use Railway protected variables.
- Rotate any credential accidentally exposed.
- Keep Demo and production keys completely separate.
- Keep execution flags disabled except during a single explicitly armed Demo test.
- Restore kill switch immediately after each armed scenario.
- Independently reconcile exchange state after every execution/fault test.
