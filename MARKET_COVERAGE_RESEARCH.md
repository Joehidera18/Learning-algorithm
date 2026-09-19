# Broader market and timeframe studies — 19 September 2026

This note records the earlier V11.10 source checkpoint. The later [predeployment review](PREDEPLOY_REVIEW.md) corrects time-exit labels and adds new pinned LTC comparisons. The eight studies below retain their original source hash and results.

The prior dashboard requested three years on one configured timeframe for thirteen suggested coins. It could accept twenty markets but keyed each study and checkpoint only by coin. Simply looping through additional timeframes would overwrite saved reports, reset another timeframe's checkpoint and potentially replace the model used by the forward account.

## Implemented coverage

The dashboard now suggests 30 Coinbase USD tickers, accepts up to 60, and defaults to separate 15-minute, hourly and 6-hour studies with five years requested. A 5-minute study is optional. Existing saved coin selections remain available; **Use suggested 30 coins** loads the expanded list. The submitted coin list, timeframe selection and lookback persist across restarts.

| Study interval | Maximum requested history | New dashboard default |
| --- | ---: | --- |
| 5 minutes | 365 days | Optional |
| 15 minutes | 1,825 days | Included |
| 1 hour | 2,920 days | Included |
| 6 hours | 2,920 days | Included |

These are application download/workload limits, not promises that the exchange has complete history. Requests can select one, three, five or eight years. Each report records the requested days, the effective interval limit, actual dates, observed candles and coverage percentage. For example, choosing eight years still limits the 15-minute study to five years, and that difference is shown. At least 3,000 valid completed candles remain required; six-hour studies need at least 750 observed days. All timeframes use the existing completed daily context, with its availability and warmup checks.

The suggested list is BTC, ETH, SOL, HBAR, XRP, XLM, ADA, DOGE, AVAX, LINK, LTC, BCH, DOT, UNI, AAVE, ATOM, NEAR, FIL, ETC, ALGO, XTZ, ICP, INJ, OP, ARB, RENDER, APT, SUI, SHIB and PEPE, each quoted in USD. Suggestions are not investment recommendations or a claim that all listings are currently available. Current product metadata is checked once per study queue. Unknown, inactive, disabled, auction-only, cancel-only and stablecoin markets are reported as unavailable and do not stop the other studies. If the metadata request fails, the report records that missing check and the candle API still has to provide observed prices. No fabricated fallback is used.

## Model and result isolation

- Each coin/timeframe gets separate settings, candle files, report/model fingerprints and checkpoints. Lookback changes invalidate the appropriate reuse scope. A checkpoint for an interrupted hourly study survives a completed 15-minute study and a controller restart.
- Only the currently configured decision interval, at the current cost settings, can install or remove its forward profile. Secondary-frame research cannot overwrite it. Six-hour models are explicitly research only: the application does not allow that decision interval in the forward account and the installer rejects it even if passed a matching settings dictionary. Coarser OHLC bars hide exit timing and intrabar event order, so enabling six-hour trading needs separate execution validation. The app does not automatically choose whichever timeframe reports the largest backtest profit.
- Completed studies from other coins and timeframes remain visible when automatic reviews run. Progress counts studies separately from coins. Automatic learning expands to ten scanner markets at the configured decision interval and retains the last selected lookback; explicit historical practice runs the selected multi-timeframe plan.
- Market hours are the union of observed candle coverage per coin. The same hour represented at several timeframes counts once. Example counts and simulated accounts can overlap and are not independent observations or one pooled account.
- Earlier reviewed price endpoints are retained per coin across new timeframe and lookback scopes. Re-aggregating already examined prices does not turn them into unseen confirmation data.
- A shorter download preserves older cached observations, including the daily context needed for another timeframe's exact candle/report export. Revisions to cached prices still cause an old export's hash check to reject a mismatch.

## Data-source research

