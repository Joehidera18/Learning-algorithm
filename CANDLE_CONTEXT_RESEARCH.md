# V11.6: fuller entry context and honest loss severity

## Declared change before the comparison

This revision tests one fixed feature expansion against V11.5 on the supplied DOT and AVAX snapshots. It also corrects the clipping of economic loss estimates. No parameter search, per-market winner selection, new entry strategy or risk increase is authorized by these comparisons. The previous break-even exit model remains an independent research experiment.

The 19-input adaptive learner omitted useful inputs already computed by the candle engine. Add eight fixed-scale inputs: upper and lower wick fractions (0 to 1), RSI change (divided by 20), distance to preceding 20-bar resistance and support (each divided by 3 ATR), distance to the existing rolling VWAP proxy (divided by 3 ATR), ATR regime minus 1 (divided by 1.5), and preceding compression (0 or 1). Signed scaled values are bounded to [-1, 1]. Preserve all original indices, candidates, fees, entry conditions and account limits. Indicators use only completed signal candles; support/resistance exclude the current candle. These are candidate predictors, not claims about why a particular trade lost.

The earlier learner limited realized returns to +/-3 R in recent economic memory and capped prediction residuals before measuring squared error. A large gap loss could consequently look much smaller in decision statistics than in the account ledger. Retain raw realized net R in recent returns, context means/variance and the pre-update squared residual. Bound only the optimization step and model scores. This separates training stability from honest loss measurement. R is the original modeled net stop risk; fees are already included and must not be deducted twice. Numerically unusable labels are rejected before any state changes.

Both models must be rerun chronologically on the exact same supplied candles, completed daily context, costs and reviewed-history boundary. All report-19 history remains reviewed; an apparent improvement here is research reuse, not fresh confirmation or permission to trade. Record all results, including regressions, without picking a winning market or altering scales after inspection.

## Research basis

- [Scikit-learn's SGDRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDRegressor.html) explains robust loss functions that limit the influence of large residuals. The lightweight learner uses a bounded residual update without adding scikit-learn as a dependency. Raw risk statistics remain separate from that optimization rule.
- [Scikit-learn's time-series validation guidance](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) motivates chronological training and evaluation. Existing exit-time label release, purge periods and future-candle protections remain required.
- [Lo, Mamaysky and Wang's original research](https://www.cis.upenn.edu/~mkearns/teaching/cis700/lo.pdf) studies systematic representations of price patterns in historical US equities. It motivates testing explicit measurable context, but does not validate these features in crypto or establish profits after this account's costs.
- [Coinbase's Advanced fee documentation](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees) distinguishes maker and taker execution and the fee tier at order time. Keep the supplied fee assumptions unchanged; no lower fee tier or maker fill is assumed to make a replay look better.

## Validation and results

The exact supplied 15-minute snapshots and separate daily candles were compared with pinned V11.5. Ordinary-cost selected trades are identical in both markets. Each row is a separate $500 simulation; the AVAX bundle is the older report-17 snapshot, not report-19 AVAX candles.

| Snapshot | V11.5 ordinary net | V11.6 ordinary net | V11.5 at 1.5x costs | V11.6 at 1.5x costs | Qualified |
|---|---:|---:|---:|---:|---|
| DOT, report 19 | $0.00 / 0 trades | $0.00 / 0 trades | $0.00 | $0.00 | No |
| AVAX, report 17 | -$5.61 / 3 trades | -$5.61 / 3 trades | -$5.99 | -$4.33 | No |

AVAX loses $1.659514 less under higher costs, and its second earlier fold rises from $5.582693 to $7.826429. Its other two earlier folds are unchanged at $0 and $0.961763. DOT's earlier folds remain -$1.384411, $0 and -$3.75. These are separate windows, not returns to add together. The ordinary selected-account-feedback controls remain $0 for DOT and -$6.508937 for AVAX; AVAX's higher-cost control changes from -$5.538450 to -$5.479984. The separate break-even exit experiment has the same final ordinary/higher-cost results as the revised primary model in these snapshots; it remains unable to control trading.

Development examples stay at 10,841 for DOT and 11,270 for AVAX. Candidate definitions, training diagnostics, costs, candle/daily hashes and test boundaries match the baseline. The change is what the adaptive model can learn from those examples and how it measures loss severity. Neither final ordinary-cost result improves, both markets remain unqualified, and there is no fresh confirmation window. No new candles were downloaded in this revision and no threshold or market-specific choice was changed after the comparison.

**234 Python tests passed in 71.381 seconds**, including all earlier account/execution tests. Five added tests verify richer-feature discrimination, old-vector rejection, full loss moments, finite bounded weights, exact restart round-trips, completed-candle timing, agreement between compact and full features, and exclusion of exit/future information. A worker-completion test initially exceeded its five-second deadline while both full replays ran concurrently; it passed alone in 2.141 seconds. Its completion budget now matches the existing 30-second integration-test budget, and the full suite then passed. This is not a training-latency guarantee.

Both dashboard checks passed against the actual JavaScript, including report 19, old reports and account separation. Python compilation, JavaScript syntax and whitespace checks passed. These are software and mocked-document checks; the hosted/mobile site was not visually verified and no orders or deployment were performed.

The [saved comparison](research_baselines/candle-context-comparison.json) records exact inputs, source hashes, earlier folds, controls and qualification failures. The model version is `online-net-r-v9-candle-context`, engine is `market-structure-v11.6-candle-context`, and report schema is 11. Historical practice must be rerun after deployment. Existing account histories remain intact.

## Reproduction

Create a separate V11.5 checkout at commit `6718a89164bd383c825594f6cb3551ece04b8014`. The first command records the baseline on unchanged attachments; the second uses V11.6 and verifies the same inputs before comparing its actual decisions. Run from the V11.6 checkout and substitute absolute paths for the placeholders.

```bash
python scripts/compare_exit_learning.py --repo /path/to/v11.5 --bundle "DOT-USD_15m_learning-data 5.zip" --reviewed-report "learning-results 19.json" --out dot-v11.5.json
python scripts/compare_candle_context.py --bundle "DOT-USD_15m_learning-data 5.zip" --reviewed-report "learning-results 19.json" --baseline dot-v11.5.json --out dot-v11.6.json --summary dot-context-comparison.json
```

Repeat once with `AVAX-USD_15m_learning-data.zip` and distinct AVAX output filenames. This is the fixed two-market comparison, not a parameter search. After publication, evaluate subsequent prices through the app's existing qualification process before treating the revised model as a trading candidate.
