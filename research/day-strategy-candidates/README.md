# Day-trading candidates: rules and first comparison

Research date: September 29, 2026. **No candidate has demonstrated a tradable edge in our tests.**

Three explicit, long-only candidates are now available in **Backtest stocks**. This folder contains their fixed research plan, the input snapshots, every result and an offline replay script. They remain research-only even if a later run has positive returns. Nothing here enables orders or promotes a strategy to live trading.

## What we learned

Across the twelve new strategy–instrument combinations, the later window produced **15 qualifying setups, 3 opened trades and 12 entry rejections related to costs or insufficient net reward**. All three opened trades lost money. That is useful evidence about these rules and assumptions, but far too little evidence to estimate a reliable win rate or prove that an entire strategy family cannot work.

The most useful research distinction is between an entry pattern and the method for selecting stocks. An opening breakout on four fixed instruments is not a test of a strategy that ranks a broad universe for unusually active stocks each morning. More rules alone will not repair that difference.

## Sources and their limits

Sources were checked on September 29, 2026.

- [Zarattini, Barbon and Aziz: ORB study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284) — [author-hosted paper](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf). The study evaluates opening-range breakouts and selection using unusual opening volume across a broad historical stock universe. Its order triggers, daily-ATR stops, end-of-day exits, short positions and portfolio construction differ from our implementation. Our long-only, next-open, fixed-target tests are adaptations; the paper's returns are not our returns. The retest rule below is our hypothesis, not the paper's strategy.
- [Andrew Aziz: public VWAP teaching slides](https://bearbulltraders.com/wp-content/uploads/pdfs/speedtrader.pdf). Useful for defining VWAP-related setups and intraday context. Teaching charts do not establish performance after costs. The precise two-bar reclaim, volume threshold and stop rule below are our testable translation, not a claimed verbatim book strategy.
- [Zarattini, Aziz and Barbon: SPY intraday momentum paper](https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf). A distinct next research candidate: compare price with an intraday noise band estimated from prior sessions at the same clock time, with VWAP-related exits. This has not been implemented or backtested here. It would require its own fixed specification and honest disclosure of differences from the paper, particularly sizing and shorting.
- [Reddit: 5M chart discussion](https://www.reddit.com/r/Daytrading/comments/1f6g81l/) and [strategy discussion](https://www.reddit.com/r/Daytrading/comments/1ggpvw5/). Indexed excerpts supplied breakout/retest and VWAP ideas. Direct thread access, including the previously shared short Reddit link, was unavailable; this is not a claim to have read those entire threads. Unverified profitability claims were not used as evidence.

## Exact implemented rules

All times below are New York exchange time. Use regular-session 5-minute candles. Each strategy uses only completed earlier bars and prior sessions available at the decision time. The first qualifying signal consumes the session's one attempt, even if indicator warmup, a next-open gap or cost checks prevent a fill. There is no second attempt that day.

### 5-minute opening-volume breakout

Strategy ID: `orb_5m_rvol`. Version: `orb-5m-rvol-close-v1`.

1. Use 5-minute regular-session bars and 14 complete prior sessions for the opening-volume baseline.
2. The 09:30–09:35 bar must close above its open. Its volume must be at least 1.5× its prior-session average.
3. Take the first later close above that bar's high, from 09:40 through 11:00 New York time; entry is the next open.
4. Stop at the opening bar's low. Full target is signal close plus twice its distance to the stop; flatten at session close.
5. At most one signal per session. Next-open gaps and costs may reject it; there is no second attempt.

### 15-minute breakout and retest

Strategy ID: `orb_15m_retest`. Version: `orb-15m-retest-v1`.

1. Build the 09:30–09:45 high and low from complete 5-minute bars. Opening volume must be at least its prior 14-session average.
2. Record the first subsequent close above the range high. Do not enter on that breakout bar.
3. Within the next six bars, require low at or below the range high, close above it, and close above the candle's open.
4. Signal must close by 11:00 New York time. Enter next open; stop below the retest low by 0.1× the signal's 5-minute ATR.
5. Full target is signal close plus twice its stop distance. One signal per session; flatten at the close. The retest rules are our hypothesis, not the paper's implementation.

### VWAP reclaim

Strategy ID: `vwap_reclaim`. Version: `vwap-reclaim-v1`.

1. Compute session VWAP from cumulative typical-price × volume, resetting at 09:30 New York time. This bar approximation is not tick VWAP.
2. From 10:00 through 12:00, require each of the two preceding candles to close below its own then-current VWAP.
3. The signal must close above current VWAP, above the preceding high and above its own open.
4. Cumulative volume must be at least its average at the same session minute over 14 complete prior sessions.
5. Enter next open. Stop below the lowest low of the signal and preceding two bars by 0.1× 5-minute ATR; full target is twice the signal-close stop distance. One signal per session; flatten at close.

### Shared execution and data checks

- A signal is decided at the candle close. A buy fills at the next scheduled bar's open with adverse spread/slippage. Signal prices are never treated as fills.
- The full target is calculated from the signal close, not moved to manufacture 2R after a gap. The actual filled reward/risk can therefore differ.
- Stop, target and session-close execution use the existing shared engine. If both stop and target are touched inside a bar, the stop takes precedence. Stops that gap are filled at the worse available price. Intrabar order flow remains unknown with five-minute candles.
- Missing bars invalidate the affected session for new candidate signals and reset the 14-session volume history. A missing whole session is detected using calendar-derived expected next timestamps. No bars are interpolated. An unresolved position at a gap prevents valid account-performance reporting.
- Session VWAP is a typical-price/volume approximation from bars, not tick-by-tick VWAP. Relative-volume baselines contain exactly 14 complete, contiguous earlier sessions and never include the current session.
- There is no point-in-time news filter, historical universe ranking, short selling or leverage in these tests. These omissions matter when comparing with published studies.

## Fixed comparison and results

The plan was written before running these new candidates. The same four instruments and frozen inputs were already examined in our [earlier stock screen](../stock-strategy-screen-2026-09-29/README.md). Consequently, **the whole new comparison is exploratory**, including the column labelled “later.” It is not an untouched out-of-sample confirmation.

Each input contains 3,120 observed five-minute candles over 40 regular sessions, August 3–September 28, 2026. The provider/calendar check found no missing scheduled five-minute candles within this requested snapshot. This is provider coverage, not independent verification of every price. The later window contains 936 candles across just 12 sessions, September 11–28. It can contain at most 12 signals per candidate/instrument, before all other filters.

Settings were held fixed: $1,000 starting balance for each independent test; fractional shares; 0.5% account risk per trade; 95% maximum notional allocation; 2% session loss limit. Fees are 1 basis point, slippage 5 and half-spread 2 **per side**: 16 basis points round trip before differences in entry/exit prices. The stress comparison multiplies all three by 1.5, approximately 24 basis points round trip. These are declared modeling assumptions, not measured brokerage fills. The existing entry guard requires at least 1R potential net reward and modeled costs no greater than 0.5R.

The chronological split is 70/30 with 240 initial indicator-warmup bars and the additional 14-session volume requirement. Each window starts at a fresh balance. Data are Yahoo's normalized, split-adjusted OHLC snapshots; dividends and taxes are excluded. These results are separate accounts, not a combined portfolio.

| Candidate | Symbol | Earlier return / trades | Later return / trades | Later at 1.5× costs / trades | Later setups / entries |
|---|---|---:|---:|---:|---:|
| 5m opening-volume breakout | SPY | 0.000% / 0 | 0.000% / 0 | 0.000% / 0 | 1 / 0 |
| 5m opening-volume breakout | QQQ | -0.276% / 1 | 0.000% / 0 | 0.000% / 0 | 2 / 0 |
| 5m opening-volume breakout | IWM | 0.000% / 0 | 0.000% / 0 | 0.000% / 0 | 0 / 0 |
| 5m opening-volume breakout | NVDA | 0.000% / 0 | -0.500% / 1 | -0.500% / 1 | 1 / 1 |
| 15m breakout/retest | SPY | 0.000% / 0 | 0.000% / 0 | 0.000% / 0 | 0 / 0 |
| 15m breakout/retest | QQQ | 0.000% / 0 | 0.000% / 0 | 0.000% / 0 | 2 / 0 |
| 15m breakout/retest | IWM | 0.000% / 0 | 0.000% / 0 | 0.000% / 0 | 0 / 0 |
| 15m breakout/retest | NVDA | -0.997% / 2 | 0.000% / 0 | 0.000% / 0 | 0 / 0 |
| VWAP reclaim | SPY | 0.000% / 0 | 0.000% / 0 | 0.000% / 0 | 4 / 0 |
| VWAP reclaim | QQQ | 0.000% / 0 | -0.500% / 1 | 0.000% / 0 | 2 / 1 |
| VWAP reclaim | IWM | -0.077% / 1 | -0.185% / 1 | 0.000% / 0 | 2 / 1 |
| VWAP reclaim | NVDA | -0.384% / 3 | 0.000% / 0 | 0.000% / 0 | 1 / 0 |

A 0% result with zero trades is not a successful strategy. The two VWAP trades that disappear under higher costs were rejected before entry; their disappearance does not demonstrate resilience. The underlying reports retain every trade, fee, window boundary, rejection and source-quality field. No symbol was dropped and no threshold was adjusted after seeing these returns.

## Research priority and next evidence needed

1. **First priority: opening-volume breakout with point-in-time stock selection.** My research preference is to test the selection mechanism explicitly: each day, rank a historical universe using only information available after the opening bar. Include delisted securities and apply liquidity/corporate-action rules before ranking. Compare the frozen single-stock baseline with the full selection hypothesis; do not describe the existing four-instrument test as that replication.
2. **Keep VWAP reclaim as a separate benchmark.** It provides a distinct reclaim entry, but this screen does not support trading it. Retain losing and no-trade observations rather than searching only for favorable tickers.
3. **Lower priority: breakout/retest.** It is a transparent discretionary-style hypothesis, but its very low event count and weaker source evidence warrant less research effort until a longer sample exists.
4. **Then test the separate SPY intraday momentum family.** Specify its timing, bands, exits, financing and allowable position sizes before seeing results. Avoid turning this sample into an open-ended parameter search.

The immediate data requirement is 12–24 months or more of reliable intraday history across varied market conditions; elapsed history alone will not establish an edge. Also obtain enough qualifying trades, point-in-time symbol membership, and quote/fill observations to estimate costs. This workspace currently has no configured Alpaca or Massive credentials for deeper history; that says nothing about the Render service's private settings. No paid feed was purchased.

Freeze any next specification, evaluate rolling chronological periods, compare against appropriate exposure-matched and passive benchmarks, inspect concentration by symbol/day, stress realistic costs and gaps, and then reserve a genuinely untouched forward-paper period. Confidence intervals should account for clustering by day; a handful of trades is not a useful probability estimate. Do not lower evidence thresholds merely to get a passing label.

## Reproduce and inspect

From the repository root, using the project's installed Python dependencies:

```sh
python research/day-strategy-candidates/run_study.py --output /tmp/day-strategy-replay
```

Choose a new output directory: the script refuses to overwrite existing evidence. It verifies the compressed input checksums, uses the same application backtester, and records code, plan, runner, dependency and input identities. It does not call market-data providers or brokerage APIs.

- [Fixed plan](plan.json)
- [Input provenance and SHA-256 checksums](input_manifest.json)
- [All twelve results](outputs/results.json)
- [Execution manifest](outputs/manifest.json)
- Individual journals and metrics: `outputs/reports/`
- [Software verification](verification.md)

The website update exposes these candidates and their rules when deployed. This saved study is a repository artifact; it is not silently imported as a user's website job history. The changes were prepared on the existing draft pull request. Render deployment and live trading are not part of this study.
