# V11 verification

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
