# 18 September 2026 practice-track verification

**262 Python tests passed in 337.164 seconds** on the final V11.9 source. Both actual JavaScript mocked-DOM checks passed against the completed V11.8 upload and the new practice-group fixtures. Python compilation, JavaScript syntax and diff whitespace checks passed. No hosted/mobile visual verification, deployment or exchange orders were performed.

New regression cases reproduce an occupied cost-blocked practice position hiding a later eligible setup, and verify that separate tracks collect both losses with full cost accounting. They cover complementary entry membership, signal-versus-fill cost checks, account/practice separation, delayed one-time updates, duplicate rejection, future-candle isolation and deterministic simultaneous closure order. Existing restart, checkpoint, gap, account separation, loss-severity and qualification tests pass.

The checkpoint test now expects two simulations per completed candidate while preserving one saved checkpoint per candidate and separate exit-policy namespaces. Its saved/resumed/fresh model and result comparisons still match. A dense integration fixture exceeded its previous 60-second worker-completion gate both with competing research runs and in a later suite. Its test-only completion deadline is now 120 seconds to accommodate the two tracks; the final full suite passed. No production timeout, financial limit or qualification requirement was relaxed.

Pinned V11.8/V11.9 replays use identical DOT, XRP and AVAX candle bundles, daily inputs, costs and reviewed boundaries. Development gains 620 examples; cost-eligible final practice grows from 339 to 361 examples. Selected entry/exit identities and P&L remain identical: final account nets are $0.00, -$4.98 and -$5.61. Higher-cost results are unchanged. Earlier periods and matched-entry forecast errors are mixed. All markets remain unqualified, with no unseen confirmation window in these inputs.

A separate candidate-execution replay verified every saved primary practice entry, exit availability and net reward on each pinned source. It also corrected an initial research observer's cost-group tags, which had incorrectly relied on exported public feature dictionaries lacking private close/ATR fields. Saved forecasts, models and account results were preserved. The fixed observer uses saved signal-time economics and the actual fill rejection. Revised group counts match the learner's own track counts. This analysis correction did not change the learner or trading execution.

All revised core replays and independent execution checks use lab-source SHA-256 `0d1db1624bfabf24175796e7a5a257d56ac874d7c85392d230504f5039f2546c`. [The research record](PRACTICE_TRACKS_RESEARCH.md) includes sources, negative results and reproduction commands. [The compact comparison](research_baselines/practice-tracks-comparison.json) preserves exact results and input/source hashes. [The all-upload inventory](research_baselines/practice-input-inventory.json) covers ten reports and ten candle archives, validates declared price hashes, and identifies duplicates plus one revised overlapping DOT candle.

# 16 September 2026 chronological forecast-learning verification

**254 Python tests passed in 83.871 seconds** on the final V11.8 source. Both actual JavaScript mocked-DOM checks passed; the learning renderer was exercised with the completed V11.7 upload and the new correction fixtures. Python parse/compilation, JavaScript syntax and diff whitespace checks passed. No hosted/mobile visual verification, deployment or real orders were performed.

New checks cover development entry/closure ordering, future-outcome isolation, identical bulk/incremental/reconstructed training, raw-residual correction without an extra reward, actual break-even and tail losses, sparse-context fallback, strategy/cost/forecast-band separation, invalid-state rejection before updates, and default-versus-experimental model isolation. Experimental reports always carry a disqualifying reason; approved-profile loading rejects their models. The existing paper journal transaction test now verifies one-time correction-memory updates and retains restart and Coinbase-account separation checks. Existing checkpoint resume and future-price mutation checks pass with the new development event replay.

The full suite ran after real-data replays finished. No production limits or test deadlines were relaxed in this revision. Initial new fixture assertions assumed the helper contained 100 observations; it actually contains 80. Those assertions were corrected before the final successful suite. An intermediate targeted command named a nonexistent test class; the actual persistence class and the final discovery run both passed.

