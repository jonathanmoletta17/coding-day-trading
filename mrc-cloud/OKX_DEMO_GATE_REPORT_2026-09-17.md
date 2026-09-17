# OKX Demo Gate Report — 2026-09-17

## Scope

End-to-end validation of the `SLOW_TREND_BREAKOUT_V1` execution path using **OKX Demo Trading only**.
Production/real-money execution remained out of scope and hard-blocked throughout.

## Final gate state

| Gate | Result | Exchange side effects |
|---|---|---|
| D0 — offline/code safety | PASS | none |
| D1 — authenticated read-only | PASS | none |
| D2 — dry-run / no order | PASS | none |
| D3 — minimum Demo round-trip | PASS | 1 tiny open + 1 reduce-only close |
| D4 — lifecycle/fault/restart validation | PASS | bounded Demo-only resting orders + 1 minimum restart-position round-trip |
| Forward PAPER/OOS evidence | ACTIVE | PAPER only |
| R0 — real money | BLOCKED | none |

## D1 — authenticated Demo account validation

Validated state:

- `x-simulated-trading: 1`
- account level: `acctLv=2` (Futures mode)
- position mode: `net_mode`
- API permissions: `read_only`, `trade`
- API label: `MRC-SLOW-DEMO-GLOBAL`
- private SWAP instruments visible: 107
- `BTC-USDT-SWAP`: private available, live, linear USDT-settled
- `ETH-USDT-SWAP`: private available, live, linear USDT-settled
- BTC/ETH cross leverage observed: exactly `3x`
- production credentials not used

BTC metadata used by execution gates:

- `ctVal=0.01 BTC`
- `lotSz=0.01`
- `minSz=0.01`
- `ctType=linear`
- `settleCcy=USDT`

## D2 — fail-closed dry run

Result: **PASS**.

Validated before execution testing and repeatedly after it:

- target position zero
- target pending orders zero
- Futures + `net_mode`
- 3x cross leverage readable/preserved
- deterministic `clOrdId`
- minimum BTC test size `0.01` contracts
- approximate test notional about US$7.65
- exchange max-size comfortably above test size
- payloads constructed in memory
- no private POST during the dry-run
- real-money execution blocked

A legacy D3 readiness diagnostic later exposed a reporting-only bug: it stored `private_post_performed=false` as a Boolean gate and then required every gate value to be true. The raw audit still correctly showed position 0, pending 0, safe locks and no POST. D4 final validation therefore uses the independent read-only reconciliation audit rather than that legacy aggregate status.

## Safe POST transport probe

Before the first live Demo order, `POST /api/v5/trade/order` was authenticated with a deliberately expired `expTime`.

Observed:

- HTTP `200`
- OKX top-level code `1`
- item `sCode=50036`
- no order history entry
- no fill
- no position
- no pending order

This proved Demo request signing, routing, `x-simulated-trading` and server-side expiry handling without exposure.

## D3 attempt A — fail-closed diagnostic

Attempt: `D3BTC260917A`.

The first armed execution did not reach a completed round-trip. Locks were restored and an independent postmortem found:

- BTC position `0`
- BTC pending `0`
- no matching OPEN/CLOSE/SAFE order
- no matching fill
- `any_d3_order_evidence=false`

A GET-only shadow preflight then passed, isolating the failure from account mode, leverage, sizing and read-side API state.

## D3 attempt B — minimum Demo round-trip

Attempt: `D3BTC260917B`.

Result: **PASS**.

Preflight:

- Futures / net mode
- 3x cross
- quantity `0.01` contracts
- contract value `0.01 BTC`
- approximate notional `US$7.65148`
- starting position `0`
- pending orders `0`

Opening fill:

- `clOrdId=MRCD3O08A5DF691590C2B1316E`
- `ordId=3931664057535287296`
- buy `0.01`
- average `76514.8`
- state `filled`
- position after open `0.01`
- fee `-0.003825740 USDT`

