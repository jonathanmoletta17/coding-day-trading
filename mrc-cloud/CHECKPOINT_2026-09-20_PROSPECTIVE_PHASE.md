# SLOW_TREND_BREAKOUT_V1 — Canonical checkpoint — 2026-09-20

Status: `PROSPECTIVE_EVIDENCE_COLLECTION`

## Canonical verdicts

- D0 code safety: PASS
- D1 private auth/read-only gate: PASS
- D2 no-order dry run: PASS
- D3 minimum OKX Demo roundtrip: PASS
- D4 lifecycle/fault/restart/reconciliation: PASS
- PAPER durable runtime: PASS
- PAPER evidence archive: PASS
- First prospective PAPER trade reconstruction: PASS
- Corpus integrity: PASS
- Scientific evidence floor: `INSUFFICIENT_EVIDENCE`
- Real-money R0: `BLOCKED`

## Current observed corpus

Latest runtime checkpoint after the 2026-09-20 restart:

- decision events: 144
- signals: 2
- PAPER trades: 1
- closed trades: 1
- open trades: 0
- equity: 9,973.929897792597 USDT
- total net R: -1.042804088296126
- scientific status: `INSUFFICIENT_EVIDENCE`
- all closed-trade lineage links: PASS
- durable SQLite probe boot count: 28
- durable SQLite probe id unchanged: `1d586d7c-2190-4d10-8cef-df931f6fe1d4`

## First prospective trade

ETHUSDT LONG:

- entry: 2636.27
- stop: 2599.573666484411
- target: 2709.6626670311775
- gross outcome: -1R
- baseline 6 bps net outcome: -1.042804088296126R
- realized PAPER PnL: -26.070102207403153 USDT
- postmortem: completed
- 1m causal replay continuity: clean
- MFE: approximately +0.988R
- MAE: approximately 0.961R before stop completion

The outcome does not authorize V1 retuning.

## Readiness incident classification

The 2026-09-19 intermittent 503 observations are classified as `OBSERVABILITY_READINESS_TRANSIENT`.

They were isolated fail-closed `/readyz` responses followed by recovery, with no durable-corpus regression or restart evidence in the affected windows. See `READINESS_503_INCIDENT_2026-09-19.md`.

## Evidence preservation hardening

The runtime maintains:

- tamper-evident append-only evidence chain;
- verified SQLite online backups;
- backup manifest hashing and quick-check validation;
- archive health endpoint;
- same-volume backup retention set to 64.

Important limitation: same-volume backups are not full disaster recovery. A platform-managed scheduled volume backup or separately authorized off-volume target is still required.

## Information velocity

`INFORMATION_VELOCITY_V1` was added to the research layer.

It reports, without mutation:

- observed closed-trade pace per day/week/month;
- breakout-candidate pace;
- decision-event pace;
- naive time-to-30 and time-to-100 closed trades at the observed pace;
- explicit sample-confidence label.

These values are descriptive and path-dependent, not forecasts or promotion thresholds. Sparsity must not be repaired by loosening V1.

## Track separation

### EXECUTION_TRACK

Operational exchange execution engineering is validated through D4. Further Demo-order experimentation is not the priority unless a new execution-specific question emerges.

### RESEARCH_TRACK

Continue untouched V1 prospective PAPER collection. Evaluate the precommitted `PAPER_SCIENTIFIC_GATE_V1` only as evidence accumulates.

### CAPITAL_TRACK

R0 remains blocked. No production credentials, production routing, or real-money authorization is in scope.

## Precommitted scientific floor

Human research review eligibility requires all of the following:

- at least 100 closed PAPER trades;
- at least 200 decision events;
- at least 30 observed days;
- positive net expectancy in R;
- moving-block bootstrap 95% lower bound >= 0;
- profit factor >= 1.10;
- maximum drawdown <= 10R;
- at least 30 BTCUSDT closed trades;
- at least 30 ETHUSDT closed trades;
- positive expectancy for each asset;
- clean corpus integrity.

Passing that floor means only `ELIGIBLE_FOR_HUMAN_REVIEW`. It does not enable LIVE execution.

## Next operational work

1. Keep the frozen V1 collection running.
2. Run the daily read-only evidence/scientific/velocity cron.
3. Preserve and verify the evidence chain and SQLite backups.
4. Add off-volume/platform-native disaster recovery when a supported backup control is available and explicitly configured.
5. Review every new closed trade descriptively without modifying V1.
6. Reassess economics at meaningful sample accumulation points, not after individual wins/losses.

Canonical rule remains:

`OBSERVE -> VERIFY INTEGRITY -> ACCUMULATE -> DESCRIBE -> REVIEW`