Paired final-source replays on identical supplied DOT, XRP and AVAX candles preserve cost settings, label counts, training diagnostics and test boundaries. Default-model final nets are $0.00, -$4.98 and -$5.61, versus $0.00, -$6.03 and -$5.61 for V11.7. Higher-cost primary results and earlier primary folds are unchanged. The XRP account path changes, so the $1.0576 improvement is not simply one deleted trade. All three remain unqualified, with no unseen confirmation prices.

The initially enabled residual correction had mixed forecast accuracy. It is now a measured experiment, disabled in the default policy and blocked from qualification/approved model loading. Final-source exports compare the raw and trial estimates on identical completed candidate examples and verify zero corrections applied to default decisions. Those comparisons do not represent another account's P&L. Selected forecast optimism remains unresolved; this is a more complete error-learning process with a small reused-history loss reduction, not proven profitability.

All three final replays match the current lab-source SHA-256 `4a84f3cb24203d4daf02c3926223fac84fa56ba61cddcdd3b34a9b0b1ce20105`. Input hashes, chosen trades, negative diagnostic results and ordinary/stressed comparisons are recorded in [the comparison data](research_baselines/forecast-calibration-comparison.json). See [the design, sources, limits and reproduction commands](FORECAST_CALIBRATION_RESEARCH.md).

# 16 September 2026 entry-forecast learning verification

**241 Python tests passed in 145.957 seconds** on the final implementation. The two actual JavaScript mocked-DOM checks passed against the completed V11.6 upload and the new forecast/selection fixtures. Python compilation, JavaScript syntax and diff whitespace checks passed. No hosted/mobile visual verification, deployment or real orders were performed.

New checks establish that a forecast is saved before entry, remains unchanged when other outcomes update the model, is scored only after a normal exit, and updates error evidence without an extra reward. Bulk and incremental shadow advancement produce identical forecasts and model state. Invalid/future forecasts cannot partly update a model. Warm-up/missing/end-mark/zero-return cases stay distinct. The forward decision clock can follow the candle close without admitting future outcomes. Experimental selection state cannot load through the approved trading profile. Paper forecast/error persistence, one-time learning and restart/account separation are covered by the existing journal transaction test with added assertions.

The initial concurrent test run exceeded three worker-completion deadlines. A separate run resolved two; the deliberately dense gap fixture still exceeded 30 seconds with three research variants and forecast scoring. Its completion deadline is now 60 seconds, and two full-practice 5-second deadlines use 30 seconds. No production timeout was changed. The final full suite ran without the large real-data replays competing for CPU and completed successfully; no timing check was skipped.

The same source is replayed against pinned V11.6 on supplied DOT, XRP and AVAX snapshots with identical costs and reviewed boundaries. Final primary results remain $0.00, -$6.03 and -$5.61 respectively; higher-cost results remain $0.00, $0.00 (no XRP trades) and -$4.33. Earlier primary folds are unchanged. The conditional selection experiment has mixed earlier-period results and no final-period improvement; it remains unable to control trading. All markets fail qualification and no unseen confirmation prices are present.

Final-source replays matched all 50 substantive result fields in each DOT, XRP and AVAX repetition (creation time excluded). Their lab-source SHA-256 is `5c2c909f32963c0a17aaa763ab4a51ba724e3eaac138169f0b6d067f0a16c190`. The compact record contains matching input/source hashes and paired results.

The entry audit exposes overprediction in the five selected XRP and three selected AVAX trades. This is a better account of forecast mistakes, not demonstrated profit improvement. See [the design and measured results](ENTRY_LEARNING_RESEARCH.md), [the compact record](research_baselines/entry-learning-comparison.json), and `scripts/compare_entry_learning.py`.

# V11 verification

## 16 September 2026: V11.6 fuller candle context and loss severity

**234 Python tests passed in 71.381 seconds.** New tests verify that entry-time rejection/extension inputs distinguish outcomes the old vector could not, match full and compact candle features, use preceding resistance, and never include exit reviews or later candles. They also verify that a severe gap loss retains its actual size in recent economic moments and prediction-error penalties while weights remain finite and bounded. Invalid old vectors and numerically unusable labels cannot partly update a model. A worker completion test now has the same 30-second budget as the other full-practice test; its original five-second deadline failed only under concurrent replay load and passed alone in 2.141 seconds.

