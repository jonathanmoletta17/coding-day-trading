# FIRST PROSPECTIVE PAPER TRADE — REVIEW TEMPLATE

Strategy: `SLOW_TREND_BREAKOUT_V1`

Use this document only after the first naturally qualifying PAPER trade has closed.

Do not fill it from memory. Every field should be backed by the durable PAPER corpus, frozen release metadata or the causal replay evidence.

## 1. Identity

- PAPER release SHA:
- trade ID:
- signal ID:
- symbol:
- side:
- signal close timestamp:
- PAPER open timestamp:
- PAPER close timestamp:
- outcome (`STOP`, `TARGET`, `TIME`, other):

## 2. Corpus integrity before interpretation

Confirm first:

- `/readyz` ready at review time:
- durable storage true:
- evidence integrity pass:
- historical unpaired closes = 0:
- internal hourly gaps BTC = 0:
- internal hourly gaps ETH = 0:
- decision/signal/trade counters monotonic:
- cross-endpoint counter parity pass:
- trade references an existing signal:
- at-most-one-open-position invariant held:

If corpus integrity is not clean, stop economic interpretation until the discrepancy is understood.

## 3. Entry decision reconstruction

Record the exact decision context that generated the signal:

- trend:
- EMA20 4H:
- EMA50 4H:
- breakout direction:
- breakout close:
- Donchian high:
- Donchian low:
- ATR14:
- bid/ask-derived PAPER entry:
- age at decision:
- chase ATR:
- risk USDT:
- PAPER quantity:
- stop:
- target:
- daily lock state:
- global slot state:
- re-entry block state:

Then answer descriptively:

- Did the candidate satisfy the frozen V1 rule set exactly?
- Was any fallback, stale-data path or manual override involved?

Expected answer to the second question for a valid prospective V1 trade: **no**.

## 4. Exit reconstruction

Reconstruct from confirmed causal 1m data:

- first causal minute after entry:
- last checked minute:
- max-hold deadline:
- replay source (`recent` or paginated history):
- replay page count:
- coverage gap detected?:
- exit-trigger minute:
- stop touched?:
- target touched?:
- same-minute stop+target ambiguity?:
- deadline-straddling minute?:
- final exit reason:
- final exit price:

Confirm that the frozen conservative rules were applied:

- STOP wins same-bar ambiguity.
- TARGET cannot win on a bar that closes after the 72h deadline.
- Current incomplete minute can trigger STOP only, not TARGET.

## 5. Economic result — frozen baseline

At official 6 bps round-trip cost:

- gross PnL:
- modeled fees/cost:
- net PnL:
- gross R:
- cost R:
- net R:
- equity after trade:

## 6. Cost sensitivity — same trade, no mutation

Reprice the exact same entry/exit/quantity/risk under:

| Scenario | Round-trip cost | Net PnL | Net R | Difference vs 6 bps |
|---|---:|---:|---:|---:|
| Baseline | 6 bps | | | 0 |
| Stress | 10 bps | | | |
| Stress | 15 bps | | | |

Do not change entry, exit, stop, target or quantity between scenarios.

## 7. Demo calibration comparison

Current first bounded Demo calibration reference: `10.01 bps`.

For this PAPER trade, record:

- modeled 6 bps cost R:
- modeled 10 bps cost R:
- modeled 15 bps cost R:
- where 10.01 bps would lie descriptively:

This is a sensitivity comparison only. It does not retroactively replace the frozen 6 bps baseline.

## 8. First-trade interpretation discipline

Do **not** conclude from one trade that:

- the strategy works;
- the strategy fails;
- the win rate is meaningful;
- expectancy is established;
- parameters should be changed;
- R0 should advance.

The first trade is most valuable as a full-chain prospective validation of:

`DECISION -> SIGNAL -> PAPER OPEN -> CAUSAL MANAGEMENT -> EXIT -> COST ACCOUNTING -> DURABLE AUDIT`

## 9. Questions the first trade may legitimately raise

Examples:

- Was modeled slippage/cost materially important relative to risk R?
- Did the 6/10/15 bps scenarios materially change the sign or magnitude of net R?
- Was the holding period close to the 72h deadline?
- Did the trade occur in a market regime represented in historical research?
- Did the signal occur shortly after a deployment/restart?
- Were there any transient data errors around entry or exit?

These are investigation prompts, not reasons to retune V1 automatically.

## 10. Post-review verdict fields

Choose descriptive statuses only:

- `TRADE_CHAIN_INTEGRITY = PASS / FAIL / INVESTIGATE`
- `CAUSAL_EXIT_RECONSTRUCTION = PASS / FAIL / INVESTIGATE`
- `FROZEN_COST_ACCOUNTING = PASS / FAIL / INVESTIGATE`
- `CORPUS_INTEGRITY = PASS / FAIL / INVESTIGATE`
- `ECONOMIC_SAMPLE_STATE = N1_9`
- `V1_PARAMETER_CHANGE = NO`
- `R0 = BLOCKED`

## 11. Canonical rule after review

If all engineering/integrity checks pass, the correct next action after the first trade is normally:

`CONTINUE PROSPECTIVE COLLECTION`

—not strategy promotion and not parameter optimization.
