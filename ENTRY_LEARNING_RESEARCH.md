# Entry prediction accountability and conditional selection study

## Problem and fixed design

The completed V11.6 report contains 146,907 development examples across 13 markets, but just 21 selected final-period trades: five wins and sixteen losses. Those separate $500 simulations won $29.3167, lost $55.4106 and netted -$26.0939. None qualified. Six selected losses had little follow-through and seven gave back gains; these observations describe price paths, not proven causes. Eighteen selected trades used daily trend momentum; three used support/RSI reclaim.

The old ranking error used a prediction computed when an outcome arrived. The model may have learned other outcomes while that position was open. That optimizer residual is useful for fitting, but it is not the forecast error actually made before entering.

V11.7 freezes each selected or independent-practice entry forecast. It evaluates the full net outcome at normal closure, preserving fee costs, large losses and exactly zero rewards. Model components retain both optimizer errors and entry forecast errors. With at least the existing 30-sample minimum, the latter RMSE divided by the square root of the effective sample count can raise the ranking margin. The existing cap of 100 observations is retained. The margin cannot shrink because of this new statistic. No new threshold search, reward bonus, stop widening or leverage change is introduced.

Independent candidate runs now release each candle's outcomes before the following candle's entry forecasts, even during bulk replay. Same-clock outcomes keep candidate-index ordering. This makes bulk and incremental learning identical. Initial offline development labels do not invent entry forecasts: the entry audit begins where a chronological model is actually making them.

Entry features and the SGD reward update are unchanged. Paper and Coinbase error feedback follows the existing single journal-close transaction and account separation. Forward forecasts record the actual decision clock separately from the candle close, allowing legitimately known outcomes received between those times; replay forecasts still use the signal close. A saved forecast may update error statistics, but cannot add another reward or trade. Closed forecast errors are separate from report-only RMSE summaries. Frozen-model diagnostics do not learn.

## One experiment that did not justify promotion

A broad recent-return veto can reject a setup even if its contextual net estimate minus its error allowance is positive. One declared variant removes only that veto. Cost filters, the context adjustment itself, sample minimum, error margin, daily loss limit, sizing, stops, targets and qualification remain.

The initial probe used V11.6 fitting with that single veto removed, before the entry-error correction. Final DOT, XRP and AVAX results did not improve. Earlier DOT and XRP periods became worse; an AVAX period improved. These mixed results do not justify changing the trading rule. V11.7 keeps this variant in a separate experimental account. Its exported summary cannot install a model, grant eligibility or choose a winner for a market. A mismatched experimental state is rejected by the trading policy loader.

The new primary learner and its conditional variant are compared without a parameter sweep on the supplied DOT, XRP and AVAX bundles. Those prices have already been reviewed; they cannot supply independent confirmation. The whole-account break-even exit experiment remains separate as well.

## Prediction audit

The report separates selected account exits from overlapping candidate examples. It gives mean forecast, mean realized net R, optimism bias (forecast minus actual), mean absolute error, RMSE, and a zero-return forecast benchmark. Smaller RMSE means better squared-error forecasting on the observed sample; it does not prove calibration, profitability or independent evidence. A near-break-even return retains its true sign and size. Cold, missing, end-mark and unresolved gap records are excluded from scoring.

Paper journal rows also show the saved entry estimate beside the realized net R. R is net dollars divided by initial dollar risk, not a probability or guaranteed payoff.

## Data and sources

The new DOT bundle has 105,049 recorded 15-minute candles, 71 missing intervals, and 1,125 continuous completed daily candles. Canonical hashes match the report. Duplicate uploads are byte-identical. A new direct Coinbase request for a 25-interval gap timed out in this workspace; no candles were added or imputed. Earlier uploaded XRP and AVAX bundles support additional comparisons; the other ten markets were reviewed from their exported reports, not replayed locally.

