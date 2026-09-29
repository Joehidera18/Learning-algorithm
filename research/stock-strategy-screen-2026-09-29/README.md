# Finding a tradable stock strategy: first fixed comparison

Research date: September 29, 2026. Historical cutoff: September 29, 2026 at 00:00 UTC; latest completed US session: September 28.

## Decision

**None of the 12 strategy/asset combinations qualifies for trading on the evidence collected here.** This screen found a software blocker, repaired it, and produced real historical results. It did not establish a profitable strategy.

For the next research cycle, concentrate on two families: opening-range breakouts in unusually active stocks for day trading, and slower trend breakouts for swing trading. Treat the current hourly pullback as a lower priority after its weak results. These are research priorities, not buy signals.

## What was preventing progress

The default Strategy Lab exit function returned two identical profit targets with a 50% partial exit. Its execution engine required two strictly ordered targets, so valid entry signals from all four default structure families were rejected. A generated, deterministic example reproduced one qualified signal and zero entries with `invalid_or_passed_price_levels`.

The correction makes the existing single target explicit: sell the full position at the original target, with no partial exit. It preserves entry rules, stop distance and target distance. The engine still rejects malformed, already-passed or reversed levels; genuine two-target strategies retain their partial fills. The structure-strategy version is now `structure-v2-single-target`.

