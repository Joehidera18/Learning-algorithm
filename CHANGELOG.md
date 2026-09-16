# Entry prediction accountability — 16 September 2026 UTC

- Save entry forecasts before outcomes are known, including independent candidate practice. Score only normally resolved trades; mark cold models, missing forecasts, final end marks and unresolved gaps separately.
- Track actual entry forecast squared errors separately from optimizer residuals at closure. After 30 scored forecasts, use the larger error margin. Actual rewards still train once and retain their full economic magnitude.
- Advance historical candidate feedback in candle order even for bulk calls. Apply a candle's resolved outcomes before the next candle's entry forecasts, with deterministic same-time ordering.
- Preserve forecasts in paper and Coinbase learning records; learn their errors atomically with journal closure. Show entry estimates in the paper journal and forecast/outcome summaries in historical reports.
- Add a separate conditional selection study, retaining costs, contextual estimates, error margins, sample minima and risk limits. Its state cannot load as the approved trading model and its report exposes no model.
- Register the completed V11.6 report as reviewed history, add a pinned before/after replay script, and require fresh practice with engine `market-structure-v11.7-entry-audit`, policy `online-net-r-v10-entry-audit`, report 12.

# Fuller candle context and loss severity — 16 September 2026 UTC

- Expand adaptive inputs from 19 to 27 with closed-candle wicks, RSI change, preceding support/resistance, rolling VWAP-proxy distance, ATR regime and prior compression. Use fixed scales and identical features in historical, paper and Coinbase learning.
- Retain full realized returns in recent economic memory and variance. Measure raw pre-update residuals for the model's ranking penalty; bound the optimizer update instead of hiding large losses in economic statistics.
- Identify the learning inputs in reports and explain the richer context on the dashboard. Preserve entry candidates, costs, risk limits, chronological label release and qualification rules.
- Add a declared comparison with pinned V11.5 on identical DOT and AVAX snapshots, with input/source hashes and no winner selection. All supplied dates remain reviewed history.
- Versions: engine `market-structure-v11.6-candle-context`, policy `online-net-r-v9-candle-context`, report 11. New practice is required after deployment. Includes the earlier finance and exit-study work.

# Causal exit learning and monitoring parity — 15 September 2026 UTC

- Fix adaptive paper and Coinbase signal readiness to require the chosen decision timeframe. Unused higher-timeframe gaps no longer add a different filter from historical replay. Retain daily-context entry checks, legacy multi-timeframe readiness, quote timing, risk limits and activation controls.
- Train a separate 22-candidate break-even-exit model on its own completed outcomes. Activate fee-covered protection only on the candle after a close at +1 net R; preserve targets, time limits, gap losses and original risk. Treat an algebraically zero exit as break-even without a floating-point win/loss reward.
- Recompute the entire account path, online feedback, ordinary/higher costs, folds and account-feedback controls. Display the comparison under each market's loss study. This model cannot replace an approved profile, qualify a market or enter paper/Coinbase positions.
- Keep independent checkpoint namespaces for both models; register all 13 markets in report 19 as reviewed history. Include a reproducible same-data comparison with V11.4. DOT and AVAX final account results are unchanged; no profit improvement is demonstrated.
- Versions: engine `market-structure-v11.5-exit-study`, policy `online-net-r-v8-exit-study`, report 10. Fresh practice is required after deployment.

# Main-screen trade finances — 15 September 2026 UTC

- Add a finance panel above learning controls with completed trades, money won/lost, net result, wins, losses, exact break-even outcomes and win rate.
- Keep historical tests, paper money and Coinbase bot results in separate selectable views. Identify incomplete historical coverage and forced test-window exits.
- Total complete saved journals rather than the latest visible table rows. Recover historical totals from saved reports without retraining or altering the exported source reports.
- Preserve Coinbase authentication, report refresh failures visibly and keep all trading behavior unchanged.

# Loss and near-break-even study — 15 September 2026 UTC

- Continue independent training at normal entry spacing after losses, without account loss-streak pauses. Preserve full costs, risk sizes, signals, missing-data rules and actual account controls.
- Define near break-even as within 0.10 net R and prioritize detailed review of these outcomes and losses. Preserve their true rewards and count each observed outcome once.
- Record net price excursions, giveback, fee drag and entry context. Add period-bounded 1h/4h/24h after-exit observations and one fixed, next-candle break-even-stop experiment. These hindsight diagnostics never enter entry decisions or substitute rewards.
- Save available close-time reviews in paper and settled Coinbase journals; retain historical development summaries through checkpoints and include reviews in dashboard/export output.
- Record report 17 as reviewed history, add exact AVAX reproduction, and avoid repeatedly scanning an entire loss history or rebuilding the same candidate-key set.
- Versions: engine `market-structure-v11.4-trade-review`, policy `online-net-r-v7-trade-review`, report 9. Existing models require fresh practice and qualification.

