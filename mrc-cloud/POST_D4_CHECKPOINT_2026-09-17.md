# POST-D4 CHECKPOINT — 2026-09-17

Strategy: `SLOW_TREND_BREAKOUT_V1`

Purpose: record the operational state after completing OKX Demo gates D0–D4 without modifying the frozen V1 research specification.

## Canonical verdicts

- `D0_CODE_SAFETY = PASS`
- `D1_AUTH_READ_ONLY = PASS`
- `D2_NO_ORDER_DRY_RUN = PASS`
- `D3_MINIMUM_DEMO_ROUNDTRIP = PASS`
- `D4_LIFECYCLE_FAULT_RESTART = PASS`
- `D4_FINAL_READONLY_RECONCILIATION = PASS`
- `FORWARD_PAPER_COLLECTION = ACTIVE`
- `REAL_MONEY_R0 = BLOCKED`

## Final OKX Demo state

Final authenticated no-order readiness after the D4 sequence:

- account level: Futures (`acctLv=2`)
- position mode: `net_mode`
- private SWAP count: 107
- BTC target position: `0`
- BTC pending orders: `0`
- cross leverage: `3x`
- Demo opening execution: disabled
- kill switch: active
- diagnostic-only: active
- D4 arm: cleared
- order submission performed by final readiness: false
- private POST performed by final readiness: false
- real-money execution enabled: false

The legacy readiness Boolean aggregation bug was corrected in commit:

`b825abdddc317a5f2394bd13f6f8008d3fce364a`

After the fix the read-only gate returned `status=PASS` under the same safe exchange state.

## D4 evidence summary

### Safe resting-order lifecycle

Attempt `D4BTC260917A` validated:

- cancel by `ordId`
- cancel by `clOrdId`
- ambiguous acknowledgement recovery through deterministic `clOrdId` lookup
- no blind retry after remote order discovery
- deterministic expired-request rejection
- final flat state

### Restart with pending exchange order

Attempt `D4BTC260917R` validated:

- stage 1 left exactly one owned deep resting order and zero position
- stage 2 was a new Railway process under safe locks
- existing order discovered from exchange state
- no opening POST by recovery process
- order canceled
- final pending=0 / position=0

### Restart with exchange position

Attempt `D4BTC260917P` validated:

- stage 1 opened the minimum `0.01` BTC-SWAP contract
- open fill: `76643.8`
- stage 2 was a new Railway process under safe locks
- exchange position recovered independently of prior process memory
- ownership proven from OKX order history
- no opening POST by recovery process
- only a `reduceOnly` close was allowed
- close fill: `76679.4`
- final pending=0 / position=0

### Partial-fill / idempotency state model

Deterministic test result:

`D4_ORDER_STATE_TEST=PASS partial_fill=true idempotency=true invalid_states_fail_closed=true`

This covers exact remaining quantity, canceled-after-partial evidence retention and fail-closed invalid states without increasing Demo order size merely to manufacture a partial fill.

### Independent final exchange audit

The final read-only D4 audit independently reconciled all expected exchange evidence:

- three D4 safe resting orders: canceled with zero fills
- expired probe: no exchange order evidence
- restart-pending order: canceled with zero fills
- restart-position OPEN: filled with one fill
- restart-position CLOSE: filled with one fill
- position=0
- pending=0
- leverage=3x
- safe locks=true
- real-money=false

## Active PAPER release

Pinned sidecar release:

`132f3e939c8074dff084f4e56049754f9030af6f`

Externally verified from the internal Railway probe:

- BTC feed ready=true
- ETH feed ready=true
- coverage gap=null
- storage backend=SQLite
- durable storage=true
- `/api/audit` available
- `/api/cost-sensitivity` available
- engine tests: `24/24 PASS`
- cost sensitivity test: PASS and non-mutating
- durability boot count reached 13 during the validation sequence

Prospective state at checkpoint:

- decision events: 16
- breakout candidates: 0
- PAPER trades: 0
- closed PAPER trades: 0
- open PAPER position: false
- PAPER equity: 10,000 (unchanged because no PAPER trade has closed)

This absence of PAPER trades is valid evidence: the strategy has not been forced to trade when its frozen rules do not produce a qualifying setup.

## Cost model separation

Keep these four concepts distinct:

1. Frozen PAPER baseline: **6 bps** round trip.
2. Analytical stress scenario: **10 bps**.
3. Analytical stress scenario: **15 bps**.
4. First observed D3 Demo calibration: **10.01 bps** total round-trip cost.

The active PAPER API exposes `demo_calibration_bps=10.01` as audit metadata only.

It does not mutate:

- signal generation
- position sizing
- stop/target rules
- historical PAPER results
- official V1 6 bps baseline

## What is now complete

Execution engineering in Demo has evidence for:

- authenticated POST path
- server-side request expiry
- deterministic client IDs
- order acknowledgement
- market fill reconciliation
- limit resting state
- cancellation by exchange and client IDs
- rejected-order handling
- ambiguous-result query-before-retry policy
- kill-switch recovery semantics
- restart with pending remote order
- restart with existing remote position
- reduce-only recovery flatten
- deterministic partial-fill lifecycle model
- independent final reconciliation

## What remains intentionally incomplete

The project is **not economically validated prospectively yet**.

Current missing evidence is primarily economic, not connectivity-related:

- enough prospective qualifying signals
- enough closed prospective PAPER trades to characterize realized behavior
- prospective expectancy net R
- prospective profit factor
- prospective max drawdown
- prospective cost R
- comparison of modeled 6/10/15 bps outcomes against observed Demo costs across more than one execution
- regime-dependent prospective behavior
- production-specific slippage and operational study

No parameter should be retuned merely because the current prospective sample is small or because the first Demo cost measurement was ~10 bps.

## Current operating policy

Until a separate human approval after sufficient prospective evidence:

- keep `MRC_DEMO_EXECUTION_ENABLED=0`
- keep `MRC_KILL_SWITCH=1`
- keep `MRC_DEMO_DIAGNOSTIC_ONLY=1`
- keep D3/D4 arm variables empty
- continue PAPER forward collection
- preserve V1 parameters
- use Demo execution only for a newly named, deliberately bounded experiment
- do not enable production credentials
- do not enable real-money execution

## Next phase

`PHASE = PROSPECTIVE_EVIDENCE_COLLECTION`

The next engineering focus is observability and evidence quality around the untouched PAPER process, not further execution promotion.
