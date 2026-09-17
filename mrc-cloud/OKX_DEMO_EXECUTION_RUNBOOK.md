# SLOW_TREND_BREAKOUT_V1 — OKX Demo Execution Runbook

Status: **D0–D4 VALIDATED / FORWARD PAPER ACTIVE / R0 BLOCKED**.

Real-money execution remains hard-blocked. D3/D4 validates Demo execution plumbing; it is not authorization to risk production capital.

## Current validated baseline

- Strategy: `SLOW_TREND_BREAKOUT_V1`
- PAPER markets: `BTC-USDT-SWAP`, `ETH-USDT-SWAP`
- Risk per PAPER trade: 0.25%
- Daily realized loss lock: 1% of initial PAPER equity
- One global open position
- Persistent state: durable SQLite under `/data`
- Causal exit replay: confirmed 1m bars with paginated OKX history through the 72h max-hold deadline
- Same-1m stop+target ambiguity: STOP wins
- Deadline-straddling 1m bar: STOP conservative; no post-deadline TARGET
- Official PAPER transaction-cost baseline: 6 bps round trip
- Analytical stress cases: 10 bps and 15 bps
- Observed first Demo calibration: 10.01 bps total round-trip cost
- Active PAPER release: `132f3e939c8074dff084f4e56049754f9030af6f`
- Real-money adapter gate: hard blocked

## Credential policy

Only OKX **Demo Trading** credentials are permitted in the current execution scope.

Credentials must exist only as protected Railway service variables:

- `OKX_DEMO_API_KEY`
- `OKX_DEMO_SECRET_KEY`
- `OKX_DEMO_PASSPHRASE`

Never place credentials in source code, GitHub, issues, documentation, screenshots, logs, tests or chat messages.

Production API credentials remain outside the current scope.

## Validated gate sequence

### D0 — offline/code safety — PASS

Validated:

- engine/replay tests
- restart replay tests
- Demo adapter tests
- fail-closed diagnostics
- causal replay safeguards
- production-money hard block

### D1 — authenticated Demo read-only — PASS

Validated:

- `x-simulated-trading: 1`
- Futures `acctLv=2`
- `net_mode`
- read + trade permission
- private BTC/ETH SWAP visibility
- live linear USDT-settled contract metadata
- 3x cross leverage readability
- initial flat target account

### D2 — no-order dry run — PASS

Validated:

- instrument availability/state
- contract conversion/minimum/lot sizing
- account and position mode
- leverage policy
- deterministic client order IDs
- zero target exposure/pending
- notional cap
- exchange max-size
- Demo balance presence
- no private POST
- real-money blocked

### Safe expired-POST transport probe — PASS

A deliberately expired `POST /api/v5/trade/order` returned OKX item code `50036` and created no order, fill or position.

This proved authenticated Demo POST routing and server-side `expTime` handling before any live Demo execution.

### D3 — minimum Demo market round-trip — PASS

Validated attempt: `D3BTC260917B`.

- opened `0.01` BTC-USDT-SWAP contracts at `76514.8`
- confirmed exchange position `0.01`
- closed with `reduceOnly` at `76514.7`
- independently reconciled both orders and fills
- final position `0`
- final pending `0`
- emergency SAFE cleanup not required
- observed total cost about `10.01 bps`
- all locks restored immediately

The 10.01 bps observation is calibration only. It does not overwrite the frozen 6 bps PAPER baseline.

### D4 — Demo lifecycle/fault/restart validation — PASS

#### D4.1 / D4.5 — idempotency + ambiguous ACK

Validated with a tiny deeply non-marketable limit order:

- submission treated as ambiguous at the local state-machine boundary
- exchange queried by deterministic `clOrdId`
- existing order discovered
- `retry_allowed=false`
- no duplicate opening order
- order canceled
- final flat

#### D4.2 — cancel by exchange `ordId`

PASS. Deep resting order was acknowledged, remained unfilled, canceled by `ordId`, and disappeared with position still zero.

#### D4.3 — cancel by `clOrdId`

PASS. A distinct deep resting order was canceled using its deterministic client order ID; final position/pending `0/0`.

#### D4.4 — rejected order

PASS. Deliberately expired `expTime` produced `sCode=50036`; no order history/fill evidence and no exposure.

#### D4.6 — kill switch recovery semantics

PASS in actual restart tests:

- new opening execution disabled before recovery container
- kill switch active
- diagnostic-only active
- exchange reads/reconciliation still available
- pending-order cancellation permitted
- `reduceOnly` risk-reducing flatten permitted
- no opening submission from recovery process

#### D4.7 — restart with resting exchange order

