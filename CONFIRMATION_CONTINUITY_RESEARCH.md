# V11.10: preserve learning across review dates

## Reproduced defect

The latest supplied V11.9 export is partial: 11 of 13 markets completed. Those markets contain 19 selected historical account trades (six winners, thirteen losers), $36.05 gained by winners and $48.74 lost by losers, for a net loss of $12.69 after costs. They are separate $500 simulations, not a pooled portfolio. The aggregate higher-cost result is -$16.86. Changing candle windows and models means the improvement from the preceding ordinary-cost snapshot is not a controlled treatment effect.

Code inspection found a learning handoff error in the confirmation test. The old code replayed practice only to the review boundary, discarded still-open candidate positions there, then constructed new practice generators for the newer period. This lost subsequent outcomes from earlier entries and reset their occupancy and cooldowns. The routine then replaced the model from the complete primary replay with the restarted confirmation model. Thus an evaluation date could change the saved learner even when prices, strategies and costs stayed identical.

The supplied LTC report makes the accounting discrepancy visible: 12,282 development examples plus 2,836 primary final-period practice outcomes should yield 15,118 learned observations. Its exported model instead contains 15,114. These four net missing observations are not the full affected population: resetting positions removes some examples and adds other entries that an uninterrupted practice path could not open.

Eight of the eleven market reports have an observation-count mismatch. The difference between the exported model and the uninterrupted total is ETH -2, HBAR -2, XLM -6, ADA +4, DOGE -8, AVAX -1, LINK +6 and LTC -4. BTC, SOL and XRP have matching counts, which alone does not prove matching observations or weights. The [reviewed-report record](research_baselines/report-v11.9-partial.json) preserves both counts for every market. Complete candle-path reproduction in this revision focuses on LTC, the newly supplied market bundle.

A separate issue affected higher-cost confirmation: it was initialized with the ordinary-cost practice prefix. It now continues the corresponding higher-cost stream from the same pre-test development model used by the full higher-cost test. Its selected-account-only control receives that same higher-cost prefix model.

## Changes

- Continue the practice generators through the review date. Keep open positions, cooldowns, duplicate-entry identities and original entry forecasts. Only reporting counters restart.
- Learn carried-in trades once their actual exit bars close. An outcome available exactly at the reporting boundary belongs to the earlier prefix. An entry before the boundary that closes after it is explicitly marked as carried in.
- Preserve the model from the primary replay regardless of confirmation-account outcomes or reporting date. The confirmation account still starts with its own $500 balance and no account position at its boundary.
- Record gap censoring and practice loss-pause overrides when those events occur. Waiting until a generator finished would incorrectly attribute older events to the new reporting window.
- Show the number of carried-in learning outcomes separately from selected account trades. Correct the stale dashboard version label.

The same handoff is used by the existing independent exit and selection experiments. Neither experiment is promoted. Candidate strategies, feature definitions, fees, slippage, risk sizing, daily loss limits and qualification thresholds are unchanged. Paper and Coinbase journals retain their separate, one-time account-outcome updates. This is a historical replay correction, not a new live shadow-trading service.

## Research basis

