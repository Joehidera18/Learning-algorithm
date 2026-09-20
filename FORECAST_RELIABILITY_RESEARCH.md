# Forecast reliability: declared revision

Design recorded before the revised replay results on 20 September 2026 UTC.
The baseline is the main-branch V11.14 source. The latest uploaded run is still
partial (29/120 studies); its 35 selected historical trades forecast +0.3648 net R
on average and realize -0.5344 R. This change is prepared in an isolated branch;
the user's running study, website and accounts are not changed.

## Fixed hypothesis

More observations do not remove systematic forecast bias. The current error
margin divides forecast RMSE by a square root of a capped sample count. It can
therefore shrink even when the average forecast remains too high. Meanwhile,
positive-return calibration cells often have fewer than thirty observations,
so the existing downside correction stays exactly zero in those cells.

Test this one declared bundle of numerical changes without a parameter search:

1. Retain the existing error margin, and also retain the positive signed mean
   of saved entry forecast minus eventual net return as a floor after the
   existing thirty-scored-entry minimum. Do not divide systematic bias by the
   square root of a sample count. Score the forecast actually used at entry,
   not a model refitted after the outcome.
2. Permit a small downside correction to an eligible positive raw forecast
   from the first resolved matching calibration example. Reuse the existing
   strategy/cost/raw-band identity, fifty-observation half-life, effective-count
   cap of 100 and shrinkage effective/(effective+50). The thirty-observation
   readiness flag remains a diagnostic; sparse corrections must be explicit.
   A correction cannot raise a normal-policy estimate. The two-sided research
   experiment retains its existing thirty-observation activation requirement.
3. Preserve original net-return rewards, costs, risk sizing, candidate
   definitions, loss limits, price-gap handling and qualification requirements.
   Keep selected/raw/trial forecasts distinguishable in audits; do not count a
   loss twice or treat an unclosed trade as a label.

This is a modeling hypothesis, not proof that either rule will earn money.
Improved signed error, fewer losing selections or a cash result are not a
validated profitable strategy. Mixed and negative comparisons will be retained.

## Fixed comparison

Use the supplied XRP 15m, AVAX 15m and DOT 15m bundles, with a fourth XRP 6h
bundle containing independent Bitcoin daily context. Run the unchanged
baseline and revision on identical candle/context hashes, fees, test dates and
reviewed boundaries. These datasets are already reviewed history. Compare
ordinary and higher-cost primary accounts, frozen controls, entry forecast
errors, development examples and the unchanged qualification decisions. Report
every market. The six-hour study remains research only.

Use the full result exports, not a manually edited list of losing trades.
No new strategy threshold, calibration band or per-coin winner will be chosen
after inspecting these results. A later independent evaluation is still needed.

## Other correctness work

Repair event snapshot readiness separately: starting historical learning before
the collector, then capturing an empty snapshot once before the entire queue,
can omit later collected events from every study. Wait only for a bounded
initial collection in the background worker, permit cancellation, record missing
coverage explicitly, and preserve already pinned job snapshots on resume.
Current news must never be inserted before its actual observation time.

## Research sources

