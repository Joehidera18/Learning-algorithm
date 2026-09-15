# V11 verification

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

- **No real V11 historical profit result.** The supplied archive contained no historical dataset or running account database. Direct network access for dependency installation and historical market downloads did not complete in this workspace.
- No end-to-end Coinbase WebSocket or REST download run. Pagination, parsing, and failure controls were tested with mocked responses and checked against official API documentation.
- No authenticated Coinbase account integration or real fills. Exchange constraints, permissions, uncertain submissions and partial-fill reconciliation were exercised with offline mocks; actual SDK/account compatibility remains unverified.
- No browser-based visual/interaction test and no actual Windows launcher run.
- No multi-week unattended runtime test, real outage drill, or hosted deployment.
- No portfolio-level historical validation of combined markets and live execution controls.
- No proof that the $10–$15 daily goal is achievable, or that V11 outperforms earlier versions. The paired comparison needs actual market history and the user's real fee tier.

The delivered artifact is a complete research, paper-trading and experimental Coinbase source package. A passing software test is evidence about code behavior, not evidence of profitability.
