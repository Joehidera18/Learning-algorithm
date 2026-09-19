# V11.11: relevant evidence, failure forecasts and Bitcoin context

## Fixed design before the comparison replay

The supplied `learning-results 8.json` (SHA-256 `353061f7bb42fc547aa50cc991456734ac4f9fbadd0fd1bae78aa3b2f2f07b51`) contains 42 of 120 planned studies. Its 57 completed selected trades have mean forecast +0.398526R and mean outcome -0.450249R. The additional window-end account mark is not a learning label. Across 58 account records, the independent simulations total -$96.954856 after fees; this is not one portfolio. LTC 5-minute development practice contains 8,821 cost-blocked examples and 135 cost-eligible examples.

The fixed revision has six parts:

1. Keep all completed outcomes in overall memory, but maintain a separate eligible model for each existing candidate. Both signal and fill economics must have passed for an eligible learning label. Affordable forecasts, minimum samples, recent-return memory and errors use this eligible model; they never fall back to cost-blocked practice. Sparse cost subgroups may borrow from eligible examples of that same candidate. The existing 30-observation minimum remains a heuristic, not evidence of 30 independent bets.
2. Apply the existing predeclared residual correction only downward for positive eligible forecasts in the normal policy. Each correction still matches candidate, cost bucket and raw forecast band; requires at least 30 observations and 30 effective samples; and uses the existing decay and shrinkage. A negative or sparse estimate is not raised. The two-sided correction remains an ineligible experiment. Actual rewards, risk and fee assumptions are not altered.
3. Add six small logistic outcome models: little follow-through, gave-back gains, fees-erased gain, near break-even, target reached and time exit. They use frozen entry vectors and only closed eligible outcomes. Unknown price paths do not become negative path labels. Entry predictions are scored against outcomes and an entry-time historical-frequency baseline. These estimates are research diagnostics, not calibrated probabilities or automatic entry/exit rules.
4. Continue the independently trained, fee-covered break-even exit experiment. Its account reports now also include performance by entry regime, alongside ordinary and higher costs, account-feedback controls, earlier folds and fresh confirmation. No per-market winner selection or automatic promotion is added.
5. Add completed Bitcoin daily trend, seven-day momentum, volatility, relative seven-day strength and a readiness indicator. Historical and forward paths use the same as-of join and 21-consecutive-day warmup. Missing or stale days are unavailable. A model trained with Bitcoin context blocks new entries when that context is unavailable; open-position management continues. Candle caches, fingerprints and exported bundles include the exact Bitcoin daily inputs. Older bundles without them are still reproducible with explicitly missing context.
6. Register the reviewed report's latest date per coin across timeframes. Persist run attempts, failures, interruptions and completed experiment manifests. Record all declared variants rather than choosing the most profitable result. Report market-candle regime coverage separately from candidate counts. This ledger is not a multiple-testing-adjusted significance test.

No additional candidate strategies, relaxed costs, larger risk budgets or live orders are introduced. Model/report versions invalidate incompatible models. New versions still need historical qualification and fresh confirmation after the reviewed boundary.

## Research basis

