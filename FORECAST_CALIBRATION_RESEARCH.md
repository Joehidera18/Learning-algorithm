# V11.8: chronological forecast learning

## Problem and fixed hypothesis

The completed V11.7 report (`learning-results 4.json`, SHA-256 `80f9ad9adea71d60761ba9ca278116b356614aeed438980ed406c4d4fcc8cbe9`) contains 21 selected final-period trades across 13 independent $500 simulations, with five winners, sixteen losers and net loss $26.09. Selected estimates average +0.3548R; outcomes average -0.3291R. The 32,124 overlapping candidate examples mostly predict negative returns; their aggregate error does not establish accurate positive entry predictions.

V11.7 saves entry forecasts during later tests and forward journals. Its earlier development labels update the return model but do not supply entry forecasts. V11.8 adds a chronological event replay: predict at the entry timestamp, learn a net result only when its exit candle has closed, and preserve the earlier prediction even if other trades finish in between. Closures available at a timestamp precede new decisions at that timestamp. Training rewards are still counted once. Unresolved/gap-censored positions and end marks do not become labels.

The second change is a fixed, modest residual correction. For each strategy parameter set, group saved **raw** forecasts by the existing cost buckets and the existing forecast bands (nonpositive, above zero through 0.5R, above 0.5R). After both 30 observations and 30 effective samples, apply the exponentially weighted average of `actual net R - raw entry estimate`, shrunk by `effective / (effective + 50)`. Reuse the existing 50-observation half-life and 100-effective-sample cap. These values and grouping rules are specified before the V11.8 performance replay; no threshold search or selection by reported P&L is performed.

Correction can increase or decrease an estimate. Sparse groups retain the base forecast. Cost contexts do not borrow residuals from each other. Economic residuals retain full loss severity; the final estimate remains bounded to the existing [-3, 3] range. Corrections learn against raw estimates, avoiding feedback that would repeatedly undo an earlier correction. The existing error margin, costs, risk sizing, daily halt, candidate strategies and qualification checks remain in place.

**Decision after the fixed initial trial:** the correction slightly worsened final-period candidate forecast RMSE on DOT and XRP, and slightly improved it on AVAX. Positive-forecast groups were generally too sparse to activate it. It is therefore retained as a measured experiment, **disabled in the default policy**. The primary change is earlier, causal entry-error learning. No threshold or group was retuned to force a profitable result. This is a research decision made after seeing reused data; it is not independent confirmation.

Default entry records contain both the actual forecast and a trial correction, with an explicit `calibration_applied` flag. Raw-versus-trial errors use the same completed examples, even when the trial does not control the account. A model with experimental corrections enabled cannot load as the ordinary trading model, cannot pass approved-profile checks, and always receives a disqualifying research-only reason in its report.

## Research grounding and limits

