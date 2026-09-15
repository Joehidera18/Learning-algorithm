# V11.3: learning from completed outcomes and repairing context data

The supplied report 16 contains 130,621 development examples but only 14 selected final-period trades across 13 separate $500 accounts. None qualifies. The DOT bundle reproduces its report's data hash; it contains 105,049 quarter-hour candles and 71 missing intervals. These findings motivate data and learning corrections. They do not establish a profitable strategy.

## Declared changes

The 22 candidate strategies, entry/exit rules, 0.75% per-trade risk cap, 30% notional cap, daily loss halt and qualification requirements remain the experiment's controls. This revision does not increase risk or weaken qualification to generate trades.

- Retry remaining internal gaps directly, then reconstruct only from a complete set of smaller candles on Coinbase. Record recoveries, unresolved gaps, errors and provenance. No forward filling, interpolation, partial candle aggregation or exchange substitution.
- Request a separate series of completed daily Coinbase candles, including 30 extra days for warmup. Join daily features as of each decision close. Missing intraday candles still restart intraday indicators; a missing daily candle still resets daily warmup. A failed daily download explicitly falls back to complete intraday days.
- Give each strategy a recency-weighted memory for cost burden, intraday regime and daily trend. The outcome half-life is fixed at 50 completed observations; require 30 effective observations and shrink context estimates toward the existing linear estimate with strength 50. Cap effective evidence at 100. Keep net return as the learning target and existing error penalties. These choices are declared hypotheses, not fitted optima or calibrated confidence levels.
- Record gross return, fees and exit category separately when known. A gross gain erased by fees remains a losing label. Recent losses in a sufficiently sampled matching context block that setup; later completed successes can restore it. Forward paper and real journals stay separate and update atomically after closure.
- An explicit Practice action rechecks data even before the automatic review deadline. Hash both candle sources into checkpoints and completed reports. Data exports include `daily-candles.csv` when separate daily data was used and reject mismatched caches.
- Bump engine, policy and report versions. Existing models require retraining. Reviewed report-16 windows cannot qualify a revision as fresh evidence.

Historical shadow examples continue to overlap across variants. The memory does not convert them into independent bets. The counterfactual examples teach outcomes of prescribed strategies; they do not prove why a trade lost or teach an unconstrained strategy generator.

## Research basis

[Coinbase's candle API specification](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) documents incomplete historical data, absent intervals without ticks, a 300-candle request maximum and daily granularity. This supports targeted retrieval and explicit missingness; it does not justify invented candles.

[Liu and Tsyvinski, Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877) examines cryptocurrency momentum. [Liu, Tsyvinski and Wu, Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882) studies market, size and momentum factors. Those historical findings motivate checking broader conditions; they do not establish that a 15-minute Coinbase strategy pays its fees. This implementation is not a replication of either paper.

[Bailey et al., Pseudo-Mathematics and Financial Charlatanism](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659) explains how repeated strategy trials produce misleading backtests. Therefore the declared comparison is limited to the revised policy on the provided 15m data and complete 1h aggregates, with unchanged ordinary/stressed costs and a memory-disabled control. The better result cannot be selected retrospectively and called validated. No parameter sweep is planned.

## Evaluation protocol and reproduction

The ordinary assumptions are 0.4% fees on each side and 0.1% modeled slippage/spread on each fill; stress multiplies both by 1.5. Each test starts with $500. Training uses earlier completed labels, three later chronological folds, a purge and a final later window. Selected-account-only feedback is separately checked because that is the forward update mechanism between historical reviews. All supplied dates are marked reviewed.

Run the fixed comparison with the original uploaded files:

```sh
python scripts/compare_learning_revision.py --bundle "DOT-USD_15m_learning-data 3.zip" --previous-report "learning-results 16.json" --out dot-v11.3-comparison.json --full-results results
```

Run new data collection and practice where the Coinbase API is reachable:

```sh
python run_research.py --coinbase --learning --symbol DOT-USD --interval 15m --days 1095 --fee 0.004 --out dot-new-history.json
```

Or reproduce an exported bundle after extraction:

```sh
python run_research.py --csv candles.csv --daily-csv daily-candles.csv --learning --symbol DOT-USD --interval 15m --fee 0.004 --out reproduced.json
```

Omit `--daily-csv` for an older bundle with only intraday candles. Do not substitute another venue's candles for missing Coinbase intervals. The command itself does not install a trading model or place orders.

## Results

The reproducible record is [dot-v11.3-comparison.json](research_baselines/dot-v11.3-comparison.json). The supplied input and source-code hashes are recorded in it. The declared method was committed in `014cfa7` before examining the revised replay; a final replay after validation hardening confirmed the same account results.

| DOT research test | Development examples | Final account trades | Net after ordinary costs | Net at 1.5x costs | Profitable later folds | Qualified |
|---|---:|---:|---:|---:|---:|---|
| Supplied V11.2, 15m | 9,797 | 0 | $0.00 | $0.00 | 0 / 3 | No |
| V11.3, 15m | 9,797 | 0 | $0.00 | $0.00 | 0 / 3 | No |
| V11.3, complete 1h | 3,035 | 0 | $0.00 | $0.00 | 0 / 3 | No |

The memory-disabled and selected-account-only controls also selected no final-period trades at either cost level. The measured P&L improvement from outcome memory is **$0**, and no new profitable edge is demonstrated. Cash preservation is not trading profitability. This revision should not be represented as a successful trading strategy.

The 15m memory records 11,535 completed examples including development and subsequent shadow feedback: 8,032 stopped out, 397 had gross gains erased by fees, 305 lost at time exits and 2,801 made net gains. Every family's combined average net R remains negative. The categories cover overlapping hypothetical examples, not actual account trades; fees are not the sole cause of failure. The context-loss gate rejected 93 final-period candidate evaluations on 15m and 187 on 1h; these are not independently measured avoided account losses.

The 1h series contains 26,248 complete hours, with incomplete hours discarded. It has 32 missing hourly intervals. Its split dates differ from the 15m split because of aggregation and omitted hours. These tests share the same underlying market history and are not independent evidence.

Separate daily data were unavailable in these real-data replays. Daily context was available on 10,615 / 21,010 final-period 15m candles (50.52%) and 2,663 / 5,250 hourly candles (50.72%). Direct Coinbase retrieval timed out in the development environment, so the supplied 71 missing DOT intervals have not been recovered here. Recovery and independent daily context must be exercised with real additional data before claiming a fuller market picture or a performance benefit from those data changes.

The expanded test suite passes **195 Python tests**, including context-specific failures and recovery, outcome accounting, no future daily inputs, intraday warmup after gaps, exact smaller-bar reconstruction, cancellation/request bounds, persistent recovery provenance, cache invalidation and daily-data exports. The dashboard's actual JavaScript also passes Node-based report rendering, escaping and download checks. Those checks use a mocked document; they do not verify hosted/mobile rendering or live fills. No order was placed and no deployed service was changed.

Use this as a tested research revision. Run fresh practice to collect and repair same-venue data with the actual account fee, inspect the recovery report, and retain qualification checks. New strategy hypotheses or a more complex model would require separately declared development work and later confirmation; repeatedly optimizing these known test windows would not supply that confirmation.