- [Gneiting and Resin, conditional forecast calibration](https://arxiv.org/abs/2108.03210): calibration should be assessed conditionally rather than inferred from pooled error. Our bounded online correction is an implementation hypothesis, not a reproduction of their isotonic method.
- [Scikit-learn time-series splitting](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): chronology matters when estimating future performance. Entry-time feature joins and closure-time labels remain separate.
- [Bailey et al., probability of backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf): trying multiple alternatives and reusing holdouts can mislead. Explicit experiment records and an updated reviewed boundary help expose reuse; they do not prove an edge or remove selection bias.

## Reproduction and interpretation

Use `scripts/compare_eligible_learning.py` with a pinned source tree, exact candle bundle and the reviewed report. Run the unchanged V11.10 baseline, then the revised source with `--baseline` pointing to its record. Input hashes, costs, label counts, test boundaries and training diagnostics must match. `--with-exit-study` runs the separate exit experiment. `--bitcoin-csv` accepts real recorded daily candles only; never substitute a generated price path for a market replay.

Artificial fixtures verify software behavior only. A replay without Bitcoin inputs measures the eligible-learning revision with missing benchmark context; it cannot establish the benefit of the new Bitcoin features. Improvements on already reviewed prices cannot qualify this revision. The latest report was incomplete, and later unreviewed account results remain necessary.

## Measured paired results

All six primary replays used exact supplied intraday/daily prices, the same costs, reviewed boundaries, development labels and training funnels. Each final test starts a separate $500 simulated account. Bitcoin daily prices are absent in these bundles. Direct retrieval was unavailable in this workspace, so no real-data benefit is claimed for the new benchmark features.

| Market / interval | Baseline trades | Revised trades | Baseline net | Revised net | Higher-cost net, before / after |
| --- | ---: | ---: | ---: | ---: | ---: |
| XRP / 15m | 4 | 6 | -$4.976139 | -$12.749657 | $0 / $0 |
| DOT / 15m | 0 | 0 | $0 | $0 | $0 / $0 |
| LTC / 5m | 0 | 0 | $0 | $0 | $0 / $0 |

Every study remains unqualified. The XRP change is a **$7.773519 deterioration**, not a profit improvement. Its selected-trade mean estimate rises from +0.335004R to +0.348376R while its mean actual outcome falls from -0.327928R to -0.569304R. The selected trades differ, so their error summaries do not establish a matched-entry forecasting improvement. None of these six revised selected entries had enough matching calibration evidence to apply a correction. No parameters were adjusted after observing this result.

The main benefit established here is correct evidence separation and observability. The ending learners contain 1,059 eligible versus 12,773 blocked XRP examples, 1,008 versus 12,060 DOT examples, and 193 versus 11,268 LTC examples. Totals match the baseline's 13,832, 13,068 and 11,461 observations exactly. Candidate examples overlap and are not independent bets. In LTC development, no eligible candidate had enough previously completed evidence to yield a scored ready forecast; pooled blocked examples no longer conceal that shortage.

The new failure heads beat their entry-time frequency baseline in only **2 of 18** market/target comparisons: XRP time exits and LTC targets. The remaining 16 comparisons are worse. Counts are small and dependent. Keeping these estimates diagnostic is therefore material: this comparison does not justify using them as trade filters or calibrated probabilities.

The declared XRP break-even exit study earned **$13.419072 across seven trades** at ordinary costs, but lost **$7.471875 across two trades** at higher costs. It fails the research checks and remains ineligible for trading. That isolated ordinary-cost gain is not selected as a replacement policy. An earlier XRP fold also stopped at a data gap while holding a position; its return remains unknown.

Final-window candle coverage is reported separately from entry regimes. For example, XRP includes 4,568 BULL, 6,779 BEAR, 9,426 CHOP and 240 unavailable-warmup candles, while every selected revised trade entered in BULL. That is broader price coverage, not demonstrated trading skill in every regime.

[The machine-readable comparison](research_baselines/eligible-context-comparison.json) contains exact input/source hashes, fees, dates, counts, error and failure scores, regime results, declared trials and negative results. The unchanged baseline tree is `412d198ae5d05a914989bb615bb62d3853660e3d`. All revised replays use lab-source SHA-256 `506c5d8a1fbdc7403b5fb4b80734e8c6ea0fe96cace3898ed4552e049b110949`; the final source changes only one explanatory string in `prediction_audit.py` afterward. Reversing that string exactly restores the replay hash. All learning and execution calculations are unchanged.

The revised runs peaked at 416.5–451.6 MiB RSS on these inputs. XRP includes the separate exit study, so its runtime is not comparable with the primary-only baseline. These are local measurements, not evidence that a 512 MB hosted service can handle larger plans plus HTTP requests. See [hosting guidance](WEBSITE_SETUP.md) and [final verification](VERIFICATION.md).

Example reproduction, using a separately checked-out V11.10 baseline and this revision:

```sh
python scripts/compare_eligible_learning.py --repo /path/to/baseline --bundle '/path/to/XRP-USD_15m_learning-data 2.zip' --reviewed-report '/path/to/learning-results 8.json' --out /tmp/baseline-xrp15.json
python scripts/compare_eligible_learning.py --repo . --bundle '/path/to/XRP-USD_15m_learning-data 2.zip' --reviewed-report '/path/to/learning-results 8.json' --baseline /tmp/baseline-xrp15.json --with-exit-study --out /tmp/revised-xrp15.json
```

Repeat without `--with-exit-study` for the supplied `DOT-USD_15m_learning-data 4.zip` and `LTC-USD_5m_learning-data 2.zip`. A new recorded-Bitcoin comparison requires the same additional daily inputs across declared comparable feature variants; these no-Bitcoin baseline records must not be presented as that test.
