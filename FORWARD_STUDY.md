# V11.14: future-price studies and reconciled finances

## Why this revision

The trading discussions raise useful questions: were the rules fixed before the results, do losses include all costs, and does continued learning actually beat leaving the original model alone? Repeatedly improving the same historical score cannot answer those questions. The existing XRP diagnostic even has a frozen model doing better over a very small sample. Choosing it now from that result would introduce another selection decision.

This revision makes that comparison prospective and fixes two concrete accounting mistakes. It leaves the numerical learning rule, candidates, fees, risk limits and qualification requirements intact. Existing net-return learning still receives normally completed wins, losses and break-even outcomes, without rewarding a loss for being large.

The design follows the chronological evaluation principle in [Hyndman and Athanasopoulos, time series cross-validation](https://otexts.com/fpp3/tscv.html): the observations available for fitting precede those used to evaluate forecasts. [Bailey and colleagues, The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explains why choosing strategies after many historical trials can produce misleading performance. These sources motivate the evaluation procedure; neither establishes that this strategy has an edge.

## The registered comparison

Choose a saved 15-minute or hourly historical model on the main screen and begin a 30-day study. Registration saves:

- The exact model, its historical report fingerprint and source-code hash.
- A start at the next candle boundary strictly after registration, and an end exactly 30 days later.
- Equal $500 starting balances, fees, modeled slippage, a fixed 0.05% half-spread assumption, risk per trade, notional cap and daily loss limit.
- One declared question: does learning from selected, completed trades improve subsequent net results against the identical frozen seed?
- The updating, frozen and cash comparisons. Holding cash has zero modeled net return.

The updating account learns only its own normally closed trades. The frozen account starts from the same seed and never updates. They can subsequently choose different trades, so the comparison concerns complete account paths. It is not a comparison of differently scored copies of the same selected trades. These research accounts stay separate from the existing paper account and Coinbase balances. A compatible unqualified seed can participate in this diagnostic, while trading qualification remains unchanged.

The saved report's costs must match the settings at registration. Later changes to settings or historical practice cannot alter the study's pinned seed or costs. The engine is V11.14, reports are version 20 and the numerical policy format remains v17. Prior engine qualifications need fresh practice.

## Observations and execution

A background worker downloads completed Coinbase candles and evaluates them using the existing chronological simulator. It requests 500 initial intraday candles and 90 days of daily context; available Bitcoin context and locally observed events follow the seed's existing requirements. Indicator warmup restarts after data gaps. Previously saved candles and signal features stay frozen, including when daily context or news arrives later. Provider revisions or late insertions that would change an evaluated prefix are rejected.

Entries occur at the next candle open under the simulator's costs. Stops take priority when intrabar ordering is unknown. The observations are collected after registration, but fills are modeled from completed candles. A recovered outage may be evaluated afterward using those candles. This establishes a registered future-price candle simulation, not evidence of executable live quotes, queue position or actual spread behavior.

The table separates normally closed trades and their realized net result from the net valuation of open positions. `END` records value an open position after estimated exit costs; they are excluded from completed counts and learning labels. A gap while either account holds a position makes its result incomplete and unknown. Missing requested candles are counted, including missing candles at the end of a fetch. A missing final candle cannot create a completed study. Missing inputs and source failures stay visible.

Every simulated fill pair has an independent arithmetic check. The study saves forecast diagnostics, regime results, full trades, model hashes and input hashes. Downloading a record preserves its exact seed, inputs, observations and results. Source or protocol mismatches prevent silently continuing with different rules.

## Starting, stopping and interpreting it

1. Confirm the fee setting and complete 15m or 1h historical practice. For event-enabled inputs, start event collection and inspect its source freshness as well.
2. Select one saved model in **Does continued learning help?**, then **Begin 30-day study**. Only one study can be active at a time.
3. Inspect errors, last candle time, missing counts, both accounts' net results and drawdowns. Account results remain research only.
4. Use **Download this study** to retain the protocol, full inputs and trade records. **End study early** retains a stopped record rather than discarding the attempt.

An active collector resumes after server restart with identical code. Code changes end that attempt with a `code_changed` status. Missing-position paths or reconciliation failures become `incomplete`. All attempts remain in the database; the dashboard shows the latest 20 and the total registered count. This includes unsuccessful and early-stopped studies. Keep the configured persistent database and data storage on the host as described in [website setup](WEBSITE_SETUP.md).

Thirty days is a fixed initial collection window, not a statistically sufficient proof period. Few trades, overlapping conditions and one market can leave the comparison inconclusive. Results never promote a model automatically. Any later rule change needs a separately registered evaluation and must retain the earlier attempts. Viewing interim results does not turn them into a valid basis for selecting a winner.

To reproduce an exported study, check out the exact recorded implementation and run:

```sh
python scripts/replay_forward_study.py /path/to/forward-study.json
```

The command checks source, protocol, seed and input hashes, reruns both accounts and requires equality with the saved result. This is reproducibility under the same simulator, rather than independent validation of its fill assumptions.

## Financial and review repairs

Paper-account counters previously classified a zero result as a loss. Exact zero now has its own count, including after restart. A small negative result still counts as a loss in the finances, even if its diagnostic review calls it near break-even. Win rate uses all completed trades.

Trades closed in the same timestamp could also appear in the wrong order on the balance curve. Each new closure now saves the actual account commit sequence. The dashboard reconciles the complete closed journal with the saved balance and independently recomputes net P&L and R from fill prices, size, risk and frozen entry fees. Spread and slippage are already included in fill prices; fees are deducted once. Older rows without frozen cost evidence have partial coverage, rather than an assumed zero fee. An audit reports discrepancies without rewriting money.

Loss and near-break-even reviews now include concrete questions tied to observed findings: whether costs consumed the move, gains were surrendered, the entry lacked follow-through, a gap exceeded planned risk, or a countertrend entry had supporting evidence. These are hypotheses for later comparisons. A review cannot establish why the market moved, infer an unobserved tick path, or select an optimal exit from hindsight. The questions are descriptive and do not add rewards or extra training observations.

## Optional Massive historical data

Massive is an additional market-data provider. The optional downloader uses its [documented crypto aggregate endpoint](https://massive.com/docs/rest/crypto/aggregates/custom-bars) and [Bearer-header authentication](https://massive.com/docs/rest/quickstart). It supports USD crypto symbols at 15m, 1h and 1d, subject to market availability and the account's entitlement.

The request limits follow the published [currencies Basic plan](https://massive.com/currencies): five requests per minute, historical end-of-day access and two years of history. Plan details may change. This adapter conservatively waits at least 12.2 seconds between requests, limits requests to 730 recent days, and excludes today's unfinished UTC session. It does not subscribe to a plan or validate billing access in advance.

Configure `MASSIVE_API_KEY` privately in the environment, then, for example:

```sh
python scripts/download_massive_history.py --symbol BTC-USD --interval 1h \
  --start 2025-09-01 --end 2026-09-01 --out massive-research/BTC-USD_1h.zip
```

Dates are UTC, with an inclusive start and exclusive end. Choose dates within the allowed window when running the command. Repeat with another supported USD symbol for a separate dataset. Existing output files cannot be overwritten.

Each ZIP contains `candles.csv` and a manifest recording the provider, dates, coverage, missing intervals, request IDs and price-data hash. Quote volume is volume times VWAP, or an explicitly documented estimate using close when VWAP is absent. Missing candles remain missing. Wrong markets, malformed records, unexpected pagination and redirects are rejected. The key stays in the authentication header and is excluded from exports.

Massive's aggregated candles stay separate from Coinbase execution history. The downloader creates a research bundle; importing this venue into training requires a later controlled integration and comparison. Mixing it into missing Coinbase intervals would change the underlying venue evidence. No Massive credentials were available for a live integration check in this revision.

## Measured result and remaining work

The supplied 105,062-candle XRP replay preserves the previous historical account metrics exactly: six primary trades, gross P&L −$8.187137, fees $4.562520 and net −$12.749657. The higher-cost primary selects zero trades. The frozen diagnostic has three trades and +$8.329271, remains unqualified and is not promoted. This reused sample verifies unchanged accounting and strategy behavior; it does not evaluate a new 30-day study. See [the exact replay](research_baselines/forward-revision-replay.json) and [verification](VERIFICATION.md).

The earlier 14-source news collector and signal/entry/after-entry journal remain included. Article interpretation, actual-versus-consensus economic surprises, complete historical event coverage and a dedicated live news-versus-price-only account comparison remain open research work. This study isolates continued updating against a frozen seed; it cannot isolate a news contribution. Unscheduled wars or regulatory announcements cannot be assumed predictable. The software can record when information became available and test what decisions followed.