Both actual dashboard checks passed, including the new entry-context explanation, supplied report 19 and finance account separation. Python compilation, JavaScript syntax and diff checks passed. No hosted/mobile visual test, real order or deployment was performed.

Pinned V11.5 and revised V11.6 use identical DOT/AVAX snapshots, completed daily data, costs and reviewed-history boundaries. Independent development examples and diagnostics are unchanged. Ordinary-cost selected trades and final net results remain identical: DOT 0 trades/$0, AVAX 3 trades/-$5.610306. AVAX's higher-cost loss changes from -$5.989253 to -$4.329739, and its second earlier fold rises from $5.582693 to $7.826429; no other earlier ordinary-cost fold changes. Neither market qualifies. The account-feedback controls still fail profitability. There are no new downloaded candles or fresh confirmation prices in these comparisons.

See [the declared design, sources and full results](CANDLE_CONTEXT_RESEARCH.md), [the compact comparison](research_baselines/candle-context-comparison.json) and `scripts/compare_candle_context.py`. The published update includes the earlier finance panel, monitoring repair and non-trading exit experiment. Models must be rebuilt under the new 27-input policy before qualification.

## 15 September 2026: V11.5 causal exit learning and integrated finances

**229 Python tests passed in 63.927 seconds** after integrating the main-screen finance changes. The new regressions check fee-covered zero-reward exits, prior-close/next-candle timing, same-bar and wick ambiguity, losses through gaps, unknown missing-price outcomes, short-side algebra, causal shadow feedback, additional trades after earlier exits, model/profile separation, and paper/Coinbase rejection of the research-only exit. Readiness tests cover unused timeframe gaps, required timeframe gaps, newly completed candles and separate Coinbase model selection. Checkpoints resume identically after interruption in both the original and experimental model, with no label overlap. Tests use synthetic fixtures and submit no exchange orders.

Both dashboard JavaScript checks passed, including the new whole-account comparison, supplied report 19, separate financial accounts, complete ledger totals, old saved reports, stale updates and escaping. Both scripts passed syntax checks; Python compilation and diff checks passed. These are mocked-document checks, not a hosted/mobile browser verification.

The exact supplied DOT and AVAX candle snapshots were run against V11.4 and the combined revision. With identical costs and reviewed-history boundaries, the current model's weights, observations, selected trades and reported account metrics match exactly. The independently trained exit model selects zero DOT trades for $0 and the same three AVAX trades for **−$5.610306**, or **−$5.989253** at higher costs. It creates more near-break-even development examples, but does not improve either final account result and passes no qualification. Its returned comparison contains no model that could be installed as a forward profile.

See [the declared experiment and results](EXIT_LEARNING_RESEARCH.md), [the compact comparison](research_baselines/exit-learning-comparison.json), and `scripts/compare_exit_learning.py`. All report-19 market endpoints are registered as reviewed history. Requests for additional hosted-app/Coinbase data timed out; these are tests of the provided snapshots, not newly retrieved data. No deployment or real-money execution was performed.

## 15 September 2026: main-screen trade finances

**217 Python tests passed in 40.252 seconds.** Eight new regressions cover net-result reconciliation, exact zero versus tiny losses, complete paper/Coinbase journals beyond visible table limits, open/rejected-order exclusion, account separation, restart persistence, incomplete historical reports, cached recovery from existing saved reports, unchanged original exports and Coinbase authentication boundaries. No request placed an exchange order.

Both dashboard JavaScript check scripts passed. The finance checks exercise account and market selection, after-cost totals, empty and locked states, escaping, stale refresh failures and the actual Coinbase status-event connection. Syntax and whitespace checks passed. Browser rendering and iPhone layout have not been visually verified in this environment.

The supplied partial report 17 reconciles across its nine completed market simulations: 20 selected test trades, 6 wins, 14 losses, $37.059234 in positive net outcomes and $52.319662 in negative net outcomes, for -$15.260428 total. These are separate historical accounts, not one portfolio, current website balances or real-money profits. No strategy, qualification, model or risk setting changed in this display update; no new market-performance claim is made.

