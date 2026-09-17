# Forward PAPER Evidence Gate

Strategy: `SLOW_TREND_BREAKOUT_V1`

Phase: `PROSPECTIVE_EVIDENCE_COLLECTION`

## Purpose

This gate exists after Demo execution gates D0–D4 have passed.

Its job is to prevent a category error:

> successful execution plumbing is not the same thing as prospective economic evidence.

The evidence gate is **read only**. It does not use the OKX private API, does not submit exchange orders, does not mutate the PAPER database and cannot promote the system to real money.

Implementation commit:

`8348cd766a195556b720d6ba9734482304692852`

Runtime service: `mrc-research-run`

Expected PAPER release:

`132f3e939c8074dff084f4e56049754f9030af6f`

## Operational checks

The gate requires all of these to be true before its own healthcheck is green:

- PAPER `/readyz` is ready
- BTC feed ready
- ETH feed ready
- no coverage gap
- durable storage
- release SHA matches the expected pinned release
- mode remains `PAPER_STAGING`
- 6/10/15 bps cost scenarios are present
- official PAPER baseline remains exactly 6 bps
- Demo calibration metadata is present
- one-global-position invariant remains database-enforced

A PASS here means the prospective evidence collector is operationally coherent.

It does **not** mean the strategy is economically proven.

## Current economic state at activation

At activation on 2026-09-17:

- decision events: 16
- breakout candidates: 0
- PAPER trades: 0
- closed PAPER trades: 0
- open PAPER position: false
- PAPER equity: 10,000
- baseline cost: 6 bps
- stress costs: 10 and 15 bps
- Demo calibration: 10.01 bps

Therefore:

`sample_state = NO_CLOSED_PROSPECTIVE_TRADES`

This is not treated as an error. It means the evidence collection phase has started but has not yet produced a closed qualifying trade.

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

- decision event count
- breakout candidate count
- total PAPER trades
- closed PAPER trades
- open position state
- win rate
- expectancy net R
- profit factor net
- max drawdown R
- average transaction-cost R
- gross R vs net R
- realized PnL/equity
- daily realized PnL
- 6 bps scenario
- 10 bps scenario
- 15 bps scenario
- observed Demo execution calibration over multiple bounded executions, if additional Demo experiments are deliberately authorized

## Interpretation discipline

Do not:

- force trades to create a sample
- loosen entry rules because the forward sample is sparse
- optimize parameters against the prospective sample while it is still being collected
- reinterpret no-trade periods as strategy failure without market/context analysis
- replace the frozen 6 bps baseline with one Demo execution measurement
- promote to R0 because D4 passed

Do:

- preserve each hourly decision event
- preserve rejected/wrong-direction/no-breakout decisions as evidence
- keep release SHA and cost policy visible in every audit
- separate modeled cost scenarios from observed execution measurements
- investigate discrepancies before changing V1
- require a separate research decision before any V2 parameter change

## Current verdict

- Demo execution engineering: **D0–D4 PASS**
- PAPER collection infrastructure: **PASS**
- Prospective economic sample: **INSUFFICIENT / COLLECTING**
- Real money: **BLOCKED**