PASS, attempt `D4BTC260917R`.

Stage 1:

- created one deep resting order (`0.01` contracts)
- confirmed pending=1 and position=0

Stage 2, new Railway process under safe locks:

- discovered existing order by deterministic `clOrdId`
- `opening_post_performed=false`
- canceled existing order
- final pending=0
- final position=0

#### D4.8 — restart with existing exchange position

PASS, attempt `D4BTC260917P`.

Stage 1:

- minimum market open `0.01` BTC-SWAP
- fill `76643.8`
- position confirmed `0.01`

Stage 2, new process under safe locks:

- discovered exchange position independently of prior process memory
- proved ownership using the filled OPEN order in exchange history
- performed no opening POST
- sent only a `reduceOnly` close
- close fill `76679.4`
- final position=0
- final pending=0

#### D4.9 — partial-fill state handling

PASS through deterministic state-machine tests without artificially increasing live order size.

Covered:

- live/unfilled
- partial fill
- live snapshot with nonzero accumulated fill
- filled terminal state
- canceled-after-partial
- exact remaining quantity
- remote order always blocks blind duplicate opening retry
- ambiguous result requires bounded query/reconciliation
- invalid/inconsistent fill states fail closed

Test marker:

`D4_ORDER_STATE_TEST=PASS partial_fill=true idempotency=true invalid_states_fail_closed=true`

An organic Demo partial fill may be retained as supplemental evidence if it occurs naturally. Do not manufacture one by materially increasing size.

## Final D4 independent reconciliation requirement — PASS

After all D4 execution flags were disabled, a separate read-only process must and did verify:

- position=0
- pending=0
- leverage=3x
- kill switch active
- diagnostic-only active
- opening disabled
- D4 arm empty
- all expected canceled resting orders present in exchange history as canceled
- expired request absent from order/fill history
- restart position OPEN/CLOSE both present as filled with fills
- no private POST during final audit
- real-money execution false

This final read-only audit is the authority for D4 completion.

## Post-D4 operating mode

Default runtime state after any armed Demo test:

- `MRC_EXECUTION_MODE=DEMO`
- `MRC_DEMO_EXECUTION_ENABLED=0`
- `MRC_KILL_SWITCH=1`
- `MRC_DEMO_DIAGNOSTIC_ONLY=1`
- D3/D4 arm tokens empty
- no target exchange position
- no target pending orders

Do not leave an armed executor running as a service.

## PAPER release and cost calibration

Active PAPER sidecar is pinned to:

`132f3e939c8074dff084f4e56049754f9030af6f`

Required endpoints:

- `/readyz`
- `/api/audit`
- `/api/cost-sensitivity`

The cost audit must keep these roles distinct:

- 6 bps = frozen PAPER baseline
- 10 bps = stress scenario
- 15 bps = stress scenario
- 10.01 bps = observed D3 Demo calibration metadata

Cost stress calculations must remain non-mutating: they do not alter signals, position management or persisted baseline trade results.

## Current gate after D4 — prospective economic evidence

The next milestone is **not** another order-connectivity gate.

Continue untouched forward PAPER/OOS collection and accumulate enough actual candidate signals and closed PAPER trades to evaluate:

- prospective expectancy net R
- win rate
- profit factor
- max drawdown in R and currency
- average cost R
- gross vs net R
- 6/10/15 bps sensitivity
- regime dependence
- difference between modeled PAPER costs and observed Demo execution costs

Do not retune V1 based on a handful of signals or Demo fills.

## R0 — real money — BLOCKED

D0–D4 PASS does **not** authorize R0.

Before R0 can even be considered, require a separate explicit human decision plus, at minimum:

- sufficient prospective PAPER/OOS economic evidence
- production-specific execution/slippage study
- production credential isolation
- production account-mode/instrument verification
- independent capital/risk budget
- hard daily/position/order limits
- restart/reconciliation controls carried into the production adapter
- monitoring/alerting and incident procedure
- emergency flatten/revoke-key procedure
- audit log/immutable intent IDs
- fresh production-only risk review

Until then:

**REAL MONEY = HARD BLOCKED.**

## Credential and safety hygiene

- Never print secrets.
- Never expose authenticated diagnostics publicly.
- Use protected Railway variables.
- Rotate any credential accidentally exposed.
- Keep Demo and production credentials completely separate.
- Arm Demo execution only for one named attempt at a time.
- Restore kill switch immediately after every attempt.
- Independently reconcile exchange state after every execution/fault test.
- Prefer risk-reducing recovery actions under kill switch; never treat a local timeout as proof an exchange order failed.