[Coinbase's candle documentation](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) lists native 5-minute, 15-minute, hourly, 6-hour and daily buckets. It limits each HTTP request to 300 candles and explains that intervals without ticks may be absent. The client keeps its existing rate limiting, pagination and completed-candle filtering; this revision adds native 6-hour support throughout downloads, repair, research and export. Missing six-hour candles can be reconstructed only from six complete observed hourly candles.

[Coinbase's product documentation](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-all-known-trading-pairs) exposes current listing status and trading restrictions. That supports checking availability at run time instead of treating a static suggested list as authoritative. These checks do not eliminate survivorship bias: this downloader studies currently available USD products, and failed/delisted historical assets would need suitable archived data. The existing CSV research command can read such supplied histories without claiming their source was independently verified.

The online documentation was accessible during development. Direct access to the public Coinbase product API timed out from the development environment. Therefore, no new-coin or earlier external candle download is claimed in this revision. After deployment, the application requests that coverage when practice is run. Server connectivity, exchange availability, history length and persistent storage determine what can actually be collected.

## Reproducible studies on the supplied data

The offline validation uses all four distinct supplied coin datasets: LTC, DOT, XRP and AVAX. For each, it verifies the original intraday and daily hashes and forms fixed hourly and six-hour candles only when every required 15-minute subcandle is observed. Incomplete edge buckets and buckets containing missing observations are omitted. The same daily prices, costs, strategies and risk limits are retained. Each timeframe trains and evaluates its own model; there is no parameter search or promotion of the best-looking result.

```sh
python scripts/study_timeframe_coverage.py \
  --bundle /path/to/LTC-bundle.zip \
  --bundle /path/to/DOT-bundle.zip \
  --bundle /path/to/XRP-bundle.zip \
  --bundle /path/to/AVAX-bundle.zip \
  --out-dir /path/to/full-results \
  --summary /path/to/timeframe-coverage.json
```

All source prices are already reviewed. The script marks the complete source endpoint as reviewed, checks that no resulting report qualifies, and checks model observations against development plus later completed practice outcomes. Aggregation is a different view of existing data, not additional independent market history. Each ordinary and higher-cost account begins with its own simulated $500, and differing timeframes can have different final-window boundaries.

## Measured results

The [eight-study record](research_baselines/timeframe-coverage.json) contains exact input/source hashes, dates, costs, ordinary/higher-cost metrics and rising/falling/sideways example counts.

| Coin | Timeframe | Complete candles | Learned outcomes | Final account trades | Ordinary net | Higher-cost net |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LTC-USD | 1h | 26,261 | 4,442 | 0 | $0.00 | $0.00 |
| LTC-USD | 6h | 4,372 | 580 | 0 | $0.00 | $0.00 |
| DOT-USD | 1h | 26,248 | 3,760 | 0 | $0.00 | $0.00 |
| DOT-USD | 6h | 4,359 | 372 | 0 | $0.00 | $0.00 |
| XRP-USD | 1h | 26,261 | 3,794 | 1 | $-3.75 | $-4.59 |
| XRP-USD | 6h | 4,371 | 421 | 0 | $0.00 | $0.00 |
| AVAX-USD | 1h | 26,241 | 3,957 | 0 | $0.00 | $0.00 |
| AVAX-USD | 6h | 4,356 | 421 | 0 | $0.00 | $0.00 |

The studies learned 14,939 development outcomes plus 2,808 later practice outcomes, for 17,747 total model observations. These overlap across candidates and timeframes. Seven final accounts opened no selected trade; the XRP hourly account lost $3.75 at ordinary costs and $4.59 at higher costs. All eight remain unqualified. There is no demonstrated gain in profitability from adding these timeframe views.

The candidate set remains long-only and mostly favors rising or sideways conditions. Bear-regime completed examples are rare in these replays, and three of the six-hour studies have none. More dates and coins do not by themselves establish that the model can trade downturns well. These counts are visible in each report so sparse experience can be identified.

Replay lab-source SHA-256: `415593a1742073c96bf5d9b570d913f831d607b3e44fa29516f6147e32efaef7`. After the replay began, only orchestration changed: automatic reviews were made to retain the selected lookback, and six-hour models were restricted to research. The directly invoked learning/execution code, default costs and aggregation are unchanged. Final lab-source SHA-256: `3670f2704c3efcef824dbca17e77d6e3a85fe54bcc88a162e3cae20cdd775bc7`. The final orchestration is covered by dedicated regressions. The separate [continuity study](CONFIRMATION_CONTINUITY_RESEARCH.md) retains its earlier exact source fingerprint and identical-input LTC comparison.