- [scikit-learn: regression scoring](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics) explains squared error for evaluating mean forecasts. This supports measuring actual saved forecasts against outcomes; it does not validate our strategy.
- [scikit-learn: time-series cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-of-time-series-data) explains why future observations should test models fitted on earlier data. Our chronological boundaries, purged labels and fresh-confirmation rules remain.
- [Vowpal Wabbit: contextual bandits](https://vowpalwabbit.org/docs/vowpal_wabbit/python/latest/tutorials/python_Contextual_bandits_and_Vowpal_Wabbit.html) describes decisions conditional on observed features and feedback from outcomes. It motivates testing conditional selection, not removing financial risk controls. Our simulated candidate outcomes are not randomized real-world bandit observations or unbiased off-policy estimates.
- [Coinbase: product candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) documents incomplete candle history and omitted no-tick intervals. This does not identify the cause of each observed gap, and does not justify inventing OHLC paths.

## Reproduction

Use `scripts/compare_entry_learning.py` with a checkout of V11.6 (remote commit `8ed823d5a64f37199681dbfd7701c7bbc6761879`, source tree `40d6bf4cf55fe2ed08bdc5570312f647ce644258`) for the baseline. Then use the revised checkout, identical bundle and reviewed report, and `--baseline` with the first output. Both runs use the completed report's endpoint as their reviewed boundary.

```sh
python scripts/compare_entry_learning.py --repo /path/to/v11.6 --bundle /path/to/bundle.zip --reviewed-report /path/to/completed-report.json --out /path/to/baseline.json
python scripts/compare_entry_learning.py --repo . --bundle /path/to/bundle.zip --reviewed-report /path/to/completed-report.json --baseline /path/to/baseline.json --out /path/to/revised.json
```

The script checks canonical candle hashes, identical inputs, cost signatures, training diagnostics, resolved-label counts and test boundaries. It records source hashes, account outcomes, higher-cost runs, earlier periods, selected-trade feedback controls and both research experiments. No comparison can authorize trading.

## Measured results

These are paired replays of identical supplied prices and costs. Every row starts with its own $500 account. This release improves prediction accountability, but did not improve these final-period account profits.

| Market | V11.6 primary net | V11.7 primary net | Trades | V11.7 higher-cost net |
| --- | ---: | ---: | ---: | ---: |
| DOT | $0.00 | $0.00 | 0 | $0.00 |
| XRP | -$6.03 | -$6.03 | 5 | $0.00 (no trades) |
| AVAX | -$5.61 | -$5.61 | 3 | -$4.33 |

Primary earlier-period results are unchanged too. The conditional experiment's final results match the primary on these three bundles. Earlier DOT periods changed from -$1.38 / $0 / -$3.75 to +$0.47 / $0 / -$11.17; XRP's comparable complete earlier periods changed from -$0.83 / -$1.28 to -$8.29 / -$1.28. One AVAX period improved from +$7.83 to +$15.11; its other two periods were unchanged. The first XRP period remains incomplete because a position crossed missing candles. These mixed results support keeping the experiment separate.

The new entry audit exposes overprediction among the selected trades:

| Market | Scored selected exits | Mean predicted net R | Mean realized net R | Optimism bias | Forecast RMSE | Zero-forecast RMSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| XRP | 5 | +0.323 | -0.319 | +0.642 | 1.238 | 1.091 |
| AVAX | 3 | +0.422 | -0.499 | +0.921 | 1.138 | 0.867 |

These are tiny selected samples; they cannot support a fitted correction or a profit claim. Across overlapping independent practice, the audit scored 1,948 DOT, 2,494 XRP and 2,280 AVAX exits. Their forecasts were better than zero in RMSE overall, while the selected subsets were worse. Negative forecasts on many rejected setups therefore cannot by themselves establish the quality of the few positive entry decisions.

The separate break-even experiment retains XRP's +$15.32 ordinary result and -$7.47 higher-cost result. Neither it nor the conditional experiment qualifies or controls trading. There are no later-than-reviewed candles in these comparisons, no newly downloaded data, and no real account performance measurements.
