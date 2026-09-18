# V11.9: keep eligible practice available

## Finding and fixed change

The latest completed V11.8 upload contains 18 selected trades across 13 separate $500 historical accounts: five winners, thirteen losers, $29.37 won, $48.65 lost, and a net loss of $19.27 after costs. These are the same selected trades as the preceding V11.8 upload. More downloaded candles changed the models, but did not create new selected account trades. The latest report's short confirmation window contains 394 resolved, overlapping practice examples; all their entry forecasts are nonpositive. This alone does not prove that the model is too pessimistic about trades that can pass its cost rules.

Code inspection identified a sampling problem. Each strategy's single practice position could open despite failing the account's cost rules. While that position remained open, the strategy could not study a later setup that passed those rules. Separate cost buckets in the model cannot recover examples that were never collected. A deterministic regression fixture reproduces this: the original practice path only collects a costly entry; the revised paths also collect a later eligible entry. Both happen to lose in that fixture, and both losses are learned.

For every existing candidate, V11.9 runs two independent practice tracks:

- **Eligible:** both signal-time economics and next-open fill economics pass the existing cost and net-reward rules.
- **Cost blocked:** at least one of those checks fails. Actual modeled fees, spread and slippage are still charged.

Each candidate entry belongs to exactly one track. Holding a position or serving routine entry spacing in one track cannot occupy the other. Each track retains the same stops, targets, execution ordering, gap handling and exit deadline. Independent practice keeps learning through losing streaks; account risk controls still govern account tests and trading. This change does not reward losses, relabel break-even outcomes as wins, lower fees, increase trade size, or authorize trades.

The two new paths are not simply the old example list plus extra entries: changed occupancy can also replace later examples. The comparison records shared entries, entries present only before, and entries present only after.

The same split applies to earlier development labels and later historical shadow feedback. Entry forecasts are preserved before outcomes become available. At a shared closure timestamp, outcomes are ordered by candidate and original entry time, consistently across both training mechanisms. Duplicate candidate/entry identities are rejected. Every net reward updates learning once; overlapping strategies are still not independent bets. Account feedback is not additionally applied when shadow feedback is active.

The learner retains its 27 features and 22 candidate parameter sets. Engine, policy and report versions change to invalidate old learning/checkpoint identities. Prices and account journals remain usable. The latest V11.8 endpoints are recorded as reviewed history, so these replays cannot independently qualify the revision.

## Research used