Reduce-only closing fill:

- `clOrdId=MRCD3CD9BBC639C09AD6608B19`
- `ordId=3931664070218862592`
- sell `0.01`
- average `76514.7`
- state `filled`
- PnL `-0.00001 USDT`
- fee `-0.003825735 USDT`

Final:

- position `0`
- pending `0`
- both orders and fills independently reconciled
- emergency SAFE order not required

### D3 cost calibration

- fees: `0.007651475 USDT`
- price PnL: `-0.000010000 USDT`
- total realized test cost: `0.007661475 USDT`
- approximate total round-trip cost: **10.01 bps**

This is execution calibration evidence, not a research-baseline change. PAPER remains 6 bps; 10 and 15 bps remain analytical stress cases.

## D4 — lifecycle/fault/restart validation

Result: **PASS**.

All D4 scenarios used Demo credentials only, BTC minimum size where exposure was required, deterministic IDs, 3x cross without leverage mutation, and final independent reconciliation.

### D4 safe lifecycle — attempt `D4BTC260917A`

Preflight market reference: BTC `76575.2`; deep resting test buy price `38287.6`, roughly 50% below market, quantity `0.01` contracts.

#### Cancel by exchange `ordId` — PASS

- `clOrdId=MRCD4O61D12A2A85FA94B604`
- `ordId=3931702876758331392`
- no fill
- final state `canceled`
- position remained `0`

#### Cancel by deterministic `clOrdId` — PASS

- `clOrdId=MRCD4C990B8F6C9E80925B0A`
- `ordId=3931702906118459392`
- no fill
- final state `canceled`
- position remained `0`

#### Ambiguous ACK / query-before-retry — PASS

- `clOrdId=MRCD4A288ACDB54F4253BE50`
- `ordId=3931702934438400000`
- client state intentionally treated as ambiguous after submission
- resolver queried exchange by deterministic `clOrdId`
- existing order discovered in `live` state
- `retry_allowed=false`
- no duplicate opening submission
- order then canceled
- final position/pending `0/0`

#### Deterministic rejected-order handling — PASS

A deliberately expired request returned:

- HTTP `200`
- top-level OKX code `1`
- item `sCode=50036`
- no order evidence in history
- no fill evidence
- final position/pending `0/0`

### D4 restart with exchange-side resting order — attempt `D4BTC260917R`

Stage 1 created one deep non-marketable order:

- `clOrdId=MRCD4RF61DE85C9295B4CB1F`
- `ordId=3931707070659678208`
- price `38294.5`
- size `0.01`
- state `live`
- position `0`
- exactly one owned pending order

A new Railway process was then started with:

- new openings disabled
- kill switch active
- diagnostic-only active

Stage 2:

- discovered the existing exchange order by deterministic `clOrdId`
- `opening_post_performed=false`
- canceled the existing order
- state `live → canceled`
- final position `0`
- final pending `0`

This validates restart reconciliation plus the rule that kill-switch mode still permits read/reconciliation and risk-reducing cancellation.

### D4 restart with exchange-side position — attempt `D4BTC260917P`

This test was only performed after the resting-order restart passed.

Stage 1:

- opened minimum `0.01` BTC-SWAP contract
- `clOrdId=MRCD4P0E2DC2B2B67C2F3A32`
- `ordId=3931713404092272640`
- filled at `76643.8`
- position confirmed `0.01`
- pending orders `0`

Before stage 2, new openings were disabled and kill switch/diagnostic-only were activated.

Stage 2:

- discovered exchange position `0.01`
- independently proved ownership from the filled OPEN order in OKX history
- `opening_post_performed=false`
- sent only a risk-reducing `reduceOnly` market close
- close `clOrdId=MRCD4PFE793257D9A832315A`
- close `ordId=3931714612420923392`
- filled at `76679.4`
- size `0.01`
- exchange-reported close PnL `0.00356 USDT`
- final position `0`
- final pending `0`