## 15 September 2026: V11.4 loss and break-even study

**209 Python tests passed in 35.972 seconds.** New coverage checks actual after-cost outcome bands, review priority without duplicated evidence, fee-covered break-even calculations, next-candle activation, stop-first ambiguity, adverse gaps, future-data isolation, incomplete post-exit windows, bounded case selection, exact checkpoint resumption and persisted paper/Coinbase reviews. Paper positions predating quote-path tracking retain unknown excursions. Independent practice continues after loss streaks while account simulations keep their existing pauses. No test submitted an exchange order.

The actual dashboard JavaScript passed Node-based checks against report 17 and new review fixtures, including outcome counts, after-exit availability, the fixed exit experiment, paper journal details, escaping and download handoff. These mocked-document checks do not establish hosted operation or mobile layout.

The final source replay used the supplied AVAX 15m and separate daily candles with matching canonical hashes. Development examples increased from **10,279 to 11,270**, including **229 near-break-even outcomes**. All completed development outcomes were counted; detailed reports retained 82 priority cases. The selected account still made the same three trades and lost **$5.610306** at ordinary costs and **$5.989253** at stressed costs. The fixed +1 net R break-even-stop experiment never activated on those trades. Qualification remains rejected and no account-profit improvement is measured.

Report 17's nine completed market windows are now registered as reviewed history. The AVAX replay has no fresh confirmation window. Costs, strategy candidates, account risk and qualification gates were not fitted to this report. [The research note](TRADE_REVIEW_RESEARCH.md) documents the fixed rules, concrete loss patterns, reproduction command and limitations; [the comparison](research_baselines/avax-v11.4-comparison.json) records input/source hashes and results. This revision has not been deployed or validated against real fills.

## 15 September 2026: V11.3 outcome memory and data recovery

**195 Python tests passed in 14.35 seconds.** New checks exercise comparable-context losses, fee-erased gains, recovery after later successes, finite/consistent outcome state, direct and complete smaller-bar recovery, cancellation/request bounds, persistent recovery provenance, daily joins without future information, intraday gap warmup in replay and monitoring, daily input cache identity, explicit rechecks and exact daily exports. Existing execution, qualification and separate account-journal tests continue to pass.

The actual dashboard JavaScript passed Node-based checks against the supplied report 16 and fixtures for the new failure table, recovery counters, context availability, memory comparison, escaping and download handoff. This is a mocked-document check, not verification of a deployed website or mobile layout.

The real supplied DOT bundle reproduces the prior report's canonical data hash. The fixed revised 15m replay learns 9,797 development examples; complete 1h aggregation learns 3,035. Both have zero profitable later folds and zero selected final-period account trades at ordinary or stressed costs. Both reject qualification. The memory-disabled controls also return $0, so measured account-profit improvement is $0. See [OUTCOME_MEMORY_RESEARCH.md](OUTCOME_MEMORY_RESEARCH.md) and [the machine-readable comparison](research_baselines/dot-v11.3-comparison.json).

Additional Coinbase requests timed out. Actual recovery of the 71 missing supplied intervals and performance with independent daily downloads remain unverified on real additional data. Newer data, portfolio performance, hosted execution and real fills have not been validated. No exchange order or deployment was performed.

## 15 September 2026 cost-aware learning and reproducible exports

**182 Python tests passed in 12.13 seconds** with production dependencies available. The new regressions cover signal-time cost inputs, separately learned cost groups, pre-update prediction-error penalties, and continued feedback when selected account trades are zero. Historical shadow outcomes agree with the shared execution engine; changing future prices cannot alter earlier labels. Missing-price outcomes and forced end-of-window closes are excluded, and account closures are not learned twice. No test placed an exchange order.

Qualification checks reject profitable but previously reviewed history without new confirmation. They also reject positive shadow results when the selected-account-feedback control loses, including on the fresh price window. Export checks cover authentication, exact report dates and candle count, canonical SHA-256 matching, changed-price rejection, path traversal, and explicit handling of older reports without a digest.

