# News, market data and trading-concept review

Initial review: 2026-09-20 against commit `5390393a2e1634173a6f85dc2426ff8d5109071c` (draft PR #15). V11.13 implementation follow-up: later the same day.

## Current implementation status

The workspace connection recovered. The V11.13 follow-up implements and tests the repairs below; it supersedes the earlier documentation-only status. [Verification](VERIFICATION.md), [the event design](MARKET_EVENTS.md) and [the measured review record](research_baselines/observed-news-review.json) describe the current source. This remains a draft for review, without a merge or deployment.

| Reviewed issue | V11.13 result |
| --- | --- |
| Older gaps escaped the last-25 update window | Every retained gap is advanced; filled/expired states are removed |
| Inverse gaps persisted indefinitely | Retire on a close through the opposite boundary; all gaps expire after a fixed 240 bars |
| Repeated closes reset structure-break age | A confirmed swing can produce only one fresh break |
| Relative-return helper compared mismatched times | Require ordered unique timestamps and a complete paired window; explicitly identify missing coverage |
| Poll conflicts rewrote past source health | Reject duplicate source/timestamp records atomically |
| Missing dedicated world/project inputs | Add BBC World and six project publication feeds, with per-topic and asset-specific source coverage |
| News between signal, entry and closure was missing | Persist separate signal, entry and after-entry records; later observations remain review-only |

The 240-bar lifetime is a predeclared software definition, not a horizon selected for profit or a verified TJR rule. The relative-return helper is still not a confirmed-swing SMT strategy. These structure helpers remain outside the simplified adaptive training path; their repair is not evidence that they caused or fixed the primary learner's historical losses.

The live adapter check reached 13 of 14 sources and recorded 1,163 versions; Coinbase status timed out. On 105,062 previously supplied XRP candles, these later observations have zero historical coverage and reproduce the prior six-trade −$12.749657 result. No profitability improvement is established.

The newer `learning-results 9(1).json` and `AVAX-USD_5m_learning-data.zip` did not survive in the accessible workspace and remain unread. The surviving `learning-results 8.json` is an earlier unfinished report: 42/120 studies, 356,350 historical examples, no qualified markets and no forward trades. It is not a substitute for the newer report. Full course videos/transcripts remain unverified. Actual/consensus surprises, semantic article interpretation, verified upgrade/unlock schedules, full-depth market data and a forward price-only shadow account remain separate work.

## Historical inspection and proposed experiments

The sections below preserve the original pre-fix findings and concept map. References to missing functionality describe that inspected revision unless the current status above says it remains outstanding. The initial workspace interruption prevented a new-upload audit and executable tests at that time.

## Main finding

The project contains market-structure code, but the chronological learner calls `build_feature_cache(..., simple_only=True)` in lab/learning_research.py. That path returns before lab/structure.py runs. Its adaptive feature vector in lab/adaptive.py also excludes the structure/FVG/SMT fields. The forward dashboard can calculate structure without making those fields learned predictors.

The current candidate families are trend pullback, volume breakout, range reclaim and signal consensus. Connecting a concept to the learner requires an explicit feature/candidate experiment, an equivalent replay/live definition, model versioning and new confirmation data. Merely adding another indicator file would not accomplish this.

PR #15 already adds timestamped news/calendar history, source-health records, seven event inputs, a price-only comparison and entry-context recording. Its seven feeds cover Fed monetary/regulatory releases, SEC releases, BLS/FOMC schedules, Coinbase incidents and CoinDesk headlines. It does not yet provide dedicated geopolitical coverage, project-specific announcement adapters, article interpretation, macro consensus/actual surprises, or a comprehensive historical news archive.

## Code-inspection findings to fix or test first

1. **Old FVGs can escape invalidation.** lab/structure.py only revisits the last 25 gaps on each side, but chooses an active gap from the entire accumulated list. An older unfilled gap can leave the update window, subsequently be invalidated by price, and later reappear as active when newer gaps are inactive. Track every retained active gap or explicitly expire and remove older ones. Test with more than 25 gaps and a later invalidating candle.
2. **Inverse-gap flags have no lifetime.** A gap marked inverted remains selectable indefinitely; no subsequent invalidation or expiry clears the inverted flag. Define and test the intended retest/invalidation rules before exposing these flags as learned features. This finding does not establish that it caused losses in the current simplified learner.
3. **Break of structure is a persistent condition in some cases.** Repeated closes above the same unconsumed swing can repeatedly reset bars-since-break. Decide separately whether the input describes a new crossing or remaining above a level. A repeated event must not masquerade as a fresh break.
4. **SMT helper assumes alignment.** lab/smt.py compares equal array indexes up to the shorter length and does not verify timestamps. Missing bars could compare different times. It measures return spread, which is not the same definition as one market breaking a confirmed swing while a correlated peer fails to do so. Require explicit timestamp alignment and distinguish the two hypotheses.
5. **Partial news coverage needs finer meaning.** EventIndex exposes one healthy-source fraction; its event counts do not express per-topic observation quality. A healthy calendar feed does not establish that geopolitical news was observed. Retain known announcements with their age/provenance while exposing missing/stale coverage for each source/topic. Do not turn an outage into a claim of no news.
6. **Ambiguous external poll histories are accepted.** validate_snapshot rejects simultaneous ambiguous event revisions but does not reject duplicate same-source/same-timestamp poll records. Conflicting success/failure records can make interpretation depend on input order. Reject such archives; test reversed input ordering.
7. **Latest news and signal-time news are different.** Forward model inputs are intentionally joined at the completed signal candle close, matching historical replay. A headline first observed between that close and actual entry is not a model input. Record a second snapshot at the actual decision/entry time and a separate during-position event log. Do not silently change historical features or train on events that arrived after the decision.
8. **The collector is not a breaking-news execution service.** Its loop waits 900 seconds after a refresh. Source publication and ingestion delays add latency. Measure those delays before claiming rapid reaction. A faster collector can run independently of candle-based entry logic.

These findings are based on source inspection. Reproduction, fixes and performance comparisons remain outstanding because execution was unavailable.

## Live news design

Add separately identifiable information streams:

| Stream | Candidate primary or documented source | What to preserve |
| --- | --- | --- |
| Geopolitics and conflict reporting | Reviewed reporting feeds or GDELT article discovery | Original publisher, original link, discovery/receipt times, event topic, affected regions, corrections and unverified status |
| Sanctions and regulatory actions | Treasury OFAC, SEC and relevant local regulators | Proposal vs final action, jurisdiction, effective date, named entities and official source |
| Coin/project announcements | Ethereum Foundation and individual project-maintained channels, such as Avalanche | Asset identity, announcement type, upgrade/outage/security/listing details and changes to announced dates |
| Scheduled macro events | BLS and Federal Reserve | Schedule as known at that time, timezone, revisions/cancellations; no guessed outcome |
| Released macro numbers | Official releases and appropriately versioned numerical data | Initial value, prior value known then, revisions and actual receipt time |
| Market expectations | A separately sourced, licensed consensus archive if available | Forecast value, contributor/source, cutoff before release; missing when unavailable |
| Exchange conditions | Coinbase market/status streams | Spread, depth where collected, quote age, product availability and feed gaps |

The [GDELT DOC API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) describes article discovery, date filtering and publisher filters. It is a candidate discovery service, not proof that an underlying claim is true or a complete historical archive. Live endpoint reliability and coverage still require testing. Deduplicate syndication and story updates so twenty copies do not become twenty independent events.

[OFAC Recent Actions](https://ofac.treasury.gov/recent-actions) supplies official sanctions-related publications. [Ethereum Foundation](https://blog.ethereum.org/) and [Avalanche](https://www.avalanche.com/about/blog) publish project information. Their website availability does not establish a working adapter, stable RSS schema, complete coin coverage, or permission for unrestricted article redistribution. Select and test each actual feed; store permitted metadata and source links.

The [BLS calendar](https://www.bls.gov/schedule/news_release/) specifies Eastern time and changing release schedules. [FRED/ALFRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) distinguish information available today from past vintages. Date-level vintages alone do not establish minute-level release availability, and FRED does not supply a ready-made market-consensus archive.

### Processing and paper-trading contract

1. Collect in a background worker with provider-appropriate polling, timeouts, caching, backoff and visible source health. Publication delay and receipt delay are separately measurable.
2. Archive immutable revisions. Keep source publication time, first system observation, scheduled occurrence/effective time, and any later correction. A retrospective archive must document its original availability evidence.
3. Normalize entity IDs and event types. Separate official statements, reporting, attributed claims and rumors. An official announcement is evidence of that announcement; it is not a guarantee about its economic effect.
4. Start with transparent extraction. If an LLM later helps classify licensed article text, require evidence spans, strict structured output, uncertainty, versioned prompts/models and an abstain option. News text is untrusted data and cannot issue system instructions or orders. Missing detail must stay unknown.
5. Join only information available at the relevant decision time. Keep the original candle-close feature snapshot distinct from actual-entry and after-entry observations.
6. Match news with the market response already observed: coin return relative to BTC/ETH, spread/depth changes, volatility and elapsed time. Do not assume positive wording means buy or that every conflict headline predicts the same move.
7. Evaluate event context first in a separate shadow policy and record its decision alongside the price-only policy. Risk limits and cost checks remain enforced. Learning updates happen only after the relevant outcome has resolved.

A hypothetical conflict announcement at 10:02 received at 10:04 may be considered by a decision after 10:04. It cannot be inserted into a 10:00 signal. A later explanation of the move also cannot be substituted for the original report. A price move before our receipt may mean the opportunity has already passed. This example makes no claim about a particular current conflict announcement.

### Trade journal additions

For each paper decision, preserve:

- Signal close, decision time, quote receipt time, model/version and exact inputs.
- Related event IDs and revisions; why each was linked; source/topic coverage and data age.
- Gross P&L, fees, modeled slippage, net P&L, initial risk and net result in R.
- Largest favorable/adverse movement based on observed executable-side quotes; flag incomplete paths.
- Observed failure pattern: little follow-through, gain given back, fees erased gain, genuine net break-even, stop/time/target exit.
- Events first observed after entry in a separate field.
- Same-opportunity price-only/shadow decisions and later outcomes, including skipped opportunities.

The explanation should say “loss occurred during these observed conditions,” not “this headline caused the loss” unless an appropriate causal analysis supports that claim. A loss is useful feedback, not automatically a mistake. A winning trade is not automatically a sound decision. Gross break-even is generally not net break-even once costs are included.

## Screenshot concept map

The uploaded screenshots identify TJR's Boot Camp and Path to Profitability series. Original video pages located include [news data](https://www.youtube.com/watch?v=w5sUCqFH3Lg), [strategy overview](https://www.youtube.com/watch?v=TEp3a-7GUds), [fair value gaps](https://www.youtube.com/watch?v=xX5LTSJ5wwM), [advanced liquidity](https://www.youtube.com/watch?v=AGmAVyAuBE0) and [SMT divergence](https://www.youtube.com/watch?v=7dTQA0t8SH0). Their full original videos/transcripts were not accessible for verification in this review. The table gives independent operational definitions and code mapping, not a claim to have watched the courses or reproduced the instructor's exact method.

| Concepts visible in screenshots | Testable interpretation for this project | Current state / next requirement |
| --- | --- | --- |
| Candlesticks, trends, chart reading | Closed-bar body/wicks, momentum and confirmed swing sequence | OHLC and trend inputs exist; a candle cannot reveal every intrabar fill |
| Break of structure, daily bias | Close through a previously confirmed level; completed higher-timeframe context | Structure code exists outside simplified training; distinguish fresh breaks from persistent conditions |
| Liquidity and advanced liquidity | Prior/equal highs/lows as price-based proxies; separately measured spread/depth/trade flow | Sweep features exist; they do not prove stop locations, institutional intent or hidden orders |
| FVG and advanced imbalance | Precisely defined three-candle price pattern, size relative to volatility, creation/mitigation/expiry | Present in structure code; repair gap lifetime; no assumption that a gap must fill |
| Inverse FVG | Explicitly defined failure of a prior gap and subsequent retest | Inversion flag exists but has no expiry/invalidation |
| Order blocks | Predeclared candle zone tied to a specified displacement/break, with retest and invalidation | Exact course rule not verified; no order-block input in adaptive vector; candle zones are not observed institutional orders |
| Equilibrium, premium/discount | Position relative to the midpoint of an explicitly chosen confirmed range | Present in structure code; “discount” does not establish fundamental undervaluation |
| SMT divergence | Timestamp-aligned peer swing disagreement, compared separately with simple relative return | Existing helper is return spread and assumes alignment; BTC context is already a separate input |
| Time theory and sessions | Measured time-of-day/week liquidity and volatility, with correct timezone/DST | Research hypothesis; stock/futures session rules do not automatically transfer to 24/7 crypto |
| News, CPI/PPI and future events | Schedule, information surprise, novelty, receipt delay and observed market reaction | Calendar/count layer exists in draft; actual/consensus, semantic types and broad coverage remain missing |
| Risk management, lot size, stop losses | Size from net loss at invalidation including costs, with exposure/drawdown constraints | Cost/risk machinery exists; dollar loss limits remain meaningful regardless of learning value |
| Taking profits, execution and break-even | Compare fixed/conditional exits after costs; model spread/slippage/latency | Existing separate exit experiment; no promotion from one favorable historical result |
| Learning from losses, identifying problems, journaling | Entry forecast vs resolved net outcome, path-based failure labels and prospective review | Existing outcome memory and diagnostics; add event evidence and distinguish unavailable paths |
| Daily/weekly analysis, backtesting | Chronological evaluation across regimes with unseen confirmation periods | Existing research framework; same dates across timeframes are not independent confirmation |
| Patience, no-trade days, fear, discipline and trading plans | Consistent rules; abstention when evidence/economics insufficient; bounded paper exploration | Software needs measurable rules, not an emotional “fear” parameter |
| Overconfidence and taking wins/losses | Forecast calibration, uncertainty and review of wins as well as losses | Do not infer confidence or skill from a few outcomes |
| Goal setting, individuality, hard work, motivation and check-ins | Explicit objectives, review cadence and reproducible experiments | Process guidance rather than independent predictive market signals |
| Funded accounts | Account-specific costs, instruments, restrictions and loss rules | Different operating setup; do not transplant a funded-futures strategy into a Coinbase cash model without revalidation |

[Coinbase's WebSocket documentation](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels) describes ticker, heartbeat and order-book feeds. The current lab/coinbase_feed.py subscription uses ticker and heartbeat; that is not a recorded full-depth order-book history. lab/microstructure.py can import several microstructure fields, but accepting a column does not prove those observations were collected, valid, or used by the adaptive model. Missing fields must not become false zero-valued measurements.

## What may be preventing a reliable trader

These are prioritized hypotheses, not conclusions from the unread new report:

1. Expected returns after real costs may be too small. Audit gross edge, spread, fees, slippage and achievable fills before increasing trade frequency.
2. Forecasts may be poorly calibrated for the actual cost-eligible trades. Compare pre-entry estimates with later net outcomes by regime and strategy.
3. Many simulated examples can be variants of the same market move. Count effective independent episodes, not only candle rows or overlapping trades.
4. Existing concepts may not reach the actual learned policy, or their definitions may be stale/inconsistent between replay and live use.
5. News and market context may arrive too late, be revised, or lack the expectations against which a release should be judged.
6. Repeatedly improving against reviewed history can fit noise. More coins/timeframes do not reset the information already used during development.
7. A spot/long-only candidate set cannot be assumed to profit in every market regime. Consider additional hypotheses separately rather than forcing activity or introducing leverage to meet a daily target.

The primary research paper [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explains why selecting among many backtests can create false discoveries. Keep an experiment ledger and reserve fresh chronological confirmation; report unsuccessful variants too.

## Implementation order and acceptance checks

1. Reconnect workspace; hash and audit learning-results 9(1).json and AVAX-USD_5m_learning-data.zip. Establish version, completed studies, gap coverage, actual eligible examples, independent trades, net costs and forecast errors. Do not combine separately funded simulations into a purported live-account return.
2. Reproduce and repair the deterministic structure/poll-history issues. Test gap invalidation beyond 25 gaps, IFVG retirement, repeated crossings, mismatched peer timestamps and conflicting polls.
3. Add reviewed geopolitical and official project adapters with source-specific health and immutable revisions. Test duplicates, syndication, malformed times, corrections, outages, entity ambiguity and restart persistence.
4. Add actual-decision and during-position news records without leaking either into earlier model inputs.
5. Register one small structure/event experiment at a time. Preserve the existing price-only baseline, costs, boundaries and risk rules.
6. Compare out-of-sample net expectancy, calibration, drawdown, cost sensitivity and adequate sample coverage. Use time-block uncertainty estimates where outcomes overlap. News benefit must survive identical-period controls; a profitable event anecdote is insufficient.
7. Run Python/UI/startup tests and exact-bundle reproduction, then publish measured results. Promotion/deployment remains a separate step.

The initial review made no executable changes. The V11.13 status above records the subsequent tested implementation; neither stage claims a deployment, new-report conclusions or improved profitability.
