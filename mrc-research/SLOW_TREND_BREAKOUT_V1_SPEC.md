# SLOW_TREND_BREAKOUT_V1 — preregistered challenger

Status: **SHADOW / RESEARCH ONLY**

This specification is frozen **before inspecting the one-year OKX result of TREND_BREAKOUT_V1**. It is not a tuned response to that result.

## Rationale

The production control uses 15m breakout signals with a 1H trend filter. The challenger tests one structural hypothesis only: a slower horizon may reduce microstructure noise and transaction-cost drag while preserving the same trend-following logic.

## Frozen rules

- Markets for first comparison: BTC-USDT-SWAP and ETH-USDT-SWAP.
- Signal timeframe: **1H** confirmed candles.
- Trend timeframe: **4H** confirmed candles.
- Trend filter:
  - LONG only when EMA20(4H) > EMA50(4H).
  - SHORT only when EMA20(4H) < EMA50(4H).
- Trigger:
  - LONG when the confirmed 1H close is above the highest high of the **previous 20 confirmed 1H candles**.
  - SHORT when the confirmed 1H close is below the lowest low of the **previous 20 confirmed 1H candles**.
- ATR: Wilder ATR14 recomputed over the last **40 confirmed 1H candles**, preserving the implementation convention used by the control.
- Entry proxy in research: next 1H candle open.
- Stop: **1.5 ATR** from entry.
- Target: **2R** = 3 ATR from entry.
- Chase filter: abs(next_open - signal_close) / ATR <= **0.5**.
- Maximum holding period: **72 hours**. This is a duration scaling decision (3 days) declared before seeing the annual control result, not an optimized parameter.
- Same-bar stop/target ambiguity: **STOP wins**.
- Round-trip transaction-cost stress baseline: **6 bps**.
- Risk per trade: **0.25% of current paper equity**.
- Maximum simultaneous positions: **1 globally**.
- Exact entry-time tie priority: BTC before ETH, matching the control convention.
- Next trade requires entry_time > previous exit_time.
- Daily realized-loss lock: **1% of initial paper equity**.
- No funding, taker flow, OI, long/short ratio, RSI, ADX, Supertrend, ML or discretionary filter may affect entry in V1.

## Comparison protocol

Run over the same fixed one-year OKX period used for TREND_BREAKOUT_V1, with identical cost, ambiguity and portfolio assumptions. Report at minimum:

- N trades
- win rate
- net expectancy in R
- median R
- profit factor
- total R
- max drawdown in R and equity %
- ending equity / return
- 95% bootstrap CI of mean R
- BTC vs ETH
- LONG vs SHORT
- quarter-by-quarter stability

No parameter is changed after viewing the result. If this challenger is weak, it remains a failed experiment rather than being retuned in-place.

## Promotion constraint

This historical comparison alone cannot promote the challenger to real-money execution. Any promotion requires independent OOS / forward PAPER evidence and the existing promotion gate.