# Outcome memory and candle context — 15 September 2026 UTC

- Learn recency-weighted net outcomes by strategy, cost burden, intraday regime and completed daily trend. Keep gross returns and fees reconciled; distinguish fee-erased gains, stops and time-exit losses. Share attribution across replay and separate paper/Coinbase journals.
- Retry gaps and reconstruct only complete smaller-interval Coinbase observations. Fetch independent completed daily candles, join them as of the signal close and expose remaining missing data. Match replay's intraday gap warmup in ongoing monitoring.
- Recheck data on explicit practice, hash both data sources into cache identity and export the exact daily inputs. Keep existing fees, risk, candidates, account controls and qualification requirements.
- Record report 16 as reviewed history. Include a fixed 15m/1h reproduction script and a memory-disabled comparison. Both DOT final tests selected zero trades and made $0; profitability is not demonstrated. Direct additional Coinbase retrieval timed out here.
- Versions: engine `market-structure-v11.3-outcome-memory`, policy `online-net-r-v6-outcome-memory`, report 8. Old models require fresh practice and qualification.

# Cost-aware learning — 15 September 2026 UTC

- Use signal-time cost, net reward/risk and holding period in the 19-input learner. Separate low, moderate and high cost evidence and apply a pre-update prediction-error penalty.
- Continue historical feedback from unselected candidates through the shared simulator, releasing only resolved outcomes and keeping account cash separate.
- Add an account-only feedback control and require it to pass at both costs. Mark report-12 history as reviewed and require newer-price confirmation for revised models.
- Show separate training/account counts and strategy fee attribution. Export a per-market candle/report ZIP with a checked dataset digest.
- Preserve candidate definitions, fees, stops, account risk, journals, saved candles and separate Coinbase activation. Bump engine, policy and report versions to rebuild incompatible models.

# Research strategy additions — 15 September 2026 UTC

- Add six fixed candidates across daily trend/momentum, volatility expansion and support with RSI recovery, bringing the population to 22. Document primary research, exact adaptations and limits in STRATEGY_RESEARCH.md.
- Build daily indicators from complete UTC days only; reset daily warmup at gaps. Reuse the existing paper-runner history with a strict signal-time boundary.
- Use daily ATR for the new brackets and decision ATR for entry-gap limits. Preserve dollar-risk, fee, qualification and real-money activation controls.
- Show training examples by strategy and final-test differences against the original 16 candidates. Comparisons cannot choose a winner or change qualification.
- Advance the engine, policy and report versions; retain saved candles and account state while requiring fresh model qualification.

# More historical-practice coins — 15 September 2026 UTC

- Add 10 defaults to BTC, ETH and SOL: HBAR, XRP, XLM, ADA, DOGE, AVAX, LINK, LTC, BCH and DOT.
- Add an editable, saved list of up to 20 Coinbase USD markets. Accept short tickers or full USD product names; normalize case and remove duplicates.
- Process selected markets sequentially and report individual unavailable histories. The selection applies to historical practice; the continuous scanner and real-money allowlist retain their existing behavior.
- Preserve fees, qualification, history checks and trading activation.

# Historical training repair — 15 September 2026 UTC

- Keep recorded price sections before and after gaps; restart indicators with 240 observed warmup candles and never fill missing prices.
- Let independent historical examples explore cost-rejected setups with full fees and slippage charged. Preserve policy qualification, trading costs, signal, sizing, and account controls.
- Exclude unresolved training outcomes across missing prices. Mark policy tests interrupted with an open position incomplete and ineligible instead of inventing an exit or account return.
- Separate signal failures, entry failures, explored costly setups, and unknown outcomes in the dashboard and report. Label old reports for fresh practice.
- Advance policy to `online-net-r-v3-historical-exploration` and report to version 5. Reuse saved candles; require fresh model qualification.

# Direct practice on real history — 15 September 2026 UTC

