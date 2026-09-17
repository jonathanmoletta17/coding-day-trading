# OKX Demo Gate Report — 2026-09-17

## Scope

Read-only end-to-end diagnostic for the SLOW_TREND_BREAKOUT_V1 execution path.
No order endpoint was called. No real-money execution was enabled.

## D1 — Authenticated read-only diagnostic

Result: PARTIAL PASS / ACCOUNT-MODE BLOCK

- Demo credentials present in Railway: PASS
- OKX authenticated account config: PASS
- Clock drift: ~59 ms, PASS
- Position mode: `net_mode`
- Account level: `acctLv=1` (Spot mode)
- Private SWAP instruments returned by `/api/v5/account/instruments?instType=SWAP`: 0
- `BTC-USDT-SWAP` private availability: false
- `ETH-USDT-SWAP` private availability: false
- Order submission performed: false

Public instrument metadata was available for both targets:

### BTC-USDT-SWAP
- state: live
- ctType: linear
- ctVal: 0.01
- ctValCcy: BTC
- lotSz: 0.01
- minSz: 0.01
- settleCcy: USDT
- max published leverage metadata: 100

### ETH-USDT-SWAP
- state: live
- ctType: linear
- ctVal: 0.1
- ctValCcy: ETH
- lotSz: 0.01
- minSz: 0.01
- settleCcy: USDT
- max published leverage metadata: 100

## D2 — Dry-run order construction

Result: PASS / FAIL-CLOSED

Representative dry-run payloads were constructed without submission:

- BTC base quantity `0.001 BTC` -> `0.1` contracts
- ETH base quantity `0.01 ETH` -> `0.1` contracts
- deterministic `clOrdId`: generated
- order type: market
- margin mode payload: cross
- position-mode mapping: net

Execution gate remained blocked:

- `MRC_EXECUTION_MODE=DEMO`
- `MRC_DEMO_EXECUTION_ENABLED=0`
- `MRC_KILL_SWITCH=1`
- account mode verified for SWAP: false
- private instrument availability: false
- order_submission_performed: false

## Blocker

The Demo account is currently in OKX Spot mode (`acctLv=1`). The strategy requires SWAP access. Before any D3 simulated order test, the Demo account must be placed in an account mode that supports SWAP (for example Futures mode), and the Demo API key must have the minimum trading permission required for an explicitly authorized simulated-order test.

## Safety status

- Real money: HARD BLOCKED
- Demo order submission: BLOCKED
- PAPER strategy: unaffected
- Credentials: never logged or committed
