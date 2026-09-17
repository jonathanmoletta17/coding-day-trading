# OKX Demo Gate Report — 2026-09-17

## Scope

End-to-end validation of the `SLOW_TREND_BREAKOUT_V1` execution path using **OKX Demo Trading only**.
Production/real-money execution remained out of scope and hard-blocked.

This report supersedes the earlier same-day snapshot in which the Demo account was still in Spot mode.

## Final gate state

| Gate | Result | Order side effects |
|---|---|---|
| D0 — offline/code safety | PASS | none |
| D1 — authenticated read-only | PASS | none |
| D2 — dry-run / no order | PASS | none |
| D3 — minimum Demo round-trip | PASS | 1 tiny open + 1 reduce-only close in Demo |
| D4 — lifecycle/fault validation | PENDING | not yet promoted |
| R0 — real money | BLOCKED | none |

## D1 — authenticated Demo account validation

Final validated state:

- `x-simulated-trading: 1`: confirmed by all private Demo requests
- account level: `acctLv=2` (Futures mode)
- position mode: `net_mode`
- API permissions: `read_only`, `trade`
- API label: `MRC-SLOW-DEMO-GLOBAL`
- private SWAP instruments visible: 107
- `BTC-USDT-SWAP`: private available, live, linear USDT-settled
- `ETH-USDT-SWAP`: private available, live, linear USDT-settled
- BTC/ETH cross leverage observed: exactly `3x`
- no production credentials used

Instrument metadata used by the gate:

### BTC-USDT-SWAP

- `ctVal=0.01 BTC`
- `lotSz=0.01`
- `minSz=0.01`
- `ctType=linear`
- `settleCcy=USDT`

### ETH-USDT-SWAP

- `ctVal=0.1 ETH`
- `lotSz=0.01`
- `minSz=0.01`
- `ctType=linear`
- `settleCcy=USDT`

## D2 — fail-closed dry run

Result: **PASS**.

Validated immediately before and after D3:

- target positions: zero
- target pending orders: zero
- Futures account mode valid
- `net_mode` valid
- BTC/ETH leverage metadata readable
- BTC leverage remained `3x cross`
- deterministic `clOrdId` generation
- minimum BTC test size: `0.01` contracts
- approximate test notional: about `US$7.65`
- order payloads constructed in memory
- `private_post_performed=false`
- `order_submission_performed=false`
- real-money execution blocked

## Safe POST transport probe

Before a live Demo order was attempted, the same authenticated `POST /api/v5/trade/order` route was tested with a deliberately expired `expTime`.

Observed response:

- HTTP status: `200`
- OKX top-level code: `1` (`All operations failed`)
- item `sCode=50036`
- message: `The expTime can't be earlier than the current system time. Please adjust the expTime and try again.`
- position before/after: `0`
- pending orders before/after: `0`
- matching history/fills: `0`

Conclusion: Demo authentication, request signing, `x-simulated-trading`, POST routing and expiry handling were working without allowing exposure.

## D3 attempt A — fail-closed diagnostic

Attempt ID: `D3BTC260917A`.

The first armed run did not reach a healthy round-trip state. Execution was immediately returned to safe locks and independently audited.

Postmortem:

- BTC position: `0`
- BTC pending orders: `0`
- matching OPEN/CLOSE/SAFE `clOrdId` records: none
- matching fills: none
- `any_d3_order_evidence=false`

Conclusion: attempt A failed before any Demo order was registered by OKX. No residual exposure existed.

A shadow preflight using the same D3 gates but with POST disabled subsequently passed in full, isolating the issue from account mode, leverage, sizing and read-side API state.

## D3 attempt B — minimum Demo round-trip

Attempt ID: `D3BTC260917B`.

Result: **PASS**.

Preflight immediately before submission:

- account: Futures (`acctLv=2`)
- position mode: `net_mode`
- permissions: read + trade
- target: `BTC-USDT-SWAP`
- margin mode: `cross`
- expected/observed leverage: `3x`
- quantity: `0.01` contracts
- contract value: `0.01 BTC`
- approximate notional: `US$7.65148`
- starting BTC position: `0`
- pending BTC orders: `0`
- maximum buy size reported: `19.41` contracts
- environment: Demo only

### Opening fill

- `clOrdId`: `MRCD3O08A5DF691590C2B1316E`
- OKX `ordId`: `3931664057535287296`
- side: buy
- size: `0.01`
- state: filled
- average fill: `76514.8`
- position after open: `0.01`
- fee: `-0.003825740 USDT`

### Reduce-only closing fill

- `clOrdId`: `MRCD3CD9BBC639C09AD6608B19`
- OKX `ordId`: `3931664070218862592`
- side: sell
- size: `0.01`
- `reduceOnly=true`
- state: filled
- average fill: `76514.7`
- fill PnL: `-0.00001 USDT`
- fee: `-0.003825735 USDT`

### Final reconciliation

- final BTC position: `0`
- pending BTC orders: `0`
- OPEN order independently found in history: yes
- CLOSE order independently found in history: yes
- OPEN fill independently found: yes
- CLOSE fill independently found: yes
- emergency SAFE order required: no
- D3 round-trip completed: yes

## Observed Demo transaction cost

For the D3 B round-trip:

- entry fee: `0.003825740 USDT`
- exit fee: `0.003825735 USDT`
- total fees: `0.007651475 USDT`
- price PnL: `-0.000010000 USDT`
- total realized test cost: `0.007661475 USDT`
- approximate round-trip cost on the ~US$7.65 notional: **~10.01 bps**

This measurement is an execution calibration observation, **not** a change to the frozen research baseline. The official V1 PAPER baseline remains 6 bps, while 10 bps and 15 bps are tracked as stress scenarios.

## Locks restored after D3

Immediately after the successful round-trip:

- `MRC_DEMO_EXECUTION_ENABLED=0`
- `MRC_KILL_SWITCH=1`
- `MRC_DEMO_DIAGNOSTIC_ONLY=1`
- `MRC_D3_ARM` cleared

A fresh authenticated D2 check then returned PASS with:

- zero target positions
- zero target pending orders
- 3x cross leverage preserved
- Demo execution disabled
- kill switch active
- diagnostic-only active
- real-money execution blocked

## Forward PAPER state

The strategy remains in `PAPER_STAGING` for prospective validation.

At the post-D3 checkpoint:

- BTC feed ready: true
- ETH feed ready: true
- durable SQLite under `/data`
- no coverage gap
- one-global-position invariant database-enforced
- restart replay tests passing
- max hold replay up to 72h
- daily realized loss lock: 1%
- risk per PAPER trade: 0.25%
- official cost baseline: 6 bps round trip
- analytical stress scenarios: 10 bps and 15 bps

No successful D3 result is sufficient to promote the strategy to production money.

## Next gate — D4

D4 must validate the Demo execution lifecycle and failure modes, including at minimum:

- duplicate submission/idempotency
- acknowledgement reconciliation
- filled-state reconciliation
- resting-order cancel by order ID
- resting-order cancel by client order ID
- rejected-order handling
- ambiguous timeout / query-before-retry behavior
- kill-switch behavior
- process restart/reconciliation while an exchange-side order or position exists
- partial-fill handling where it can be produced safely and deterministically
- final flat-state proof after every scenario

## Safety status

- Production credentials: not used
- Real money: **HARD BLOCKED**
- Demo automatic execution after D3: **DISABLED**
- Kill switch: **ACTIVE**
- PAPER forward collection: **ACTIVE**
- D4: **PENDING**
