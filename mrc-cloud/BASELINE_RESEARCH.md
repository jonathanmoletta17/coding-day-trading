# MRC Quant Desk — Baseline Research State

Date: 2026-09-16

## CONTROL — TREND_BREAKOUT_V1

Purpose: simple, auditable reference strategy. It is a CONTROL, not a claim of edge.

### Frozen live rules

- Market feed: OKX public perpetual swaps (BTC-USDT-SWAP, ETH-USDT-SWAP)
- Trend: 1H EMA20 vs EMA50
- Trigger: confirmed 15m close outside the prior Donchian-20 range in trend direction
- ATR: Wilder ATR(14) calculated from the latest 40 confirmed 15m bars (same implementation as production)
- Entry: next actionable price after the confirmed signal; historical sanity proxy uses next 15m open
- Stop: 1.5 ATR
- Target: 2R (= 3 ATR from entry)
- Max signal age: 20 minutes
- Max chase: 0.50 ATR
- Max hold: 24 hours
- Cost model: 6 bps round trip
- Risk: 0.25% of paper equity per trade
- One global position at a time
- Same-bar stop+target ambiguity: STOP (pessimistic)

## Independent 30-day sanity check

Period: 2026-08-17 to 2026-09-16.

Historical source: Massive aggregated BTCUSD/ETHUSD, deliberately independent from the OKX live feed. This is a cross-source sanity check, not final OKX validation.

Coverage:
- BTCUSD 15m: 2,880 bars
- ETHUSD 15m: 2,880 bars
- 1H warm-up loaded for trend calculations

### Raw eligible signal outcomes (before de-overlap)

| Asset | Signals | Net expectancy | Net total | Avg modeled cost | Target rate |
|---|---:|---:|---:|---:|---:|
| BTC | 104 | -0.1250 R | -13.00 R | 0.1141 R | 32.69% |
| ETH | 100 | -0.1319 R | -13.186 R | 0.0919 R | 32.00% |

Raw signals are not a tradable portfolio because many occur while an earlier position would still be open.

### Executable greedy selection

Selection rule: sort chronologically; accept the earliest eligible trade only when `entry_time > prior_selected_exit_time`. For equal entry timestamps BTC has priority, matching the production symbol loop. Only one global position may be open.

#### Per-asset one-position diagnostic

| Asset | Trades | Expectancy | Total R | Win rate | PF | Max DD | Targets | Stops | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 61 | +0.0334 R | +2.037 R | 37.70% | 1.049 | -17.483 R | 23 | 37 | 1 |
| ETH | 65 | -0.1205 R | -7.831 R | 32.31% | 0.837 | -23.210 R | 21 | 44 | 0 |

#### Global production-like portfolio

- Trades: **83**
- Net expectancy: **-0.0486 R/trade**
- Net total: **-4.033 R**
- Win rate: **34.94%**
- Profit factor: **0.932**
- Max drawdown: **-22.876 R**
- Targets: **29**
- Stops: **53**
- Time exits: **1**
- Fixed-fraction simulation at 0.25% risk/trade: $10,000 -> approximately **$9,894.44**
- Approx max fixed-fraction drawdown: **-5.59%**

Bootstrap (20,000 resamples of the 83 selected net-R trades):
- 95% CI for mean expectancy: approximately **[-0.349 R, +0.263 R]**
- Fraction of bootstrap means > 0: approximately **37.6%**

Weekly selected R was highly unstable: a very strong first week was followed by several negative weeks. This is consistent with a strategy that benefits from intermittent trend bursts and is vulnerable to whipsaw.

### Decision

`TREND_BREAKOUT_V1 = CONTROL / PAPER ONLY`

It is not approved as a demonstrated trading edge. Do not optimize its parameters against this 30-day sample.

---

## CHALLENGER-001 — SLOW_TREND_TURTLE_LITE

Pre-declared rationale: the CONTROL is fast (1H trend + 15m breakout) and uses a fixed 2R target. Classical trend-following evidence is strongest at slower horizons and relies on retaining large right-tail winners rather than truncating them with a tight fixed target.

Frozen challenger before testing:

- Regime/trend: 4H EMA20 vs EMA50
- Trigger: confirmed 1H Donchian-20 breakout in trend direction
- Initial stop: 2.0 ATR(20) on 1H
- Profit target: **none**
- Exit: opposite Donchian-10 exit on 1H OR initial stop
- Risk: 0.25% paper only during research
- Cost: 6 bps round trip
- One global position
- No ADX, RSI, Supertrend, ML, order-flow veto, funding filter, or per-asset tuning

### Required validation sequence

1. 180-day discovery/diagnostic across BTC, ETH, SOL, BNB, XRP using unchanged rules.
2. Report per-asset and pooled net R, PF, drawdown, turnover, trade duration, and right-tail contribution.
3. Chronological split; no random train/test.
4. If discovery is not obviously broken, freeze rules.
5. New 90-day OOS block with no parameter changes.
6. Prospective PAPER in the cloud.
7. Only challengers that beat CONTROL after costs and survive OOS can enter the Strategy Tournament.

## Research discipline

- No parameter is promoted because it maximizes this 30-day sample.
- Rejected hypotheses remain documented.
- Order flow is telemetry until a separately pre-declared incremental test demonstrates value.
- ML is a later challenger and must predict outcomes within a frozen setup universe; it cannot invent a new universe and grade itself on the same data.
