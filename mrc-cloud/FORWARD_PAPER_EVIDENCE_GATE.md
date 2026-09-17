# Forward PAPER Evidence Gate

Strategy: `SLOW_TREND_BREAKOUT_V1`

Phase: `PROSPECTIVE_EVIDENCE_COLLECTION`

Status: ACTIVE / READ ONLY / R0 BLOCKED

## Purpose

This gate exists after Demo execution gates D0–D4 passed.

Its job is to prevent a category error:

> successful execution plumbing is not the same thing as prospective economic evidence.

The evidence gate is **read only**. It does not use the OKX private API, does not submit exchange orders, does not mutate the PAPER database and cannot promote the system to real money.

Runtime service: `mrc-research-run`

Current gate implementation lineage:

- initial forward gate: `8348cd766a195556b720d6ba9734482304692852`
- continuous refresh + monotonic regression checks: `19a12088eb1df7375eb884337a4188f811874889`
- integrity-bound gate: `c1088091c00959dc297b830fe0587033e9f05bf4`
- integrity test suite: `0ae1955faedf7f30db0867c7b50c32add5858a3a`

Current expected PAPER release:

`de7a2d08a25bd78de66c2c1bd3f72056451ba435`

This PAPER release is observability-only relative to the preceding V1 release. It adds prospective evidence-quality reporting without changing strategy rules, sizing, exits or the official 6 bps baseline.

## Continuous behavior

The gate no longer takes only one boot-time snapshot.

It refreshes the PAPER source periodically and exposes:

- `/healthz` — freshness + gate status
- `/snapshot` — current full evidence snapshot
- `/history` — bounded in-memory progression of snapshot summaries

The in-memory history is not treated as the source of truth. Every snapshot is recomputed from the durable PAPER source.

Each successful snapshot includes a deterministic SHA-256 fingerprint over the release, operational checks, economic evidence and regression state.

## Operational checks

The gate requires all of these to be true before its healthcheck is green:

- PAPER `/readyz` is ready
- BTC feed ready
- ETH feed ready
- no coverage gap
- durable storage
- release SHA matches across readiness, audit, cost and evidence endpoints
- mode remains `PAPER_STAGING`
- 6/10/15 bps cost scenarios are present
- official PAPER baseline remains exactly 6 bps
- Demo calibration metadata is present
- one-global-position invariant remains database-enforced
- PAPER evidence endpoint declares itself read only
- PAPER evidence integrity passes
- decision count agrees between audit and evidence endpoints
- signal count agrees between audit and evidence endpoints
- PAPER trade count agrees between audit and evidence endpoints
- closed trade count agrees between audit and evidence endpoints
- open-position state agrees with the number of open PAPER trades
- decision/signal/trade/closed-trade counters do not regress inside the same pinned release

A PASS here means the prospective evidence collector is operationally coherent.

It does **not** mean the strategy is economically proven.

## PAPER evidence-quality layer

The PAPER sidecar exposes a separate read-only `/api/evidence` endpoint.

It monitors:

- total decision events
- distinct hourly decision closes
- per-symbol decision counts
- first and last observed close per symbol
- expected hourly slots inside the observed span
- missing internal hourly slots
- paired/unpaired BTC and ETH closes
- historical unpaired closes
- action/state/trend/breakout distributions
- signal count
- total/closed/open PAPER trade counts
- signal-to-trade referential integrity
- at-most-one-open-PAPER-trade invariant
- unknown/unexpected symbols

A latest hourly close can be temporarily unpaired while BTC and ETH are being written sequentially. Historical unpaired closes are the actual integrity failure condition.

Coverage ratio refers only to the period between the first and last observed decision for a symbol; it does not claim observation before collection began.

## Current verified state — 2026-09-17

The first integrity-bound production snapshot after promotion returned PASS.

### Corpus