- [River: delayed progressive validation](https://riverml.xyz/dev/api/evaluate/progressive-val-score/) distinguishes prediction events from later answers. Our paired entry/closure replay follows that evaluation principle; River is not added as a dependency.
- [scikit-learn: data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) explains why unavailable future information cannot guide fitting. Practice-track membership uses entry economics, never the eventual outcome or after-exit review.
- [scikit-learn: regression metrics](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics) motivates scoring predicted returns against realized returns. Because the revised practice distribution changes, the comparison script matches identical candidate entries before comparing forecast RMSE. Aggregate errors over different sets are not presented as an accuracy improvement.
- [Coinbase: historical candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) documents incomplete history and omitted no-tick intervals. The supplied OHLC data are retained as observed; missing candles are not filled with invented prices.

The two-track design is an implementation hypothesis supported by a reproducible coverage defect, not a published trading edge. Simulated outcomes do not establish actual fills or unbiased off-policy returns. More practice can improve or worsen a model's choices. Fresh prospective evidence is still necessary.

## All-upload audit and data limits

`scripts/audit_learning_inputs.py` inventories all supplied learning reports and candle bundles, verifies declared canonical candle hashes, identifies duplicate snapshots, and records changed overlapping rows. See [the inventory](research_baselines/practice-input-inventory.json). Old reports are evidence of earlier behavior; their overlapping candles and outcomes are not appended repeatedly as new independent observations.

The audit covers ten report files and ten ZIP files. Their union contains 315,454 distinct market/15-minute timestamps across DOT, XRP and AVAX, including 300 older DOT timestamps outside the latest rolling snapshot. All declared candle hashes verify. One older DOT boundary candle at 2026-09-15 21:45 UTC has revised low, close and volume values in later exports; both versions are recorded in the inventory. The latest selected DOT snapshot has 105,049 intraday candles, 1,125 daily candles and 71 missing intraday intervals. Duplicates and revisions are not silently treated as additional independent observations.

Fixed before/after comparisons use the latest supplied DOT snapshot and the available XRP and AVAX snapshots, including their independent completed daily candles. These are the three markets for which complete candle bundles are supplied. The remaining markets have report/model summaries, which cannot reconstruct missing historical OHLC paths. Earlier DOT snapshots are audited for overlap and revisions, not silently concatenated into the latest snapshot. This preserves identical inputs for both versions. No additional market prices are downloaded in this study.

## Reproduction

Pin V11.8 to GitHub merge `2c58efdf01fce07cb1e5058a4b24859d2a7ae446`, tree `5abc5c3fe55cc298cbde23afe15cb45c49514e5b`. Run each supplied market against both source versions and use `learning-results 6(1).json` as the reviewed report in both runs:

```sh
python scripts/audit_learning_inputs.py --input-dir /path/to/uploads --out /path/to/inventory.json
python scripts/compare_practice_tracks.py --repo /path/to/v11.8 --bundle /path/to/bundle.zip --reviewed-report /path/to/learning-results-6.json --out /path/to/baseline.json
python scripts/compare_practice_tracks.py --repo . --bundle /path/to/bundle.zip --reviewed-report /path/to/learning-results-6.json --baseline /path/to/baseline.json --out /path/to/revised.json
```

The script verifies price identities, daily inputs, costs, candidate count and final-test boundary. Training-label counts are expected to change. It records source/input hashes, ordinary and higher-cost returns, earlier periods, and matched-entry forecast errors. Exact entry forecasts are collected by a read-only observer, which cannot change decisions or learning. All outcomes are reported; no parameter search or best-market selection is performed.

For an additional execution check, run `verify_practice_forecasts.py` with the corresponding `--repo`, `--bundle`, `--record` and `--out` for each side. Name outputs `dot-baseline-verified.json` / `dot-revised-verified.json` (and likewise for XRP/AVAX). `summarize_practice_tracks.py --study-dir /path/to/records --out /path/to/comparison.json` creates the compact comparison artifact.

## Measured results

The fixed before/after replays produce the following results. Each row is a separate $500 account; all figures include modeled costs.

| Market | Development examples before → after | Final practice passing cost rules before → after | Final account net before → after | Higher-cost net after |
| --- | ---: | ---: | ---: | ---: |
| DOT | 10,831 → 11,026 | 134 → 145 | $0.00 → $0.00 (no trades) | $0.00 (no trades) |
| XRP | 11,113 → 11,294 | 119 → 127 | -$4.98 → -$4.98 (4 trades) | $0.00 (no trades) |
| AVAX | 11,270 → 11,514 | 86 → 89 | -$5.61 → -$5.61 (3 trades) | -$4.33 |

Development gains 620 examples across both tracks. Final-period cost-eligible practice increases from 339 to 361 examples. This is a coverage improvement, **not an improvement in final account profitability**. The selected final trades and their net results are unchanged. Higher-cost primary results and selected-trade-only feedback controls are also unchanged. The latter remain negative for XRP (-$7.47 ordinary, -$3.75 stressed) and AVAX (-$2.78 ordinary, -$1.74 stressed).

Earlier periods are mixed: XRP's second period worsens from -$0.83 to -$4.57, while AVAX's third period improves from +$0.96 to +$3.63. Other earlier primary periods are unchanged; XRP's first period remains incomplete at a candle gap. The separate conditional-selection experiment worsens on DOT from $0.00 to -$1.15 in the final period. It remains research-only. The break-even-exit experiment is not promoted on the strength of XRP's positive ordinary-cost result; its higher-cost result remains negative.

Matched cost-eligible entry forecasts have these errors:

| Market | Same scored entries | V11.8 RMSE | V11.9 RMSE |
| --- | ---: | ---: | ---: |
| DOT | 134 | 1.101961R | 1.093838R |
| XRP | 117 | 0.925380R | 0.923559R |
| AVAX | 86 | 0.891860R | 0.897419R |

Two markets improve slightly and one worsens. Counts do not establish statistical significance. Comparison membership is based on candidate and entry timestamp, and matching exit times/net rewards are asserted. DOT has seven earlier-only and 31 revised-only practice entries; XRP has two and 24; AVAX has zero and 14. These are all practice tracks, not account trades. Full cost-blocked matched-error results are included alongside eligible results in the comparison data.

The initial research observer mistakenly tried to recover signal economics from public feature dictionaries, which omit private close/ATR fields, and consequently mislabeled its cost groups. This was an analysis-tagging error, not a learner or trading change. The observer now uses stored signal-time economics plus the actual fill rejection. A separate execution replay verified **every** saved practice entry, exit availability and net reward against its pinned source and recomputed cost groups, while preserving all saved forecasts and account results. `scripts/verify_practice_forecasts.py` reproduces that verification. Revised group counts also match the learner's independently recorded track counts.

All markets remain unqualified. There are no unseen confirmation prices in these comparisons because the latest supplied endpoints have already informed this work. The full result record is [practice-tracks-comparison.json](research_baselines/practice-tracks-comparison.json). All revised core replays use lab-source SHA-256 `0d1db1624bfabf24175796e7a5a257d56ac874d7c85392d230504f5039f2546c`. See [VERIFICATION.md](VERIFICATION.md) for software checks and their limits.
