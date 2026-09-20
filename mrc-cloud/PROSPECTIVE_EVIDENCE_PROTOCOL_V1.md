# SLOW_TREND_BREAKOUT_V1 — Prospective Evidence Protocol V1

Status: ACTIVE

Phase: `PROSPECTIVE_EVIDENCE_COLLECTION`

This protocol governs how forward PAPER evidence is collected and interpreted after OKX Demo execution gates D0–D4 passed.

It does **not** modify the frozen strategy rules and it does not authorize real-money execution.

## 1. Purpose

The purpose of the forward phase is to answer a narrower question than the historical research phase:

> What does the untouched V1 strategy actually do when observed prospectively, decision by decision, under a fixed implementation and fixed cost assumptions?

Successful exchange connectivity, Demo fills, restart recovery and cancellation behavior are operational evidence. They are not evidence of an economic edge.

## 2. Frozen strategy surface

During this protocol, the following are frozen unless a separately named V2 research process is opened:

- 4H EMA20/EMA50 trend logic
- 1H Donchian20 breakout logic
- ATR14 risk geometry
- risk per PAPER trade: 0.25%
- daily realized loss lock: 1%
- one global open position
- strict post-exit re-entry ordering
- maximum hold: 72h
- causal 1m exit replay rules
- STOP-first treatment of same-bar stop/target ambiguity
- official PAPER round-trip baseline: 6 bps

10 bps and 15 bps remain analytical stress scenarios only.

The first observed bounded Demo calibration, 10.01 bps, remains execution metadata only.

## 3. Source of truth

The durable PAPER SQLite database under `/data` is the prospective source of truth for:

- `decision_events`
- qualifying `signals`
- PAPER `trades`
- persistent runtime watermarks

The external evidence gate is read-only and recomputes from this durable source through the PAPER audit APIs.

A restart of the evidence-gate service must not erase or reset prospective PAPER evidence.

The PAPER service also maintains a tamper-evident evidence chain and verified SQLite backup set on the mounted volume. These are recovery and audit controls, not an alternate economic source of truth. The full design and its same-volume limitation are documented in `PAPER_EVIDENCE_PRESERVATION_V1.md`.

## 4. Every decision counts as evidence

The forward corpus includes more than trades.

The following states are evidence and must be preserved:

- no breakout
- breakout in the wrong trend direction
- candidate blocked by risk controls
- candidate blocked by one-global-position occupancy
- candidate blocked by causal/re-entry rules
- qualifying PAPER open
- PAPER exit
- data error or coverage gap

A low trade count is not repaired by loosening filters. It is a property of the frozen strategy during the observed market path.

## 5. Coverage and integrity requirements

Prospective economic metrics are interpretable only when the observation process is itself coherent.

The read-only evidence layer monitors:

- decision-event counts by symbol
- first and last observed hourly close per symbol
- expected hourly slots inside the actually observed span
- missing internal hourly slots
- paired BTC/ETH decision closes
- historical unpaired closes
- state/action/trend/breakout distributions
- signal count
- trade count
- closed/open trade counts
- trade-to-signal referential integrity
- at-most-one-open-PAPER-position invariant

A currently writing latest hourly pair may temporarily appear unpaired. Historical unpaired closes are treated as an integrity failure until explained or repaired from source evidence.

Coverage calculations make no claim about time before prospective collection began.

## 6. Counter monotonicity

Within the same pinned release and the same durable PAPER corpus, these counters must never decrease:

- decision events
- breakout candidates/signals
- total PAPER trades
- closed PAPER trades

A decrease is treated as evidence of rollback, database replacement, corruption or an observability defect. The forward evidence gate must fail closed and R0 remains blocked.

A deliberate release boundary does not silently reset the corpus. Release changes require an explicit checkpoint explaining whether the same durable database remains authoritative.

## 7. Economic metrics

Once closed PAPER trades occur naturally, track at minimum:

- closed trade count
- wins/losses
- win rate
- expectancy net R
- total net R
- profit factor net
- maximum drawdown R
- average transaction cost R
- average gross R
- realized PnL
- equity
- daily realized PnL

For the same closed-trade corpus, recompute without mutation under:

- baseline 6 bps
- stress 10 bps
- stress 15 bps

Observed Demo execution costs remain a separate calibration series rather than a retroactive rewrite of the research baseline.

## 8. Sample-size labels are descriptive only

The evidence gate may display sample-count bands such as:

- `N0`
- `N1_9`
- `N10_29`
- `N30_49`
- `N50_PLUS`

These labels exist only to make the amount of observed data explicit.

They are **not** statistical guarantees, approval thresholds, position-sizing rules or automatic promotion criteria.

No sample count automatically unlocks R0.

## 8.1 Precommitted scientific floor

Before the corpus can be labelled eligible for a human research review, all precommitted `PAPER_SCIENTIFIC_GATE_V1` conditions must pass:

- at least 100 closed PAPER trades and 200 decision events;
- at least 30 observed days;
- positive net expectancy;
- moving-block bootstrap 95% lower bound at or above zero;
- profit factor at least 1.10;
- maximum drawdown no greater than 10R;
- at least 30 closed trades and positive expectancy for each of BTCUSDT and ETHUSDT;
- clean corpus integrity.

This floor is deliberately fixed before a material sample accumulates. Passing it means only `ELIGIBLE_FOR_HUMAN_REVIEW`; it does not authorize LIVE, automatic promotion, or V1 parameter changes.

## 9. No prospective overfitting

During V1 collection, do not modify the strategy merely because:

- signals are sparse
- the first few trades lose
- the first few trades win
- the observed Demo cost differs from 6 bps
- one market regime dominates the early sample
- a backtest variant looks better after seeing forward outcomes

Any parameter change creates a new research hypothesis and must be separated into a new version rather than rewriting the meaning of the existing V1 forward sample.

## 10. Review events

The following are appropriate reasons to perform a human research review, not automatic promotion events:

- the first closed prospective PAPER trade
- a new integrity failure or coverage gap
- a change of pinned PAPER release
- a material divergence between 6/10/15 bps sensitivity
- a newly observed bounded Demo execution cost
- a meaningful accumulation of additional closed trades
- a prolonged no-trade period requiring descriptive regime analysis

A review may conclude that more evidence is needed.

## 11. R0 remains separate

Even if prospective PAPER economics eventually look favorable, R0 remains a separate gate.

The forward evidence collector always preserves:

- `real_money_allowed=false`
- `automatic_promotion_supported=false`
- `R0.status=BLOCKED`

A future R0 discussion would still require a separate human decision and production-specific work, including credential isolation, incident controls, execution/slippage study and a new risk review.

## 12. Current release architecture

PAPER strategy process:

- exchange access: public market data only
- state: durable PAPER SQLite
- execution: simulated local PAPER only

Forward evidence gate:

- PAPER API access: read only
- PAPER database mutation: false
- OKX private API use: false
- exchange order capability: none
- automatic R0 promotion: impossible by policy and output contract

## 13. Interpretation hierarchy

When interpreting forward results, use this order:

1. **Integrity:** was the observation corpus captured coherently?
2. **Completeness:** are there unexplained gaps or rollback symptoms?
3. **Execution assumptions:** what cost/slippage model is being used?
4. **Economic description:** what happened to the frozen strategy?
5. **Uncertainty:** how limited is the observed corpus?
6. **Research decision:** continue observing, investigate an anomaly, or open a separately versioned hypothesis.

Do not reverse this hierarchy by optimizing economics first and checking data integrity afterward.

## 14. Canonical operating rule

`OBSERVE -> VERIFY INTEGRITY -> ACCUMULATE -> DESCRIBE -> REVIEW`

Not:

`OBSERVE -> RETUNE -> BACKFILL -> PROMOTE`
