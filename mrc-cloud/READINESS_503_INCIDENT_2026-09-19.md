# Readiness 503 incident analysis — 2026-09-19

Status: CLASSIFIED / DATA INTEGRITY PRESERVED

Scope: `SLOW_TREND_BREAKOUT_V1` prospective PAPER runtime only.

## Finding

The observed HTTP 503 events were isolated `/readyz` fail-closed responses. They were not accompanied by process restarts, counter rollback, database replacement, trade loss, or persistent endpoint failure.

Representative sequence from the Railway deployment active on 2026-09-19:

- 10:00 UTC `/readyz`, `/api/audit`, `/api/cost-sensitivity`, `/api/evidence`: 200
- 10:01 UTC `/readyz`: 503
- 10:02 UTC `/readyz`, `/api/audit`, `/api/cost-sensitivity`, `/api/evidence`: 200

The same single-cycle pattern recurred later. Evidence collection failed closed during the affected refresh and recovered automatically on a subsequent refresh.

## Integrity outcome

Across the incident window:

- decision counters remained monotonic;
- no historical BTC/ETH decision-pair gap was introduced;
- no PAPER trade disappeared;
- durable SQLite remained authoritative;
- no real-money path was enabled;
- the forward evidence gate kept R0 blocked on refresh failure.

## Classification

`OBSERVABILITY_READINESS_TRANSIENT`

This classification does not assert an upstream root cause. A 503 may be produced whenever readiness conditions are temporarily not satisfied, including public-market-data freshness/readiness checks. The available logs do not support calling the event database corruption or a Railway process outage.

## Operating rule

A single transient `/readyz=503` followed by recovery is recorded as an availability incident, not as missing economic evidence, provided the durable corpus later proves:

1. monotonic counters;
2. no historical hourly gaps;
3. clean trade-to-signal lineage;
4. unchanged durable database identity/recovery chain.

Persistent or repeated 503s that cause a historical evidence gap remain fail-closed and require separate incident handling.

No strategy parameter, signal rule, risk rule, or cost assumption is changed by this incident analysis.