The actual dashboard JavaScript passed Node-based checks with the supplied `learning-results 12.json`, the new training/account counts, fee attribution, both confirmation results, escaped strings, and the attached download link with delayed object-URL cleanup. JavaScript syntax and diff checks passed. These checks use a mocked document and do not establish Safari download behavior, mobile rendering or the live Render deployment.

The supplied report contains 130,625 development examples but only 32 selected final-test trades across 13 separate market simulations, with no qualified market. It contains no raw candles. A fresh Coinbase download timed out in this workspace, so this revision has **no measured profit improvement yet**. The new export makes the saved candles available for a reproducible subsequent review. Fees, strategy rules and account-risk settings were not fitted to the report. Models and labels must rebuild under engine V11.2, policy v5 and report 7; cached market history and account records are preserved. The exact changes, source evidence and limitations are in [LEARNING_IMPROVEMENTS.md](LEARNING_IMPROVEMENTS.md).

## 15 September 2026 research strategy additions

**162 Python tests passed.** Eight new tests cover completed-day availability, non-repainting after future-price changes, full daily warmup after a missing candle, agreement between replay and the paper runner with a shorter decision cache, and exclusion of future higher-timeframe bars. They also cover each new rule, full fee deductions on flat prices, preserved entry-gap limits, bounded sizing and shared daily-ATR stop distances in simulation, paper trading and Coinbase order planning.

The expanded-policy test verifies that a better original-strategy comparison cannot replace a losing expanded holdout or grant qualification. Existing checks for gap-censored outcomes, training-label timing, cache restart/version boundaries, loss limits and exchange failure handling still pass. The 22 candidate keys are distinct. No test placed an exchange order.

Dashboard rendering checks using the actual JavaScript functions passed with the user's existing report, strategy-group counts, negative comparison values and escaped text. JavaScript syntax and diff checks passed. These checks do not establish Safari/mobile rendering or production deployment.

No new market-performance backtest was completed in this environment. The attached report contains results rather than raw candles, and no return improvement is claimed. After deployment, rerun practice using saved/downloaded real Coinbase candles and verified fees. The engine, model and report version changes invalidate incompatible qualification/label caches while retaining market history and account data. Source review and exact hypotheses are in [STRATEGY_RESEARCH.md](STRATEGY_RESEARCH.md).

## 15 September 2026 expanded practice selection

**154 Python tests passed.** New checks cover the 13-market default list (10 additions to BTC/ETH/SOL), API normalization and duplicate removal, saved selections across service reconstruction, and continuation after a market-history failure. Invalid and over-limit lists are rejected before settings change. Historical practice accepts up to 20 markets and processes them sequentially.

Node-based interaction checks verified the 13 defaults reach the practice API with unchanged fees, short/full tickers normalize, duplicate symbols collapse, blank/invalid/over-limit inputs do not submit, saved choices load, and subsequent status updates do not overwrite unsent edits. JavaScript syntax and diff checks passed. These checks use fixtures and a mocked document; they do not verify each market's current Coinbase history availability or mobile layout. Each actual download remains subject to the existing real-data validation and per-market errors.

The supplied completed `learning-results 9.json` reports 9,571 BTC, 9,515 ETH and 10,270 SOL training examples (29,356 total); all three remain unqualified with zero final-test trades. Adding markets expands the research universe and does not establish profitable performance.

## 15 September 2026 exported-report training repair

The supplied `learning-results 5.json` is an actual application export reporting Coinbase Exchange prices. In that older run, BTC had 3,436 signal matches and all 3,436 entry attempts failed the cost screen. ETH had 3,160 matches, 3,155 cost blocks, one net-reward block, and four completed examples. Only 12,461 candles per market were retained; 92,602 BTC and 92,600 ETH candles before the final gap were discarded. The export contains report aggregates and models, not the raw candles, so these observations do not independently verify the source prices.

