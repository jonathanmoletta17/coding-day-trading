# First prospective PAPER trade postmortem

Generated on 2026-09-20. This report is descriptive, read-only, and does not authorize parameter changes or real-money execution.

## Executive result

- Strategy: `SLOW_TREND_BREAKOUT_V1` (frozen).
- Trade: ETHUSDT LONG, signal `2fd810394f8fb7c770077b92`.
- Open: 2026-09-18 20:00:01.103 UTC at 2636.27.
- Close: 2026-09-20 02:44:23.670 UTC at the 2599.573666 stop.
- Duration: 30.7396 hours.
- Gross result: -1.000000R.
- Net result at the frozen 6 bps model: -1.042804R / -26.070102 USDT.
- Cost stress: -1.071340R at 10 bps and -1.107010R at 15 bps.
- Exit mechanism: current-ticker stop. The non-minute-aligned close timestamp distinguishes it from the closed-1m replay exit path.

One losing trade is not a statistically valid basis for retuning. The strategy remains frozen and PAPER-only.

## Path reconstruction

The reconstruction fetched 1,843 fully closed ETHUSDT one-minute bars from OKX in 19 pages. There were no missing minutes between the first eligible bar after entry and the last fully closed bar before the recorded exit.

- Best observed price: 2672.54 at 2026-09-19 17:18 UTC.
- MFE: +0.988382R.
- Worst fully closed-bar price before the ticker exit: 2601.00 at 2026-09-19 01:20 UTC.
- MAE before ticker exit: 0.961131R.
- Maximum target progress: 49.4191%.
- Remaining distance to target at the best price: 37.122667 USDT.

The 4-hour trend classification stayed `UP` throughout the position. Hourly ATR(14) contracted from 24.464222 at entry to a minimum of 16.299049 before the exit. This describes the observed trade path; it is not a recommendation to change stops, targets, or filters.

## Lineage and integrity

All required links passed:

- the signal exists;
- the decision exists at the signal close;
- trade and signal identifiers match;
- symbol and side match;
- repricing at the frozen 6 bps baseline matches the stored result;
- the PAPER database was not mutated;
- no private exchange API was used.

The prospective corpus after the close contains 126 decisions, two breakout candidates, one PAPER trade, one closed trade, and no open position. Per-symbol hourly coverage is complete inside the observed span, and the evidence integrity gate is `PASS`.

## Blocked BTC candidate (counterfactual only)

The second signal was correctly blocked by the one-global-position rule while ETH was open. A read-only reconstruction, explicitly not an official PAPER result, assumed a BTCUSDT LONG entry at 81616.90 on 2026-09-19 01:00:07 UTC, with stop 80852.193672 and target 83146.312656.

- Counterfactual outcome: STOP at 2026-09-19 21:21 UTC.
- MFE: +0.409438R.
- MAE before exit: 1.983637R.
- Target progress: 20.4719%.
- Coverage: 1,603 one-minute bars with zero missing minutes.

This validates the blocked-candidate audit trail without converting it into an executed trade or changing the one-position rule.

## Intermittent 503 investigation

Historical `/readyz` failures were short and self-recovering, normally followed by a `PASS` on the next one-minute poll. Audit, evidence, and cost endpoints continued to return valid snapshots around the events, and no corpus gaps or monotonicity regressions appeared.

Resource exhaustion is not supported by the 72-hour service metrics: average CPU was 0.0059 with a 0.0634 maximum; average memory was 0.0819 GB with a 0.1916 GB maximum against a 1 GB limit; disk use stayed below 0.054 GB.

In release `119a1e9a88da76ff31130804340bb0655c97d990`, `/readyz` returned 503 only for a symbol-feed readiness failure or a one-minute coverage gap. The old monitor retained only the generic HTTP 503 exception, so the exact historical branch cannot be recovered. The evidence supports classification as a transient feed/readiness event, not a process crash or resource-capacity failure. A separate startup example showed the sidecar return 503 for approximately one second and then 200 while initialization completed.

## Observability release

Read-only release `c4ce29173d08b3c5a8e030b1bd6de361068ee2fa` was validated in isolation and promoted after:

- 24/24 core tests passed;
- 3/3 restart/replay tests passed;
- 12/12 Demo adapter tests passed;
- 1/1 fail-closed Demo diagnostic passed;
- cost-sensitivity tests passed;
- 8/8 evidence cases passed;
- 4/4 first-trade postmortem cases passed.

The release adds detailed readiness diagnostics, liveness, and read-only signal lineage. It does not modify strategy decisions, sizing, stop/target logic, or execution permissions.

After promotion, durability remained on `/data/mrc_slow_staging_v3.sqlite3`; `boot_count` advanced from 16 to 17 and `probe_id` remained `1d586d7c-2190-4d10-8cef-df931f6fe1d4`. The forward gate reports release `c4ce...`, status `PASS`, zero refresh failures, and R0 real-money status `BLOCKED`.

## Decision

Continue prospective PAPER collection unchanged. Do not retune from N=1. Do not promote to real money. Re-evaluate only after a materially larger closed-trade sample and the existing scientific and operational gates.
