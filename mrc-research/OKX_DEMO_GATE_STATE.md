# SLOW_TREND_BREAKOUT_V1 — OKX Demo Gate State

Date: 2026-09-17

## Canonical status

- Strategy: `SLOW_TREND_BREAKOUT_V1`
- Strategy promotion status: **SHADOW / RESEARCH ONLY**
- Execution environment under validation: **OKX Demo only**
- Real-money execution: **NOT ENABLED / NOT AUTHORIZED**
- Current gate: **D2 PASS; D3 V2 HARDENED BUT NOT ARMED**

## Account / API state confirmed by authenticated Demo validation

- `acctLv = 2` — Futures mode confirmed after account-mode change.
- `posMode = net_mode`.
- API permissions visible to the validator: `read_only`, `trade`.
- API label: `MRC-SLOW-DEMO-GLOBAL`.
- Private SWAP instruments visible: `107`.
- `BTC-USDT-SWAP`: privately available, live, linear, USDT-settled.
- `ETH-USDT-SWAP`: privately available, live, linear, USDT-settled.
- Cross leverage observed during D2: `3x` on BTC and `3x` on ETH.
- D2 observed no non-zero BTC/ETH target positions and no pending BTC/ETH target orders.

## D2 — dry-run gate

Status: **PASS**

Canonical implementation commit:

`16179d4aeea09ef1f37ed2185b4c4baa1f213293`

Properties:

- Authenticated/public `GET` validation only.
- No private order `POST` exists in the D2 gate.
- Requires Demo mode, Demo execution disabled, kill switch active and diagnostic-only mode active.
- Builds the exact minimal BTC round-trip payload in memory only.
- Test size: `0.01` BTC-USDT-SWAP contracts.
- Approximate notional at the validated snapshot: about `7.65 USDT` (market-dependent).
- Hard notional cap: `20 USDT`.
- Deterministic client order IDs are constructed in memory.
- `order_submission_performed = false`.
- `private_post_performed = false`.
- `real_money_execution_enabled = false`.

## D3 V2 — hardened Demo round-trip code

D3 is **not authorized to run yet**.

Safety-hardening commits:

- Main D3 V2 hardening: `b84d5ed79665492f7e4dabe68f1202703dc4baa0`
- Lost-POST-response cleanup hardening: `4420d411682c54b87089b48e054b86d711b2aa51`
- Offline fail-closed safety self-test: `a86e42272bb100c62a856e48d6c54fc8a97fbe0d`

D3 V2 safety properties:

1. The old D3 arm token is invalidated. V2 requires exactly `DEMO_BTC_MIN_ROUNDTRIP_V2`.
2. It requires an explicit per-attempt `MRC_D3_ATTEMPT_ID` and derives deterministic `clOrdId` values from it.
3. It requires an explicit `MRC_D3_EXPECTED_LEVERAGE`; it does not silently choose or change leverage.
4. It requires `acctLv=2`, `net_mode`, the expected API label, trade permission, BTC SWAP availability and valid contract metadata.
5. It refuses entry if any BTC position or pending BTC order already exists.
6. It rechecks position and pending orders immediately before the first order POST.
7. It caps the opening quantity at `0.01` contract and notional at `20 USDT`.
8. Emergency cleanup is disabled unless an opening POST was actually attempted.
9. Cleanup may reduce only positive exposure up to the D3 test maximum (`0.01` contract); it refuses to flatten larger or unexpected positions.
10. After an uncertain/lost opening response, cleanup observes the account for a short window before concluding that no exposure was created.
11. The close and emergency cleanup orders are `reduceOnly`.
12. Every request remains bound to OKX simulated trading via `x-simulated-trading: 1`.

## D3 remains fail-closed

At this checkpoint the Railway service does **not** define the new required variables:

- `MRC_D3_ATTEMPT_ID`
- `MRC_D3_EXPECTED_LEVERAGE`

Therefore D3 V2 cannot pass its preflight even if an old arm value happens to exist.

The audit service start command compiles D3 V2, runs the offline D3 safety self-test, then returns to D2 dry-run validation. It does not invoke the D3 round-trip.

## Required human gate before any Demo order

Before D3 can be executed, all of the following must be an explicit deliberate change for one controlled attempt:

- choose/declare the expected leverage policy;
- create a unique attempt ID;
- confirm account remains flat with no pending BTC order;
- explicitly switch off diagnostic-only mode;
- explicitly enable Demo execution;
- explicitly release the kill switch;
- set the V2 arm token;
- run only the minimum BTC Demo round-trip;
- verify opening fill, reduce-only closing fill and final position exactly zero;
- immediately restore execution-disabled / kill-switch-on / diagnostic-only state after the test.

No historical result or Demo round-trip promotes this strategy to real-money execution. Promotion remains governed by the frozen strategy specification and independent forward/OOS evidence.