**151 Python tests passed with production dependencies available.** New regressions verify that both observed sections around a gap survive, indicators restart causally, short sections have no entry features, and history too fragmented for warmup is rejected. Cost-rejected training examples pay full entry/exit fees and slippage and can teach negative outcomes; policy entries retain the cost gates. Missing prices cannot cause an entry jump, an invented exit, an unknown training label, or a qualifying incomplete account result. Existing causality, qualification, restart/checkpoint, cost, paper, and Coinbase controls also passed.

A service integration test exercised historical practice, saved examples, JSON report download, and reconstruction from the same database with the updated versions. It retained both fixture price sections, exported nonzero costed examples and model observations, kept the original fee, and installed no qualifying model for a losing fixture. Trading runners remained stopped. These deterministic fixtures check behavior; they are not real market performance.

JavaScript syntax, Python compilation, and diff checks passed. Node-based dashboard checks exercised costly examples, missing outcomes, retained-history descriptions, incomplete results, and obsolete model labels with a mocked document. These are rendering-logic checks, not a Safari/mobile browser verification. A fresh run on the user's cached Coinbase candles and deployment of this patch are still required; neither profitability nor a better final-test return is claimed.

## 15 September 2026 pre-opening check

**140 Python tests passed with the production dependencies installed**, using Python 3.12.14. Two new regressions reproduced failures before the fixes: manual practice reused a failed download until the automatic retry deadline, and a rejected automatic-start request changed the fee setting while another task was active. Manual retries now bypass failed results' backoff, while automatic polling retains it; rejected starts preserve settings.

Installed Gunicorn 23.0.0, Coinbase Advanced SDK 1.8.4 and the remaining requirements in an isolated dependency directory. Both Coinbase REST/WebSocket client imports succeeded. All 11 SDK methods used by the adapter exist; explicitly supplied argument signatures were checked. This does not verify authenticated account responses or real order execution.

Started the actual `app:app` entry point under Gunicorn with one worker, eight threads and a 300-second timeout, using a temporary database and disabled live execution. Verified over HTTP:

- Dashboard HTML, three static assets and the public health endpoint.
- Eleven private status/export endpoints, rejection of missing/incorrect tokens, JSON/CSV exports and a valid SQLite backup header.
- Malformed JSON, invalid body types, content types and payload-size limits.
- Historical-practice start, rejection of an overlapping automatic start without changing fees, immediate retry after a failed download, and stop controls.
- Twenty-four concurrent dashboard requests during a download, all returning successfully while the paper runner remained stopped.
- Process restart with the same database: fees persisted and learning/paper runners remained stopped.

The real Coinbase history request again timed out. The app reported the error with zero downloaded training hours and no active model; it did not invent a dataset or a successful report. There is still no verified real-market training result or profitability evidence.

Added a Python 3.12 runtime selection for Render and updated the existing-service deployment instructions. Python compilation, both JavaScript syntax checks, launcher shell syntax and diff whitespace checks passed. Browser preview navigation was blocked by the environment (`ERR_BLOCKED_BY_CLIENT`), so browser interactions and mobile rendering remain unverified. The actual Render service was not deployed or inspected. Earlier entries below record the checks available at those stages; this entry supersedes their dependency-installation and local-server limitations.

## 15 September 2026 direct historical practice

**138 offline Python tests passed**, including eight new checks of the historical-practice control and Coinbase download command. They verify that historical practice does not start the live scanner, paper runner or Coinbase runner; a failed download never invokes learning or creates a substitute report; invalid requests do not mutate fee settings; the existing app token is required; and command-line intervals/end dates and source labels reach the report correctly. JavaScript syntax and diff whitespace checks passed.

The real command `python run_research.py --coinbase --learning --symbol BTC-USD --interval 1h --days 365 --end 2025-01-01` was attempted with a separate empty cache. Coinbase's public request timed out; the command exited with status 1 and did not produce a training report. Tests use fixtures to exercise software behavior, and are not substitutes for the requested real historical run. That run still needs access to Coinbase from the machine hosting the app.

## 15 September 2026 regime and training upgrade