Code commit: [1f20f2c](https://github.com/Joehidera18/Learning-algorithm/commit/1f20f2cff31e3ea4ff98bdf68969bceb9f4b5a16). The full Python regression suite passed 600 tests. This is a proposed code correction, not confirmation of a Render deployment. Software regression checks do not demonstrate profitability.

## Fixed experiment

Before viewing returns, the plan specified SPY, QQQ, IWM and NVDA, three existing rule sets, and the default cost assumptions. No parameter search was used. Every one of the twelve results is retained below.

- Independent $1,000 paper account per test; long-only; fractional shares; no leverage; one position at a time per account. This is not a combined four-asset portfolio and does not assume your current account balance.
- Target stop risk: 0.5% of equity, subject to a 95% notional cap. Actual losses can exceed this through gaps. Daily loss control: 2%, which cannot guarantee a maximum realized loss.
- Each side: 0.01% commission + 0.05% slippage + 0.02% half-spread, approximately 0.16% round trip. Higher-cost tests multiply all three by 1.5. These are explicit assumptions, not verified broker charges.
- Signals use completed bars; entry is next-bar open. If both stop and target are touched within an unordered OHLC bar, the stop wins. Stop gaps fill at the worse opening price.
- First 240 bars warm up indicators. First 70% of observed bars form development; last 30% form the later screen, with fresh balances in each window. Earlier data remains available for indicator warmup only.
- No historical news filter was supplied. No options, short borrowing, leverage, taxes, dividends or interest on idle cash are included.
- The later period becomes a selection set once we compare candidates. It is not an untouched final validation sample for any selected winner.

Five-minute history covers August 3–September 28, 2026; its later test is September 11–28 (12 sessions). Hourly history covers September 30, 2024–September 28, 2026; its later screen starts partway through February 25, 2026. Exact millisecond boundaries are in each report. Hourly bars are anchored at 09:30 New York time and include a shorter final session bar.

## Results after assumed costs

Returns are account returns over the stated window, **not annualized returns**. Trade counts exclude unresolved boundary marks. Maximum drawdown is the engine's historical equity-curve measure, not a forecast of worst possible loss.

| Strategy | Asset | Earlier return | Later return | Later trades | Later max drawdown | Higher-cost return | Higher-cost trades |
|---|---|---:|---:|---:|---:|---:|---:|
| Opening range, 5m | SPY | +0.00% | +0.00% | 0 | 0.00% | +0.00% | 0 |
| Opening range, 5m | QQQ | +0.28% | +0.00% | 0 | 0.00% | +0.00% | 0 |
| Opening range, 5m | IWM | -0.29% | -0.50% | 1 | 0.50% | +0.00% | 0 |
| Opening range, 5m | NVDA | -0.59% | +0.03% | 2 | 0.59% | -0.22% | 1 |
| Pullback, 1h | SPY | +0.38% | +0.00% | 0 | 0.00% | +0.00% | 0 |
| Pullback, 1h | QQQ | +1.23% | -0.18% | 2 | 0.98% | -0.88% | 1 |
| Pullback, 1h | IWM | Unavailable | -0.29% | 7 | 2.02% | +1.22% | 2 |
| Pullback, 1h | NVDA | -5.23% | -3.11% | 15 | 4.04% | -2.13% | 11 |
| Breakout + volume, 1h | SPY | -0.39% | +0.30% | 1 | 0.20% | +0.00% | 0 |
| Breakout + volume, 1h | QQQ | +0.86% | -1.20% | 4 | 1.71% | -1.00% | 2 |
| Breakout + volume, 1h | IWM | -1.19% | -0.75% | 5 | 1.63% | -0.53% | 2 |
| Breakout + volume, 1h | NVDA | Unavailable | +0.54% | 8 | 1.98% | -0.40% | 7 |

All twelve fail the existing minimum gate: at least 20 resolved trades, positive average net return per unit of risk, and positive account P/L in both later tests. Passing that gate would still not establish statistical confidence or authorize real-money trading.

Three specific readings:

- NVDA hourly breakout: +0.54% on eight trades, changing to −0.40% on seven trades at higher costs. This is not robust evidence.
- NVDA hourly pullback: −3.11% on 15 later trades. Its earlier period also lost money.
- SPY hourly breakout: +0.30% on one later trade, then no entries at higher costs. One winner is not an edge. A 0.00% result with zero trades means inactivity, not a successful defensive strategy.

Higher-cost runs sometimes lose less or gain more because the engine rejects additional entries when expected reward after costs is insufficient. Their trade sets therefore differ. They are not a controlled repricing of identical trades, and an apparently better stressed result does not prove that costs help performance.

## Data quality and interpretation

Source: public Yahoo historical chart endpoint, accessed through the app's equity adapter. Split-adjusted OHLC; cash dividends excluded. Calendar: NYSE regular sessions, including holidays and early closes. No missing price bar was fabricated.

| Asset | Five-minute candles | Missing 5m candles | Hourly candles | Missing hourly candles |
|---|---:|---:|---:|---:|
| SPY | 3120 | 0 | 3470 | 15 |
| QQQ | 3120 | 0 | 3471 | 14 |
| IWM | 3120 | 0 | 3470 | 15 |
| NVDA | 3120 | 0 | 3471 | 14 |

The hourly source had 14–15 invalid/missing expected bars per asset. Each observed gap resets 240-bar indicator warmup, materially reducing usable signal history. Development account P/L is unavailable for IWM pullback and NVDA breakout because a position was open when a data gap occurred. The engine stopped those accounts rather than guess an exit. All later account windows completed, but some early later bars remained in post-gap warmup.

The short opening-range window is inadequate by construction: one signal per asset per day cannot supply 20 later trades in 12 sessions. We must extend the history rather than weaken that evidence gate. The 20-session opening-volume warmup further limits the full sample.

This four-instrument screen is deliberately narrow and uses today's selected instruments. It is not a survivorship-free historical stock-universe study. No claim of alpha over buy-and-hold, portfolio diversification or statistical significance is made.

## Exact rules tested

### 1. Fifteen-minute opening-range breakout — day trading

Use five-minute regular-session bars. Build the high and low over 09:30–09:45 New York time. Require a complete range and opening-range volume at least equal to the mean of the prior 20 complete observed opening ranges. Use the first subsequent bar closing above the range high; no second signal that session, even if its entry is rejected. Enter at the following bar's open subject to the gap/cost checks.

Stop at the opening-range low. Sell half at signal close plus one range width and half at signal close plus two range widths. Those distances are **range widths, not exactly 1R and 2R** from the actual fill. Flatten remaining shares at the session close. No overnight signal carryover. The candidate is `orb_15m`, version `orb-15m-v2-complete-range`.

This is a testable existing adaptation. Its four tiny later samples do not validate it.

### 2. Trend pullback — hourly swing trading

Bull condition: 50-period EMA above 200-period EMA and close above the close 20 bars earlier. Pullback condition: close within 0.55 ATR of the 20-period EMA and at or above the 50-period EMA. Require RSI 40–65 and the app's 20-bar signed volume-pressure measure at least −0.10. Reject extreme volatility (ATR regime >2.5 or current range >4 times the preceding 20-bar average range).

Enter at next-bar open after passing the shared checks. Set the signal-time stop distance to 1.5 times ATR, with ATR floored at 0.2% of price. Place the stop below signal close and the full-position target at twice that distance above signal close. These are signal-relative levels; next-open gaps/costs change actual reward/risk. Exit after 120 elapsed hours if still open. Overnight risk applies. Candidate: `trend_pullback_simple`.

The weak later results are a reason to deprioritize this precise rule set, not to declare every pullback strategy impossible.

### 3. Channel breakout with volume — hourly swing trading

Require close above the highest high of the **preceding 55 bars**, volume z-score at least zero, RSI no greater than 78, and no bear regime. Bear means 50-period EMA below 200-period EMA together with a negative 20-bar price change. Apply the same extreme-volatility veto, next-open entry, signal-relative stop/target and 120-hour exit as the pullback. Candidate: `breakout_volume_simple`.

Shared execution rejects opening gaps larger than 0.5 ATR. The structure families require planned reward after costs of at least 1.5 times planned risk after costs and a maximum cost/risk ratio of 0.5. The ORB uses 0.8 for both thresholds. A three-loss streak triggers a six-hour structure-family pause; ORB uses 24 hours. Cooldown defaults are 15 minutes for the structure families and 390 minutes for ORB. Indicator formulas and complete parameters are frozen in the linked code and report JSON.

## What the research does—and does not—support

[Zarattini, Barbon and Aziz, 2024, opening-range study](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf) found that selecting unusually active stocks materially changed historical ORB performance. Its setup used a five-minute range and selected the top 20 eligible stocks by opening relative volume. The underlying filters included price above $5, prior 14-day average volume of at least one million shares and daily ATR above $0.50. This supports researching a daily stock-selection process. It does not validate our 15-minute, four-symbol, long-only adaptation. The paper also used shorts and leverage; its advertised returns cannot be imported into this account.

[Zarattini, Pagani and Wilcox, January 17, 2025 version, stock trend-following study](https://concretumgroup.com/wp-content/uploads/2026/02/Does-Trend-Following-Still-Work-on-Stocks.pdf) studies all-time-high entries with a wide volatility-based trailing exit on a broad historical equity universe. That is a reason to investigate slower breakouts that allow large winners to run. The paper also finds that frequent portfolio rebalancing can make the base implementation uneconomic for smaller accounts after costs, motivating turnover control. It is materially different from our hourly 55-bar breakout with a fixed target and five-day time limit. Its historical evidence is not proof that a new daily adaptation will work.

These are author-published research papers, not independent guarantees or forecasts. The next research priorities are my interpretation of their methods and the implementation gaps above.

## Next experiment, without expanding the app again

1. Keep Strategy Lab as the main workstream and merge/review the execution correction. Re-run old default-family reports; their zero entries may have come from the bug.
2. For day trading, obtain at least 12–24 months of complete one-/five-minute stock data and a historical eligible universe. Predeclare a five-minute ORB with opening relative-volume selection before looking at performance. Separate long-only results from any short/leverage version. Include spread, commission, slippage, gaps and rejected fills. The free short-window feed used here cannot supply that history.
3. For swing trading, predeclare one daily trend-breakout rule and a trailing exit, then test it over several market regimes with daily data. Do not call it the published all-time-high strategy unless its universe, history and rules actually match. This daily version has **not** been implemented or tested in this run.
4. Keep a new untouched chronological period for confirmation. Check results after costs and against buy-and-hold, inspect drawdown and concentration in a few trades, then forward-paper-trade unchanged rules. Twenty trades is an operational minimum in the existing app, not sufficient proof on its own.

There is no real-money recommendation from this screen. The concrete progress is a repaired backtesting blocker, a frozen comparison with actual data, and explicit reasons not to promote the current candidates.

## Reproduce or inspect

This directory contains the frozen `plan.json`, `run_study.py`, complete summary `results.json` and input/code hash `manifest.json`. The separate downloadable bundle with source snapshots and trade journals could not be uploaded. No API keys are included. Re-fetching Yahoo inputs can produce revisions or hit the provider's retention limits; hashes document the original inputs but are not a substitute for them.

Use a checkout containing the linked corrected code, install its requirements, and copy this research directory to a new output folder. Remove the copied `results.json` before running `python run_study.py --repo /path/to/Learning-algorithm`. Do not overwrite the original results. The runner downloads required inputs if `data/` is absent; an exact reproduction requires matching the original data hashes. It also accepts `--only SYMBOL:strategy_name` for one job at a time.
