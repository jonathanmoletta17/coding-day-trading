# POST-EVIDENCE-HARDENING CHECKPOINT — 2026-09-17

Strategy: `SLOW_TREND_BREAKOUT_V1`

Phase: `PROSPECTIVE_EVIDENCE_COLLECTION`

This checkpoint follows the D0–D4 Demo execution checkpoint and records the promotion of the prospective evidence layer.

## Canonical verdicts

- `D0_CODE_SAFETY = PASS`
- `D1_AUTH_READ_ONLY = PASS`
- `D2_NO_ORDER_DRY_RUN = PASS`
- `D3_MINIMUM_DEMO_ROUNDTRIP = PASS`
- `D4_LIFECYCLE_FAULT_RESTART = PASS`
- `PAPER_RELEASE_OBSERVABILITY_HARDENING = PASS`
- `PAPER_DURABILITY_CONTINUITY = PASS`
- `FORWARD_EVIDENCE_GATE_CONTINUOUS = PASS`
- `FORWARD_EVIDENCE_CROSS_ENDPOINT_PARITY = PASS`
- `PAPER_CORPUS_INTEGRITY = PASS`
- `PROSPECTIVE_ECONOMIC_SAMPLE = N0_COLLECTING`
- `REAL_MONEY_R0 = BLOCKED`

## Active PAPER release

Pinned SHA:

`de7a2d08a25bd78de66c2c1bd3f72056451ba435`

Relative to the prior active SHA `132f3e939c8074dff084f4e56049754f9030af6f`, this release changes observability only.

It adds:

- `slow_evidence_v1.py`
- `/api/evidence`
- evidence-quality summary inside `/api/audit`
- evidence-integrity field in `/readyz`
- read-only evidence tests

It does not modify:

- EMA logic
- Donchian logic
- ATR logic
- risk sizing
- stop/target behavior
- 72h max hold
- daily loss lock
- one-global-position policy
- 6 bps official PAPER baseline

## Promotion evidence

Isolated candidate validation on Railway:

- core engine: `24/24 PASS`
- restart replay: `3/3 PASS`
- Demo execution adapter: `12/12 PASS`
- Demo diagnostic fail-closed: `1/1 PASS`
- cost sensitivity: PASS, non-mutating
- prospective evidence module: `5/5 PASS`, read-only

Production boot after promotion:

- core engine: `24/24 PASS`
- cost sensitivity: PASS, non-mutating
- evidence module: `5/5 PASS`, read-only
- durability probe boot count: `14`
- durability probe ID unchanged: `1d586d7c-2190-4d10-8cef-df931f6fe1d4`
- SQLite path unchanged: `/data/mrc_slow_staging_v3.sqlite3`
- healthcheck: 200

This establishes continuity of the same durable PAPER corpus through the observability release.

## Continuous forward evidence gate

Runtime service: `mrc-research-run`

The earlier one-shot gate was replaced with a periodic read-only collector.

Current validation suite:

`FORWARD_EVIDENCE_TESTS_PASS=9`

The gate now checks:

- release pin across all PAPER endpoints
- feed readiness
- durable storage
- coverage-gap state
- cost-policy preservation
- evidence endpoint read-only status
- evidence-integrity status
- cross-endpoint decision/signal/trade/closed/open count parity
- same-release counter monotonicity
- R0 hard block

Each snapshot receives a deterministic SHA-256 evidence fingerprint.

First integrity-bound production snapshot fingerprint:

`a859df208b6cca26e96f3c43f684043d8a1501f2f8454c4c388decfd49ef11ce`

The fingerprint is an audit identity for snapshot content, not a cryptographic signature or authorization token.

## Real prospective corpus at checkpoint

### Global

- decision events: `18`
- distinct hourly closes: `9`
- breakout candidates/signals: `0`
- PAPER trades: `0`
- closed PAPER trades: `0`
- open PAPER trades: `0`
- realized PnL: `0`
- equity: `10000`

### BTCUSDT

- decisions: `9`
- observed slots inside span: `9/9`
- missing slots: `0`
- coverage ratio: `1.0`
- `WAIT_BREAKOUT`: `9`
- trend `DOWN`: `9`
- breakout `NONE`: `9`

### ETHUSDT

- decisions: `9`
- observed slots inside span: `9/9`
- missing slots: `0`
- coverage ratio: `1.0`
- `WAIT_BREAKOUT`: `8`
- `BREAKOUT_WRONG_DIRECTION`: `1`
- trend `DOWN`: `9`
- breakout `NONE`: `8`
- breakout `LONG`: `1`

### Corpus integrity

- unknown symbols: `0`
- unpaired hourly closes: `0`
- historical unpaired closes: `0`
- internal hourly gaps BTC: `0`
- internal hourly gaps ETH: `0`
- trades missing signal references: `0`
- signals without trade: `0`
- open PAPER positions: `0`
- all integrity checks: PASS

## Interpretation of zero trades

The present absence of PAPER trades is now backed by collection-integrity evidence.

It cannot presently be attributed to:

- a missing BTC hourly record
- a missing ETH hourly record
- an internal hourly gap
- an unpaired decision close
- a collector rollback
- a broken signal-to-trade relation

Across the first nine paired hourly closes, the frozen V1 rules simply did not create a qualifying entry.

This is valid forward evidence and must not be repaired by loosening the strategy.

## Cost separation remains intact

- frozen PAPER baseline: `6 bps`
- stress scenario: `10 bps`
- stress scenario: `15 bps`
- first bounded Demo calibration: `10.01 bps`

The Demo calibration remains audit metadata only.

## Current sample state

`sample_state = NO_CLOSED_PROSPECTIVE_TRADES`

`sample_band = N0`

Sample bands are descriptive only and cannot unlock R0.

## Operating policy after this checkpoint

1. Keep V1 parameters frozen.
2. Keep PAPER collection active.
3. Keep Demo automatic execution disabled.
4. Keep Demo kill switch active.
5. Keep production credentials out of scope.
6. Treat any historical coverage gap, count regression or cross-endpoint mismatch as an integrity incident.
7. Do not manufacture trades to accelerate the sample.
8. Review the first naturally closed PAPER trade in detail when it appears.
9. Continue reporting 6/10/15 bps outcomes from the same closed-trade corpus.
10. Keep `R0.status=BLOCKED` regardless of evidence-gate PASS.

## Next research milestone

The next meaningful event is no longer another execution-plumbing test.

It is one of:

- a naturally qualifying PAPER entry
- the first naturally closed PAPER trade
- a prospective corpus-integrity incident
- a meaningful new body of no-trade decision evidence requiring regime description

Until one of those occurs, the correct operation is continued observation of the frozen strategy.