**130 automated offline Python tests passed**, including 13 additional tests for cost-aware candidate choice, regime-specific learning, sparse-evidence fallback, non-finite/old model rejection, UTC daily loss halts, gap handling, checkpoint recovery and per-market review deadlines. A resolved-label checkpoint run resumes to the same trained model and final results as a fresh run. The causal holdout regression also verifies that a better pooled diagnostic cannot replace a losing updating policy. JavaScript syntax and diff whitespace checks passed.

An end-to-end `run_research.py --learning` invocation processed 12,000 artificial hourly candles using random seed 61904 and alternating drift conditions. It took 0.89 seconds and 40.6 MiB peak child-process memory in this workspace. It generated 411 development examples, made three final-period trades, lost $2.61 in that period and failed qualification; higher costs prevented all final-period trades. This checks processing and rejection behavior, not market profitability. No thresholds were fitted to this artificial trial.

A real Coinbase historical download did not complete here. Actual historical performance, improvement over the pooled baseline, Render operation and Coinbase execution remain unverified. The code requests real history when automatic learning runs on the user's server; it contains no pretrained profitable model.

## 15 September 2026 follow-up

**117 automated offline Python tests passed**, including seven new tests for learning diagnostics, changed-market reviews, versioned caches, and bounded retry scheduling. JavaScript syntax and diff whitespace checks passed. Diagnostics cover both valid signals blocked by costs and candidates blocked by insufficient or weak learning evidence; checks also verify that reporting does not update model weights or invent trades.

A public Coinbase candle request timed out in this environment. Real historical performance, the deployed Render service, and real Coinbase execution were not verified by this follow-up.

## Original V11 verification

Verified during the 9 September 2026 UTC upgrade.

**110 automated offline tests passed** using Python 3.12. The final suite completed in under two seconds. JavaScript syntax validation, Python compilation, and the Mac/Linux launcher's shell syntax check also passed.

Reproduce the automated suite from the extracted project directory:

    python3 -m unittest discover -v

The tests use temporary databases, artificial candle fixtures, and mocked exchange responses. They do not submit orders, access an account, or establish any trading edge.

## Covered behavior

| Area | Checks |
| --- | --- |
| Signal chronology | Latest completed candle is available; adding future data cannot revise past features; configured decision interval is used |
| Candle handling | Complete four-hour aggregation; paginated requests stay within 300 buckets; current, duplicate, misaligned and invalid bars are rejected |
| Paper execution | Next-candle fills; entry-candle stops; adverse gap fills; conservative ambiguous exits; no same-bar reentry; cooldowns |
| Costs and sizing | Both entry and exit fees; slippage; flat trades lose costs; actual risk reflects the position cap; account-wide exposure and risk limits |
| Account state | Restart recovery; persistent cooldowns and daily loss latch; atomic closure rollback under an injected failure; unique learned observations |
| Controls | Pause preserves existing stop monitoring; stale prices prevent fills; invalid settings cannot partially apply; reset refuses open trades and creates a usable backup |
| Historical research | Fixed 16-candidate population; frozen holdout parameters; no-trade-day statistics; ability to reject every strategy; cancellation preserves downloaded chunks |
| Dashboard API | Page/static assets; status, journal, research and analytics responses; malformed request handling; optional token enforcement; CSV/JSON/database exports |
| Process guard | A second runtime cannot acquire the same account's trading lock |

The Python application handlers were exercised directly through their WSGI interface, without launching a browser or network server. Dashboard element references were checked against the HTML and the JavaScript parsed successfully.

## Coinbase additions covered offline

- Local live opt-in, typed activation, token-protected controls and redacted account status.
- No create/cancel in preview mode; no write through an unarmed adapter.
- Durable intent before submission; timeout recovery by original client ID; unknown outcomes block further entries.
- Actual cumulative fills and USD fees; settlement before realizing P&L; no duplicate accounting.
- Partial bracket fills and fills during cancellation; residual-only exits after terminal confirmation.
- Incomplete market exits, missing protection, dust, explicit rejection and excessive preview costs.
- Permission completeness, dedicated balances, portfolio identity binding, quote freshness, account pagination and decimal increments.
- Persistent daily loss latch and manual close request, separate from paper account state.
- Passing historical profile required even when unvalidated paper experiments are enabled; matching current signal features.
- Coinbase dashboard element references and fee-setting refresh wiring.