- Add **Practice on real market history** to run accelerated learning on recorded Coinbase BTC, ETH and SOL candles without starting a live ticker, scanner or trading runner. Existing runners are not restarted or stopped by this action.
- Add a direct `--coinbase --learning` command, an exclusive historical `--end` date, 30–1095 download days and a reusable candle cache. Separate symbols and 5m/15m/1h intervals can be studied with separate runs.
- Show the price-data source and actual training/final-test dates in reports. Failed downloads return errors without creating replacement prices or training a new model; supplied CSV sources remain labeled unverified.
- Advance report version to 4. Keep the same causal simulator, qualified-model installation checks and separation of historical practice from current-market account trades.
- Add eight focused workflow and command tests; all 138 offline tests pass. The actual Coinbase download command was attempted here but the request timed out. No real-market training result is claimed.

# Regime learning and resumable training — 15 September 2026 UTC

- Learn separate entry-condition estimates for rising, falling and sideways markets, blended with pooled evidence after a minimum sample count. Count each resolved outcome once. Keep the existing long-only strategy templates and historical qualification thresholds.
- Check fees, slippage and net payoff at the known signal close before ranking candidates; still validate entry gaps and costs at the actual modeled fill. A cost-infeasible favorite no longer blocks a feasible alternative.
- Apply the configured UTC daily loss halt during adaptive policy tests, including conservative intrabar marks. Report fees and halted days; preserve account accounting and monitoring of existing positions.
- Add ordinary/stressed comparisons with pooled learning and cash/buy-and-hold benchmarks. A favorable diagnostic cannot replace a losing updating policy or change qualification.
- Disclose actual continuous history used after missing candles, reject invalid prices or too-short suffixes, and never invent missing bars.
- Save completed candidate labels, pin training cutoffs across restarts within 24 hours, and discard incompatible checkpoints. Review rejected markets daily, qualified markets every 28 days, and failed downloads hourly, independently per market.
- Add `run_research.py --learning` for historical CSV evaluation. Advance policy and report versions and include daily-loss settings in qualification signatures; previous models need retraining.
- All 130 offline tests pass. A 12,000-hour artificial CSV trial processed 411 development examples and correctly rejected its losing final-period result. No real-market profit or improvement has been demonstrated; see VERIFICATION.md.

# Learning diagnostics and automatic reviews — 15 September 2026 UTC

- Review newly selected training markets on resume instead of waiting for the previous universe's 28-day schedule. Reordering the same markets does not trigger another study; failed downloads retain the one-hour retry delay.
- Include policy and report versions in cached learning results and review scheduling so updated learners cannot silently reuse an incompatible report.
- Preserve per-variant training signal matches, simulated entries, completed examples, and rejection counts in learning reports. Surface common blocks in the dashboard and distinguish insufficient samples, nonpositive recent returns, and low estimated returns during replay and paper monitoring.
- Count candidate evaluations separately from account trades; overlapping variants do not become independent evidence. Entry rules, qualification thresholds, and real-order activation are unchanged.
- The first resumed study after this update regenerates reports using cached candles where available. Installing a new result follows the existing model-replacement behavior; prior trade journals remain saved.
- Added seven offline regression tests. All 117 Python tests pass. A public Coinbase candle request timed out in this environment; no real-market performance claim or hosted deployment was verified.

# V11 automatic learning — 9 September 2026 UTC

- Replace the main manual research flow with one Start learning & paper trading control.
- Request up to three years of completed history for five currently liquid Coinbase USD markets, with saved downloads and cached results.
- Train 16 small online net-R models from resolved hypothetical examples; select eligible templates using learned entry-condition estimates.
- Test the entire updating policy chronologically, including delayed outcomes, cost stress, a final holdout, and a frozen-policy diagnostic that cannot choose the winner.
- Learn from completed paper trades and settled Coinbase trades in separate, atomically updated model states. Preserve duplicate-closure protection and account limits.
- Add scheduled review while the controller runs, model expiry, cost-signature checks, report export, and a compact main dashboard.
- Reduce historical feature-cache memory by omitting unused structure features in the learning path.
- Add 18 regression tests; all 110 tests pass. The three-year-sized artificial-data performance check does not establish profitability.
- Advance engine identity to market-structure-v11.0. Existing profiles need fresh qualification; existing account/order journals must be preserved.

# V10 combined-signal research and hosting — 8 September 2026

- Add four fixed combined-signal variants, bringing the population to 16 in four families. A 20-bar breakout requires at least two of EMA alignment, RSI momentum, and positive quote-volume OBV change.
- Preserve the original 12 candidates and existing cost, exposure, cooldown, and execution controls.
- Export final training results for all candidates and validation outcomes for the shortlist; show the evidence in an expandable dashboard table.
- Advance engine identity to market-structure-v10.0; earlier profiles require new qualification.
- Complete the Render Blueprint with a persistent disk and state paths, token protection, explicit bind, one worker, and live submissions disabled. Add WEBSITE_SETUP.md.
- Add four focused regression tests. No historical profit or hosted deployment result is claimed.