- Gneiting and Resin, [conditional forecast calibration](https://arxiv.org/abs/2108.03210):
  assess agreement between forecasts and outcomes in relevant conditions. The
  shrunk online rule here is our hypothesis, not their isotonic methodology.
- Bailey et al., [backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf):
  repeated historical selection can create misleading performance evidence.
  Recording this design does not make previously reviewed prices independent.

The following results were appended after the declared comparison.

## Recorded comparison

All four comparisons use the same input hashes, development examples, costs,
reviewed boundary and test periods between versions. Baseline main is commit
`24e21c77cacd4dba28885a55e0a216eb857c3e67`, tree
`a27acc3ceae94b5ac60c808c2f296817d892c429`. Both policies use the supplied
0.4% fee per side, 0.05% slippage setting and the existing modeled spread.
Each account starts with $500. The rows are separate simulations, not a portfolio.

| Supplied bundle | Selected trades, both versions | V11.14 net | V11.15 net | Higher-cost net, both |
| --- | ---: | ---: | ---: | ---: |
| XRP-USD_15m_learning-data 2.zip | 6 | -$12.749657 | -$12.749657 | $0.000000 |
| AVAX-USD_15m_learning-data.zip | 3 | -$5.610306 | -$5.610306 | -$4.007496 |
| DOT-USD_15m_learning-data 4.zip | 0 | $0.000000 | $0.000000 | $0.000000 |
| XRP-USD_6h_learning-data.zip | 0 | $0.000000 | $0.000000 | $0.000000 |

The complete selected-trade economics, including times, fees, risk and results,
are identical. All four studies remain unqualified. Cash outcomes do not
establish a profitable trading rule. Higher-cost accounts rerun decisions and
can select different trades; they are not extra fees subtracted from one ledger.
The first three bundles have no independent Bitcoin daily archive; their
missing context stays unavailable. The six-hour bundle includes Bitcoin daily
prices but selects no trades. None of these four inputs has an observed news
archive, so these replays cannot measure the news-readiness fix's trading value.

| Forecast measurement | Before | Revised | Interpretation |
| --- | ---: | ---: | --- |
| XRP selected-trade RMSE | 1.325279R | 1.326123R | Slightly worse |
| XRP independent-practice RMSE | 0.664572R | 0.664513R | Slightly lower error |
| AVAX selected-trade RMSE | 1.152726R | 1.152726R | Unchanged |
| AVAX independent-practice RMSE | 0.651684R | 0.651527R | Slightly lower error |
| DOT independent-practice RMSE | 0.755003R | 0.755003R | Unchanged |
| XRP 6h independent-practice RMSE | 0.385459R | 0.385247R | Slightly lower error |

These small error changes do not demonstrate economic value. In particular,
lower signed optimism need not improve squared error: reducing a forecast for
an eventual winner can worsen its error. There was only one newly applied
correction among the selected XRP trades and none among the AVAX selections.
The new rules did not change final account decisions in these tests. The bias
floor is a reliability safeguard, not a demonstrated solution to trade selection.
No threshold or strategy was retuned after these outcomes.

The [comparison record](research_baselines/forecast-reliability-comparison.json)
contains exact data/source hashes, all account and forecast summaries, selected
trades and links to eight compressed complete replay records. It preserves the
negative result and the matched frozen controls. Those controls are diagnostics;
their historical results do not select a trading policy.

## Why the larger data count did not establish improvement

The latest supplied `learning-results 11.json` is a partial 29/120 export.
It has 235,734 development examples and 289,575 resolved observations after
later independent practice. Of the latter, 255,333 (88.17%) fail the entry cost
rules and 34,242 are cost-eligible. These counts overlap across strategies and
timeframes and are not independent profitable opportunities.

Across its 35 selected final account trades, mean prediction was +0.3648R and
mean actual return was -0.5344R. The model is too optimistic on this small set
of chosen trades even when the much larger all-practice forecast average looks
reasonable. Global averages can hide errors in the part used to trade. Its
simple long-only candidate family also limits what additional candles can teach:
the learner cannot create a new strategy merely by replaying more observations.

Models are separate by coin/timeframe and use additional strategy/context
groups. A large overall data total therefore does not mean a large sample of
comparable positive forecasts in each group. Gaps exclude unresolved labels,
costs consume small gross gains, and later market conditions can differ from
development periods. Cross-version uploads also changed price windows and
coverage, which is why their raw P&L totals alone cannot identify a code effect.

The export reports zero forward-learning trades and all 29 studies have news
disabled. It is evidence of historical replay, not weeks of demonstrated live
learning with world-event context. Its recorded paper status is stopped; this
does not establish the current server's state. A collector starting today cannot
supply information that was actually observable years earlier.

## Scope of this candidate update

- Actual losses and near-break-even outcomes keep their full net reward and
  train once on closure. The independent practice lanes keep collecting losses.
- The normal correction only lowers positive, cost-eligible forecasts. The
  two-sided experiment still waits for its existing 30-sample evidence minimum.
- Saved records distinguish raw, selected, trial and provisional corrections.
  Corrupt or future-dated input records cannot mutate the learner.
- News readiness waits only in the worker, for at most 15 seconds, with prompt
  cancellation. Each new job snapshots after price downloads; resumed jobs keep
  the original snapshot, even if empty. Failed polls remain in the archive.
- Engine V11.15, report 21 and policy v18 distinguish this numerical revision.
  Reviewed dates from all fourteen supplied reports are carried forward, so
  changing version cannot turn already analyzed prices into fresh validation.
- No running account, settings, website or learning job was changed to prepare
  this branch. Fear & Greed and a smaller default universe remain separate
  pending work; neither was added as an untested explanation for better returns.

The next meaningful performance evidence is a completed, fixed-protocol test
on later prices with realistic costs. The current partial learning period should
finish and be exported before deployment. Adding more features or repeatedly
testing thresholds on the same losses would not supply that evidence.

## Reproduction

Check out baseline commit `24e21c77cacd4dba28885a55e0a216eb857c3e67`
and this revision in separate directories. Run the existing driver for each
bundle in the table, using the same reviewed-report file from this revision:

```sh
python scripts/compare_eligible_learning.py \
  --repo /path/to/baseline \
  --bundle '/path/to/XRP-USD_15m_learning-data 2.zip' \
  --reviewed-report research_baselines/report-v11.14-partial.json \
  --out /tmp/reliability/xrp-baseline.json
python scripts/compare_eligible_learning.py \
  --repo /path/to/revision \
  --bundle '/path/to/XRP-USD_15m_learning-data 2.zip' \
  --reviewed-report research_baselines/report-v11.14-partial.json \
  --baseline /tmp/reliability/xrp-baseline.json \
  --out /tmp/reliability/xrp-revised.json
```

Use `avax`, `dot`, and `xrp6h` as the other output prefixes. Keep the default
primary-policy comparison options; do not add exit or selection searches.
Archive and check all eight records together with:

```sh
python scripts/summarize_forecast_reliability.py \
  --records /tmp/reliability \
  --out /tmp/reliability-summary/forecast-reliability-comparison.json
```

The retained gzip files contain ordinary JSON and can be decompressed for full
inspection. Runtime varies and was not the purpose of this comparison.

## Verification

- `python -m unittest discover -s tests -v`: **382 tests passed**. This includes
  chronology, full loss rewards, persistence, interrupted/restarted studies,
  sparse corrections, malformed forecast rejection, news timeout/cancellation,
  per-job snapshots, accounting, and paper/Coinbase separation.
- `node tests/check_learning_ui.js` and `node tests/check_finances_ui.js`:
  both passed, including the selected/provisional forecast display and old
  report compatibility. These exercise the actual render functions; a browser
  screenshot inspection is not claimed.
- Four baseline/revision pairs passed input-matching and nonqualification
  assertions. Selected-trade economics and rejection reasons are unchanged.
- All four revised runs use the final `lab/*.py` source digest
  `6f07243337116e2531f7c5847b20ab7d6e466e6511735b09d9f2d7db2b925fde`.

Fixtures establish software behavior, not profitability. The financial replay
results above remain the material performance finding.