- [Gneiting and Resin, Regression Diagnostics meets Forecast Evaluation](https://arxiv.org/abs/2108.03210): calibration of point forecasts concerns agreement between forecasts and outcomes, including conditional behavior. This motivates examining forecast groups instead of only a pooled error. The small online residual heuristic here is our implementation hypothesis, not their isotonic-regression procedure or a theorem about this trading model.
- [scikit-learn: avoiding data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage): information unavailable at prediction time must not enter fitting. The entry/closure event ordering and future-outcome mutation tests enforce that rule.
- [scikit-learn: regression metrics](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics): errors compare predicted and realized values. Raw and corrected RMSE are reported on the **same entries**, including groups defined by the raw forecast. They do not measure the return of a second trading policy.

Market examples are serially dependent and different candidate simulations overlap. Effective sample counts are stabilizers, not numbers of independent bets or calibrated confidence levels. Forecasts are net-return estimates, never success probabilities. Better average forecast error can coexist with worse trading results. The reviewed windows cannot supply independent evidence of future profit.

## Reproduction

Run `scripts/compare_forecast_calibration.py` first against pinned V11.7 (GitHub tree `e2208b6948fac5a553b1ca9ae706515e5d343622`, merge commit `c1cec2a0d7797974eb6ec85a13f7f28db0f09c49`), then against this checkout with the baseline output. Use identical candle bundles and `learning-results 4.json` as the reviewed report for both. The script records input/source hashes and checks candle identities, costs, label counts, training diagnostics and test boundaries. Outputs and ordinary/higher-cost comparisons must be reported regardless of direction.

```sh
python scripts/compare_forecast_calibration.py --repo /path/to/v11.7 --bundle /path/to/bundle.zip --reviewed-report /path/to/learning-results-4.json --out /path/to/baseline.json
python scripts/compare_forecast_calibration.py --repo . --bundle /path/to/bundle.zip --reviewed-report /path/to/learning-results-4.json --baseline /path/to/baseline.json --out /path/to/revised.json
```

The V11.8-only `--experimental-correction` switch reproduces a separate corrected policy for research. It is not a dashboard setting and cannot authorize trading. The normal run already scores its prospective correction alongside the actual forecast without changing decisions.

Engine `market-structure-v11.8-calibration`, policy `online-net-r-v11-calibration`, report 13 require fresh practice and invalidate incompatible label checkpoints. Existing price history and account records are retained. All supplied V11.7 endpoints are registered as reviewed history. No replay, summary or alternate experiment can bypass qualification or authorize orders.

## Measured results

Final-source paired replays use the same ordinary/higher costs and the same reviewed boundary in both versions. Each row is its own $500 historical account:

| Market | V11.7 final net | V11.8 final net | Trades before → after | V11.8 higher-cost net |
| --- | ---: | ---: | ---: | ---: |
| DOT | $0.00 | $0.00 | 0 → 0 | $0.00, no trades |
| XRP | -$6.03 | -$4.98 | 5 → 4 | $0.00, no trades |
| AVAX | -$5.61 | -$5.61 | 3 → 3 | -$4.33 |

The XRP improvement is $1.0576. Entry timing and later account paths change, so it is not simply one deleted losing trade. The raw forecast correction is disabled in these results; only the chronological development forecasts and their entry-error evidence affect the default learner. Earlier primary folds are unchanged on all three markets. XRP's first fold is still incomplete at a missing-data boundary.

The selected-trade-feedback control remains negative: XRP ordinary/higher-cost net is unchanged at -$7.47/-$3.75. AVAX improves from -$6.51/-$5.48 to -$2.78/-$1.74, still losses. The outcome-memory-disabled XRP diagnostic worsens from +$11.45 to +$4.24; it cannot replace the primary learner. Exit-study final results are unchanged. These mixed diagnostics are included in the comparison record rather than choosing each market's best account.

The new development forecast records score 10,183 DOT, 10,453 XRP and 10,610 AVAX outcomes before the final test; initial warm-up forecasts remain excluded. Final model error/calibration memories include 12,131, 12,947 and 12,890 scored outcomes respectively after shadow feedback. Rewards and training-label counts are unchanged from V11.7.

The disabled correction is still evaluated prospectively on the same final-period candidate entries:

| Market | Scored examples | Raw forecast RMSE | Trial-correction RMSE |
| --- | ---: | ---: | ---: |
| DOT | 1,948 | 0.736856R | 0.738110R |
| XRP | 2,494 | 0.669379R | 0.670818R |
| AVAX | 2,280 | 0.651009R | 0.650231R |

This does not establish a useful correction: two markets worsen, one improves slightly, and positive-forecast groups are mostly too sparse to activate it. Selected predictions remain overoptimistic, with mean prediction-minus-outcome of +0.6616R for XRP and +0.9306R for AVAX. The corrected and uncorrected selected forecasts are identical because their correction groups are not ready. No claim of better selected forecast accuracy is made.

**All markets remain unqualified. There are no unseen confirmation prices in these replays, and future profit is unproven.** DOT's latest bundle contains 105,049 intraday candles, 1,125 daily candles and 71 missing intraday intervals. Missing OHLC values were not invented. The other two supplied snapshots are older; these are fixed before/after comparisons, not current market forecasts.

The [machine-readable comparison](research_baselines/forecast-calibration-comparison.json) contains input hashes, exact ordinary/stress/earlier-period results, selected trades, trial forecast errors and model-source hashes. All three final runs use lab-source SHA-256 `4a84f3cb24203d4daf02c3926223fac84fa56ba61cddcdd3b34a9b0b1ce20105`. The [verification record](VERIFICATION.md) documents regression checks and limits.