## V9 additions covered offline

- A gross 2:1 payoff can fail the net-payoff test after costs; Decimal and short-side arithmetic remain consistent.
- Research uses the longer cooldown only after losses are closed; paper cooldowns persist after restart.
- Order-book VWAP accounts for quantity at each price; liquidity outside allowed prices is excluded.
- Missing, stale, unordered, duplicated and non-finite depth blocks new entries.
- Liquidity disappearing during preview prevents submission; exit monitoring is unaffected.
- Live cooldowns survive restart and expire without requiring a new closed trade.
- The frozen-rule comparison reports a negative upgrade difference when the fixture produces one. It cannot switch the selected parameters based on holdout results.
- V9 engine identity requires new historical qualification; older results are labeled in the dashboard.

## V10 additions covered offline

- Every combination of the three confirmations; at least two are necessary.
- Confirmations cannot bypass the breakout, regime, volume, overextension, or volatility guards.
- The new rule routes through the shared next-bar execution engine and can be rejected after costs.
- Final training/validation evidence includes all 16 candidates and no more than five validation finalists.
- An artificially profitable training candidate that loses in the holdout stays the frozen winner and fails qualification; the researcher cannot switch to a different rule after seeing later prices.
- The hosting YAML was parsed and its persistent paths, one-worker command, access token, and disabled live mode checked locally. The WSGI entry point was checked with temporary persistent-path environment settings. These checks do not exercise Render or install Gunicorn/the Coinbase SDK.

## V11 additions covered offline

- A loss lowers and a success raises the learned estimate for the same setup; predictions alone do not update weights.
- Sparse samples cannot authorize a trade, JSON model state round-trips, and invalid/non-finite inputs are rejected.
- Compact historical features match the shared features and cannot be revised by appending future candles.
- Simulated feedback arrives only after a trade closes and uses its stored entry vector.
- Changes to final-period outcomes cannot alter the pre-holdout model. A better frozen diagnostic cannot replace a losing updating policy.
- No-example history is rejected and the pipeline can be cancelled.
- Paper feedback persists through restart and updates once; transaction failure rolls back both journal closure and learning.
- Settled live-trade records train only the Coinbase model, once; a journal write failure rolls back feedback.
- Expired or cost-mismatched models cannot trade, even when validated_only is false; mismatched-cost feedback is excluded.
- Automatic start invokes the paper/learning workflow without invoking Coinbase activation. A restored controller remains stopped.
- Automatic study requests three years, reuses an identical cached result, and protects status/export with the existing app token.

An additional artificial flat-price dataset with 105,120 candles completed in 5.51 seconds with peak resident memory of 215.5 MiB. It produced zero training examples and was rejected. This only checks processing volume in this workspace; it is not real historical training or profitability evidence.

## What is not verified

- **No real V11 historical profit result.** The supplied archive contained no historical dataset or running account database. Dependency installation now succeeds; real Coinbase historical downloads still time out in this workspace.
- No end-to-end Coinbase WebSocket or REST download run. Pagination, parsing, and failure controls were tested with mocked responses and checked against official API documentation.
- No authenticated Coinbase account integration or real fills. SDK imports and method signatures were checked; exchange constraints, permissions, uncertain submissions and partial-fill reconciliation were exercised with offline mocks. Actual account compatibility remains unverified.
- No browser-based visual/interaction test because preview navigation was blocked, and no actual Windows launcher run.
- No multi-week unattended runtime test, real outage drill, or hosted deployment.
- No portfolio-level historical validation of combined markets and live execution controls.
- No proof that the $10–$15 daily goal is achievable, or that V11 outperforms earlier versions. The paired comparison needs actual market history and the user's real fee tier.

The delivered artifact is a complete research, paper-trading and experimental Coinbase source package. A passing software test is evidence about code behavior, not evidence of profitability.