# V9 trade-quality upgrades — 8 September 2026

- Require potential net target reward / modeled stop risk of at least 1.5 in all 12 research candidates, paper entries and Coinbase plans.
- Apply a six-hour per-market cooldown after three consecutive net losing closes; ordinary cooldown remains 15 minutes.
- Check visible Coinbase entry and immediate-exit depth before preview and again before submission.
- Show potential target profit and net reward/risk in the Coinbase preview.
- Add a frozen-rule historical comparison with the V9 payoff and cooldown filters disabled. Report improvements or deterioration without using that comparison for selection.
- Advance the engine identity to market-structure-v9.0, invalidate earlier qualifying profiles and label older dashboard results.
- Add 11 regression tests, for 88 total. No real historical superiority or live profit is established.

# V8 Coinbase changes — 8 September 2026

- Add the official Coinbase Advanced SDK adapter, loaded only when a local connection is requested.
- Sync portfolio balances, key permissions and actual maker/taker fee tier.
- Add separate preview and explicitly enabled live modes, with no automatic live resumption.
- Add a one-position spot runner with $500 capital / $150 entry-spend caps.
- Require matching historical profiles, current quotes and a successful protected-order preview.
- Record order intent durably before submission; recover unknown orders without duplicate submissions.
- Reconcile partial fills, exchange-held protection, confirmed cancellations and actual fees.
- Persist live daily loss state and trade-specific manual close requests.
- Add Coinbase controls and order journal; keep paper accounting separate.
- Add 30 offline regression tests, for 77 total; fix dashboard fee-setting refresh.
- Include setup and recovery instructions. Real account behavior and profitability remain unverified.

# V7 changes from V6

This release upgrades the supplied CryptO_Continuous_Learning_Lab_V6_COMPLETE.zip. It preserves the earlier archive and provides a separate complete source package.

## Trading and accounting fixes

- Include the latest completed candle in feature computation.
- Add a configurable decision interval and a regression check that prevents higher-timeframe processing from changing the selected signal interval.
- Fetch enough hourly history to warm up 4-hour features; omit partial 4-hour bars.
- Use completed exchange candles for volume rather than reconstructing volume from ticker messages.
- Cache features and setup rankings so dashboard reads do not repeat full strategy computation.
- Deduplicate market messages, reject stale/crossed/non-finite quotes, and stop stale data from creating entries or fabricated exits.
- Require new entries within 60 seconds of the signal candle closing.
- Check entry-candle stops; assume stop-first for ambiguous candles; simulate gaps at their worse available price.
- Measure actual stop risk after position sizing and notional caps, including modeled fees and slippage.
- Freeze each open paper position's cost assumptions so later settings changes do not rewrite its P&L.
- Commit trade closure, account balance, and learned observations in one database transaction.
- Recover open journal positions after restart and persist cooldowns and the daily entry halt.
- Remove double counting of the same trade in global and coin-specific learning.
- Validate all settings before changing any of them.
- Refuse resets with open positions and save a database backup before clearing a paper journal.
- Prevent a second process from running the same paper trading account.

## Research and reporting

- Add 12 explicit long-only candidates from three distinct hypotheses.
- Add chronological training/validation, three walk-forward windows, a final holdout, and higher-cost stress.
- Allow every candidate to fail. Default new entries require a current passing historical profile.
- Track daily dollar goals across all calendar days, including days with no realized P&L.
- Add cash and buy-and-hold benchmarks, net expectancy, drawdown, trade counts, rejection reasons, and a historical uncertainty interval.
- Download real Coinbase history in pages and checkpoint completed chunks for reuse after cancellation.
- Add CSV trade export, JSON research export, usable SQLite backups, a standalone CSV research command, and operating notes.
- Preserve manual refresh of setup rankings.
- Add 47 automated offline regression tests.

## Compatibility and scope

The V7 dashboard is served by a standard-library WSGI application. The existing Gunicorn one-worker entry point remains app:app. Legacy research modules and stored runs remain available, but the new dashboard uses the bounded V7 research path.

New research uses full target exits; legacy partial-profit backtest assumptions are not reproduced. New validated strategies are long-only. The code remains a research and paper-trading application, with no live-order endpoint or exchange-key handling.

No historical V7 profit result was verified during this upgrade. See VERIFICATION.md.