This is the strongest restart/reconciliation proof in D4: local process state was replaced while exchange exposure existed, and the new safe process recovered exchange truth without duplicating the entry.

### D4 partial-fill/idempotency state model — PASS

Live partial fills were **not forced** by increasing test size or manipulating liquidity.

Instead, deterministic tests validate:

- `live/unfilled`
- `partially_filled`
- live snapshots with nonzero `accFillSz`
- `filled`
- `canceled` after partial execution
- exact remaining-quantity arithmetic
- no blind opening retry while any remote order exists
- ambiguous submission result → query/reconcile before retry
- inconsistent fill quantities/states fail closed

Test result:

`D4_ORDER_STATE_TEST=PASS partial_fill=true idempotency=true invalid_states_fail_closed=true`

An organically observed Demo partial fill may be added as supplemental evidence later, but it is not manufactured as a gate requirement.

## Independent D4 final audit

A separate read-only process, running only after all opening flags were disabled, returned **PASS**:

- position `0`
- pending `0`
- cross leverage `[3]`
- opening disabled
- kill switch active
- diagnostic-only active
- D4 arm empty
- cancel-by-ordId order independently seen as `canceled`
- cancel-by-clOrdId order independently seen as `canceled`
- ambiguous-ACK order independently seen as `canceled`
- expired request independently confirmed to have no order evidence
- restart-pending order independently seen as `canceled`
- restart-position OPEN independently seen as `filled`, fill count ≥1
- restart-position CLOSE independently seen as `filled`, fill count ≥1
- `private_post_performed=false` in final audit
- `real_money_execution_enabled=false`

## Forward PAPER release after D4

The active PAPER sidecar was promoted to pinned SHA:

`132f3e939c8074dff084f4e56049754f9030af6f`

Verified externally through the internal probe:

- `/readyz`: BTC=true, ETH=true, no coverage gap
- storage: SQLite, durable
- historical prospective state preserved (16 decisions, 0 trades at promotion checkpoint)
- `/api/audit` exposes cost policy and 6/10/15 bps sensitivity
- `/api/cost-sensitivity` available
- cost sensitivity test passes as non-mutating
- durability probe persisted across restarts (`boot_count` reached 13 during this validation)
- observed Demo calibration recorded separately as `10.01 bps`

The 10.01 bps value is audit metadata only. Signal generation, trade management, persisted historical PnL and the official 6 bps PAPER baseline are unchanged.

## What D4 does — and does not — prove

D4 proves substantially more robust Demo execution plumbing:

- deterministic IDs
- bounded order submission
- expiry handling
- cancellation
- exchange truth reconciliation
- no blind retry after ambiguous submission
- kill-switch recovery behavior
- restart with pending exchange state
- restart with existing position
- reduce-only flattening
- final flat-state reconciliation
- partial-fill state handling in deterministic tests

D4 **does not prove economic edge**, acceptable production slippage, production credential safety, production incident response, or readiness to risk capital.

## Post-D4 safety state

- production credentials: not used
- real money: **HARD BLOCKED**
- Demo new openings: **DISABLED**
- kill switch: **ACTIVE**
- diagnostic-only: **ACTIVE**
- D4 arm: **CLEARED**
- BTC position: `0`
- BTC pending orders: `0`
- PAPER forward collection: **ACTIVE**
- D4: **PASS**
- R0: **BLOCKED**

## Next evidence gate

The next gate is not another connectivity test. It is **prospective economic and operational evidence**:

- continue untouched PAPER/OOS collection
- track 6 bps baseline and 10/15 bps sensitivity side by side
- compare future Demo execution costs with the 10.01 bps calibration
- accumulate enough actual signals/trades to estimate prospective expectancy, win rate, drawdown and realized cost-R
- investigate regime dependence without retuning V1 from a small sample
- keep production execution disabled until a separate human approval and production-specific risk review