[River's delayed progressive validation](https://riverml.xyz/dev/api/evaluate/progressive-val-score/) models a stream of predictions and later arriving answers. That supports preserving a prediction while waiting for its outcome instead of throwing it away at an evaluation cut. The implementation here uses the existing candle execution engine; River is not added as a dependency.

[Scikit-learn's guidance on data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) explains why information unavailable at prediction time must not affect fitting. Regression tests verify that future exits cannot change the model at the review boundary and that a carried-in outcome is unavailable until its exit bar closes. These sources support evaluation discipline; they do not establish a profitable trading strategy.

All endpoints in the latest 11-market report are registered as reviewed history. BCH and DOT retain their prior reviewed endpoints because the partial upload contains neither result. Replaying already examined dates cannot independently qualify this revision.

## Data and reproduction

[The input inventory](research_baselines/continuity-input-inventory.json) covers all 11 uploaded report files and 11 candle archives. All declared candle hashes verify. Duplicate snapshots are not extra observations. The earlier revised DOT boundary candle remains recorded explicitly. Across DOT, XRP, AVAX and LTC there are 420,517 distinct market/15-minute timestamps in the supplied archive union; the audit does not combine differing snapshots into one training series.

The latest LTC archive contains 105,063 observed 15-minute candles and 1,125 independent daily candles. Its intraday timeline has 57 missing intervals in five gaps; its daily timeline is continuous. The existing gap handling remains active. No candles are invented or downloaded for this study.

Pin V11.9 to merge commit `4e55d2833e9317fc86de6d97a06e306adac93238`, tree `14b91ecff489382e35dc8aa8a2b9f3040c1813c5`. Run the same script against both source directories:

```sh
python scripts/compare_confirmation_continuity.py --repo /path/to/v11.9 --bundle /path/to/LTC-bundle.zip --boundary-report /path/to/learning-results-6.json --out /path/to/ltc-before.json
python scripts/compare_confirmation_continuity.py --repo . --bundle /path/to/LTC-bundle.zip --boundary-report /path/to/learning-results-6.json --out /path/to/ltc-after.json
```

The normal research report marks the entire bundle as reviewed in both runs. A read-only observer retains the same pre-test model seed and the uninterrupted ordinary/higher-cost reference streams. Separate retrospective window diagnostics then reproduce the source version's handoff at the earlier report's LTC boundary: 2026-09-18 09:45 UTC. That window ends at 23:30 UTC the same day. The diagnostic cannot install a model, submit an order or change the learner's reviewed-history gate.

The script checks identical intraday/daily hashes and costs. It records individual practice identities, original forecasts, outcome-availability times, actual net returns and whether the ending model matches the uninterrupted reference. Mathematical model comparison excludes only the policy version identifier. All other weights, counts, errors and outcome memories remain part of the comparison. There is no parameter search or selection of the better-looking market.

## Measured results

The [compact before/after record](research_baselines/confirmation-continuity-comparison.json) preserves both cost scenarios, model hashes and every affected practice identity/forecast. Both source runs completed, in 383.060 and 380.954 seconds respectively. The continuity source fingerprint is `af56fc16be8836f81590c881c2e1cf4f3fdd7cc6c288790cc5f5639e5941dfe8`; later study-orchestration changes are verified separately in [the market-coverage record](MARKET_COVERAGE_RESEARCH.md).

| Retrospective LTC window | V11.9 handoff | Continuous handoff |
| --- | ---: | ---: |
| Normally resolved practice outcomes, ordinary costs | 16 | 20 |
| Outcomes carried from earlier entries | 0 | 8 |
| Carried-in outcomes passing cost rules | 0 | 2 |
| Ending model matches uninterrupted reference | No | Yes |
| Selected account trades | 0 | 0 |
| Account net profit | $0.00 | $0.00 |

The higher-cost replay also changes from 16 to 20 resolved outcomes, restores eight carried-in outcomes, and exactly matches its own uninterrupted higher-cost model. Account profit remains $0.00. Twelve entries are shared between versions in each cost scenario; four old-only entries disappear and eight legitimate carried-in outcomes return. This is not simply four appended training records.

The eight ordinary-cost carried-in examples include two losses and six gains. Two of the gains are multi-day support/RSI examples that passed cost screening. All outcomes retain their actual net returns; the fix does not reward a loss or mark a rejected-cost example as an account trade.

On the normal full-bundle reports, both versions use the full reviewed boundary and therefore do not run the faulty shorter confirmation path. Both produce 15,118 model observations, zero selected final-period trades and $0 final net profit at ordinary and higher costs. The older uploaded model had 15,114 observations because its shorter confirmation path overwrote the primary model. The new saved-model regression checks invariance to moving that boundary directly.

Prediction quality remains unresolved. Revised ordinary-window forecast RMSE is 1.1835R versus 1.0087R for a zero-return forecast; at higher costs these are 0.9698R and 0.8507R. The practice populations changed, so a raw before/after RMSE difference is not a clean treatment effect. These overlapping examples cannot demonstrate statistically independent profitability. All reports remain unqualified.
