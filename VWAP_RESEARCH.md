# VWAP mean-reversion research for CryptO

This adds **Advanced research → Test the Reddit strategy** and an offline runner.
It is a declared crypto adaptation, not a reconstruction of private source code.
No profit benefit has been established. It cannot qualify or install a model,
update existing learning, start monitoring, or submit orders.

## What the research suggests

The economic hypothesis is that a temporary price extension can reverse after
selling loses effectiveness. A persistent repricing can instead keep extending.
The important test is whether the confirmation improves net results at the same
risk and costs. Several correlated price indicators do not constitute independent
evidence of a reversal.

The [original post](https://www.reddit.com/r/Daytrading/comments/1wisune/quit_software_engineering_to_trade_futures_over_a/)
describes session VWAP extremes, a volume-profile level, delta divergence, and
closed 1m/5m/30m confirmation, with VWAP-based exits. The author's
[clarification](https://www.reddit.com/r/Daytrading/comments/1wisune/comment/pad25w7/)
does not disclose all thresholds or an unambiguous normalization formula.
The [earlier explanation](https://www.reddit.com/r/Daytrading/comments/1uefak9/why_you_should_stop_trading_patterns_and_feel_and/)
describes individual trade speed and sizes; one-minute OHLCV cannot recover that
sequence. The explanations therefore do not specify an exactly reproducible feed
and algorithm. Performance figures remain self-reported.

TradingView's [documented CVD calculation](https://www.tradingview.com/support/solutions/43000725058-cumulative-volume-delta/)
assigns each lower-timeframe candle's volume a direction using price. It is an
estimate, not exchange-reported aggressor volume. If signed minute volume is
divided by that same minute's volume, it becomes +1 or -1, removing volume size.
That is why this adaptation explicitly uses raw signed volume and normalizes the
*divergence* by the session CVD range available at confirmation. This is a research
choice, not a claim to match the author's normalization.

A higher CVD value at a later price low does not prove passive bid absorption.
It can reflect trading during an intervening rally or a changed price impact of
orders. [Order-book research](https://arxiv.org/abs/1011.6402) finds that depth and
order-flow imbalance matter for short-term price changes; that paper does not
validate this reversal strategy. Executed volume also does not measure outstanding
limit orders. TradingView's [volume-profile documentation](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/)
describes historical volume at prices. A low-volume node can be crossed quickly
or rejected; its presence alone does not establish support.

Two standard deviations measure dispersion under a chosen formula. They do not
give a 95% probability of a future bounce. VWAP can move toward price while price
continues falling. The experiment freezes targets at the signal to avoid silently
changing the intended payoff. Separate bar-based VWAP bands can differ across
timeframes, as [Sierra Chart explains](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=108&Name=Volume_Weighted_Average_Price_-_VWAP_-_with_Standard_Deviation_Lines).
Those differences are not three independent sets of trades.

## Declared experiment, before market results

`lab/vwap_research.py:PROTOCOL` is included in every export. No optimizer is used.
The numbers below are explicit starting hypotheses and have not been chosen from
profitable results. All four variants remain in the report, including failures.

| Part | Fixed rule |
| --- | --- |
| Data | Recorded, completed 1m Coinbase candles; no synthetic replacement or upsampling |
| Market/account | Long-only spot; independent $500 accounts with the app's risk, position cap and daily loss limit |
| Anchor | UTC midnight; at least 120 observed minutes from the session open |
| VWAP/bands | Volume-weighted HLC3 and weighted population variance, computed separately from completed 1m, 5m and 30m candles |
| Extension | A minute low below its then-known lower 2-sigma band during the preceding 30 minutes |
| Re-entry | All three band readings inside +/-2 sigma at a common 30m close; price below the 1m VWAP |
| Profile | Previous full UTC day's 48 HLC3-volume bins, smoothed across three bins; local peak >=1.25 times mean or positive valley <=0.75 times mean; touch within one bin width |
| Delta | Cumulative signed minute volume; flat bars use previous close then previous direction; session reset |
| Divergence | Two outside-band low pivots, each confirmed by two later bars; no more than 120 minutes apart; price lower, CVD higher by at least 10% of the session range known at confirmation |
| Expiry | Divergence expires after 30 minutes or a lower price low; no signal crosses a UTC session boundary |
| Trend variant | VWAP's preceding 30m change divided by current sigma must be >= -0.25 |
| Entry | Next recorded minute open plus execution friction; existing entry-gap guard retained |
| Stop | Lowest recent outside-band wick minus 0.1 current sigma |
| Exits | Half at signal-time VWAP, half at its upper 1-sigma band; fixed levels; original stop retained |
| Other exits | Four-hour time limit; final-window liquidation separately marked END; 30-minute cooldown |
| Costs | User fee per side, configured slippage plus assumed 0.05% half-spread; separate account with all costs multiplied by 1.5 |
| Payoff gates | Cost/risk <=0.8 and planned net reward/risk >=1; identical for every variant |
| Missing data | Invalid session produces no signals; incomplete prior day supplies no profile; an open account interrupted by missing minutes stops as incomplete |

The four variants are: bands alone; bands plus profile; those plus delta; those
plus trend. Earlier 70% and later 30% of elapsed history split at UTC midnight,
with independently funded accounts and no cross-window position carry. All
features are causal, but historical windows are **not certified unseen evidence**.
No weekday is excluded and no historical winner is promoted. The approach follows
the concern about repeated strategy selection described in
[The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Reading the economics

A 48% win rate with an average win three times the average loss mathematically
implies profit factor about 2.77, provided both figures describe the same sample
and cost basis. This consistency does not verify the Reddit results. Scaling out
half at 2R and half at 3R yields 2.5R on a complete winner, not 3R.

For illustration only, a 0.5% price stop on $500 notional is $2.50 before costs.
A hypothetical 0.5% total round-trip trading cost is also $2.50. Narrow stops can
therefore consume an entire unit of price risk in fees and execution friction.
Use the actual [Coinbase fee tier](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees);
this example is not a fee quote. The app's default 0.4% **per side** remains an
unconfirmed assumption until entered or synchronized by the user.

The shared simulator now supports isolated research callbacks and split exits.
Every partial exit pays its own fee. Stops win ambiguous stop/target minute bars;
stops gapped through fill at the adverse open. Signal prices cannot be filled on
the same historical close that creates the signal. This accords with
[TradingView's execution explanation](https://www.tradingview.com/pine-script-docs/concepts/strategies/).
Net excursion estimates that assume the whole position remains open are withheld
for partial-exit trades. These OHLC fills are still simulations, not executable
historical quotes or queue-position evidence.

## Run it

In the app, open **Advanced research**, enter one to three markets and the actual
fee, select the history length, and click **Backtest VWAP strategy**. Download the
comparison to retain all assumptions, data/source hashes, trade ledgers, rejection
counts and both cost scenarios. Downloads use a separate candle cache so they do
not overwrite another learning run's cache. Existing model state is untouched.

Offline, using recorded minute data:

```sh
python run_vwap_research.py --csv BTC-USD_1m.csv --symbol BTC-USD --fee 0.004 --out vwap-result.json
```

Or download from Coinbase's public API:

```sh
python run_vwap_research.py --coinbase --symbol BTC-USD --days 30 --fee 0.004 --out vwap-result.json
```

`--end YYYY-MM-DD` gives an exclusive historical UTC cutoff. CSV columns are
`ts,open,high,low,close,volume`, with timestamps in UTC milliseconds. Existing
5m/15m/1h/6h learning exports cannot reconstruct the required minute paths.

True aggressor delta is a separate future experiment requiring recorded trades.
Coinbase's [official market-trade schema](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/advanced-trade-asyncapi.json)
defines `side` as the **maker** side. An aggressor-sign calculation must invert
that side. That feed, and any backfilled trade history, is not implemented here.

## Verification and present limits — 20 September 2026

- Full Python suite: **408 passed**. After the final opening-gap target-ordering
  and UTC-boundary refinements, **32 targeted tests passed**, including one new
  regression (**409 distinct checks across these runs**).
- Both existing dashboard checks pass, including new zero-trade, error-escaping
  and comparison rendering cases. JavaScript/Python syntax, app route smoke
  checks and an offline CSV CLI fixture also pass. No browser visual review is
  claimed.
- New checks exercise future-data invariance, confirmed pivots, gap handling,
  weighted variance, next-minute entries, split exits, all fees, same-bar ambiguity,
  known opening target crosses, account reconciliation, API protection and
  preservation of existing model state. Fixtures are generated and supply no
  market-performance evidence.
- A direct Coinbase minute-data request returned HTTP 502. The actual CLI
  downloader was then tried for BTC-USD, seven days ending **2026-09-19 UTC**,
  and timed out. **No historical market comparison completed and no strategy
  profit figure is available.** There is no substitute-price fallback.
- The implementation is prepared on top of V11.16's draft, with no merge,
  deployment, active learning-run interruption or trading-account action.