- decision events: `18`
- distinct hourly closes: `9`
- BTC decisions: `9`
- ETH decisions: `9`
- breakout candidates/signals: `0`
- PAPER trades: `0`
- closed PAPER trades: `0`
- open PAPER trades: `0`
- PAPER equity: `10000.0`

### Coverage

BTC:

- observed hourly slots: `9/9`
- missing internal slots: `0`
- coverage inside observed span: `1.0`
- actions: `WAIT_BREAKOUT = 9`
- trend: `DOWN = 9`
- breakout: `NONE = 9`

ETH:

- observed hourly slots: `9/9`
- missing internal slots: `0`
- coverage inside observed span: `1.0`
- actions: `WAIT_BREAKOUT = 8`
- actions: `BREAKOUT_WRONG_DIRECTION = 1`
- trend: `DOWN = 9`
- breakout: `NONE = 8`, `LONG = 1`

Cross-symbol integrity:

- unpaired decision closes: `0`
- historical unpaired closes: `0`
- unknown symbols: `0`
- trades missing signals: `0`
- integrity pass: `true`

This matters because the current zero-trade sample is now distinguishable from a broken collector: the system observed all nine hourly BTC/ETH decision pairs and the frozen strategy did not produce a qualifying trade.

## Current economic state

- `sample_state = NO_CLOSED_PROSPECTIVE_TRADES`
- `sample_band = N0`
- baseline cost: 6 bps
- stress costs: 10 and 15 bps
- Demo calibration metadata: 10.01 bps
- realized PnL: 0
- equity: 10000

Sample bands are descriptive labels only. They are not statistical guarantees or automatic promotion thresholds.

## Counter regression policy

Inside the same pinned release, these durable counters may only stay flat or increase:

- decision events
- breakout candidates/signals
- total PAPER trades
- closed PAPER trades

If one decreases, the gate fails closed and reports `PROSPECTIVE_COUNTER_REGRESSION_DETECTED`.

This protects against database replacement, rollback, corruption or an observability defect being mistaken for normal prospective behavior.

## R0 semantics

The gate always emits:

- `real_money_allowed=false`
- `automatic_promotion_supported=false`
- `R0.status=BLOCKED`

Current block reasons include:

- no closed prospective PAPER trades
- explicit human approval required
- production credentials/account outside current scope
- production-specific risk and incident controls not validated
- production execution/slippage not validated

No future increase in PAPER trade count automatically removes the human approval requirement.

## Metrics to accumulate prospectively

As trades occur naturally under the frozen V1 rules, monitor:

- decision-event count and continuity
- breakout-candidate count
- total PAPER trades
- closed PAPER trades
- open-position state
- win rate
- expectancy net R
- total net R
- profit factor net
- max drawdown R
- average transaction-cost R
- gross R vs net R
- realized PnL/equity
- daily realized PnL
- 6 bps scenario
- 10 bps scenario
- 15 bps scenario
- observed Demo execution calibration across additional bounded experiments only if separately authorized

## Interpretation discipline

Do not:

- force trades to create a sample
- loosen entry rules because the forward sample is sparse
- optimize parameters against the prospective sample while it is being collected
- reinterpret a no-trade period as strategy failure without first checking corpus integrity and market context
- replace the frozen 6 bps baseline with one Demo execution measurement
- promote to R0 because D4 or this evidence gate passes

Do:

- preserve every hourly decision event
- preserve wrong-direction/no-breakout/blocked decisions as evidence
- keep release SHA and cost policy visible in every audit
- separate modeled costs from observed Demo execution costs
- investigate discrepancies before changing V1
- require a separate, versioned research decision before any V2 parameter change

## Current verdict

- Demo execution engineering: **D0–D4 PASS**
- PAPER release: **`de7a2d08...` ACTIVE**
- PAPER collection infrastructure: **PASS**
- PAPER evidence integrity: **PASS**
- Prospectively observed hourly coverage: **18/18 symbol-events across 9 hourly pairs**
- Prospective economic sample: **N0 / COLLECTING**
- Real money: **BLOCKED**
