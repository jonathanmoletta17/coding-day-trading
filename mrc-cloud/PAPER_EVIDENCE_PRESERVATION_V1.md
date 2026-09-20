# PAPER Evidence Preservation V1

Status: ACTIVE CANDIDATE

Scope: `SLOW_TREND_BREAKOUT_V1` prospective PAPER collection only.

This control plane preserves evidence and recovery points. It does not change signals, risk, sizing, stops, targets, cost assumptions, or exchange permissions.

## Canonical layout

- `mrc-cloud/`: deployed PAPER runtime, read-only evidence APIs, archive writer, and volume backups.
- `mrc-research/`: validation, diagnostics, forward gate, and research reports.
- No additional runtime tree is required for this release.

## Tamper-evident evidence archive

`slow_log_probe.py` reads the local sidecar APIs and writes an append-only NDJSON chain to:

`/data/evidence/paper_evidence_chain.ndjson`

Each record contains:

- sequence number;
- UTC capture time;
- event kind;
- previous-record SHA-256;
- payload;
- SHA-256 of the complete canonical record.

The chain is verified before every append. A mismatch produces an incident and prevents a silent continuation from a corrupted head.

Full evidence is stored whenever the meaningful PAPER state changes. An hourly compact heartbeat is stored when the state is unchanged. Collection or endpoint failures are stored as archive incidents when the chain remains writable.

## Consistent SQLite backups

The archive process uses SQLite's online backup API rather than copying live database bytes.

Backups are created:

- on archive-process startup;
- whenever the closed-trade count changes;
- every 24 hours while the service remains active.

Each backup must pass `PRAGMA quick_check`, is hashed with SHA-256, and is registered in a separate append-only manifest chain under `/data/backups`.

Zero-cost mode retains two verified SQLite backup files by default, configurable from one to eight. Rotation is restricted to files matching the exact managed backup prefix. The archive writer runs inside the PAPER sidecar process, avoiding a separate always-on container process.

These copies protect against application-level or SQLite-level corruption and provide point-in-time files on the mounted volume. They do not, by themselves, protect against loss or deletion of the entire Railway volume. A platform-managed scheduled volume backup or a separately authorized off-volume target is still required for full disaster recovery.

## Read-only APIs

- `/api/closed-trade-reviews`: complete closed-trade lineage and cost repricing.
- `/api/scientific-readiness`: precommitted evidence-floor progress.
- `/api/archive-health`: chain, freshness, and verified-backup health.

All endpoints are descriptive and read only.

## Precommitted scientific floor

`PAPER_SCIENTIFIC_GATE_V1` requires all of the following before the corpus can become eligible for a human research review:

- at least 100 closed PAPER trades;
- at least 200 decision events;
- at least 30 observed days;
- positive net expectancy in R;
- 95% lower confidence bound for mean R at or above zero;
- net profit factor at least 1.10;
- maximum drawdown no greater than 10R;
- at least 30 closed trades for BTCUSDT;
- at least 30 closed trades for ETHUSDT;
- positive expectancy for each asset;
- clean corpus integrity.

The confidence interval uses a deterministic circular moving-block percentile bootstrap. The block length is the rounded square root of the sample size, with a minimum of two, to avoid treating sequential trade outcomes as fully independent.

Meeting the floor changes the status only to `ELIGIBLE_FOR_HUMAN_REVIEW`. It never enables real money, never authorizes parameter retuning, and never bypasses production-specific risk, incident, credential, or execution gates.

## Recovery validation

A valid restore candidate must satisfy all of the following before use:

1. SHA-256 matches the manifest.
2. Backup-manifest chain verifies from genesis to head.
3. `PRAGMA quick_check` returns `ok` on a separate restored copy.
4. Decision, signal, trade, and closed-trade counters do not regress relative to the selected recovery point.
5. Trade-to-signal lineage and one-global-position invariants pass.
6. The restored copy is inspected outside the active PAPER database path first.

No automated restore is permitted.

## Operational interpretation

- Archive `PASS`: evidence preservation is currently coherent.
- Scientific `INSUFFICIENT_EVIDENCE`: continue unchanged PAPER observation.
- Scientific `ELIGIBLE_FOR_HUMAN_REVIEW`: begin a separate human review; do not promote automatically.
- Any archive, integrity, release, or backup failure: forward gate fails closed and R0 remains blocked.
