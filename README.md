# CryptO V11.12 — news and scheduled-event context

A trading program that studies market history, learns which setups work in different conditions, tests its decisions on later prices, and updates from completed trades.

**Goal: work toward $10–$15 a day from a $500 account. That return has not been demonstrated.** V11.12 adds a persistent news/calendar collector, the main-screen Market events panel, seven timestamped event features, trade-context reviews and an independently trained price-only comparison. Historical coverage begins when information is actually observed; today's news is never backdated into earlier tests. Read [the event design, limits and verification](MARKET_EVENTS.md). Policy v16 and report 18 require fresh practice. No event-related trading benefit has yet been demonstrated.

V11.11 separates relevant cost-eligible evidence from expensive rejected practice, permits only downward corrections of optimistic eligible forecasts, and studies specific failure patterns. It adds completed Bitcoin daily context, entry-regime results and persistent experiment records. These changes do not establish better returns: the paired XRP replay lost more than the previous model. See [the design, research and measured results](ELIGIBLE_CONTEXT_RESEARCH.md). Its prior models are superseded by V11.12.

V11.10's continuous handoff remains included: open practice trades, waiting periods and original entry forecasts continue across the review date. The saved learner comes from the continuous primary replay, and higher-cost confirmation keeps its own costed history. See [that earlier study](CONFIRMATION_CONTINUITY_RESEARCH.md).

V11.11 historical learning avoids repeated imports, unused background-practice bookkeeping and discarded model copies. Paired local runs finished in **27–29% less time** with identical complete reports except for creation timestamps. The full XRP workflow fell from 123.5 to 87.4 seconds; the primary LTC 5m workflow fell from 40.7 to 29.6 seconds. Downloads and hosted load were not part of these timings. See [the measured speed study](LEARNING_SPEED.md).

The separate cost-eligible and cost-blocked practice tracks introduced in V11.9 remain included. Both learn actual net returns, including losses and break-even outcomes, only after closure. The forecast panel separates their results. See [that earlier coverage study](PRACTICE_TRACKS_RESEARCH.md).

V11.7 entry-error margins and the separate conditional-selection experiment remain included. That experiment cannot control trading. [Its earlier paired replays](ENTRY_LEARNING_RESEARCH.md) showed no final-period profit improvement.

The V11.5 readiness repair, main-screen finances and separate break-even exit experiment are included. Each practice run trains the independent exit model and tests its complete account path; it cannot control trading. The earlier V11.5 comparison showed no final profit improvement on the supplied DOT and AVAX candles. See [that pinned experiment and reproduction commands](EXIT_LEARNING_RESEARCH.md).

The predeployment review also corrects time-based exits that ran one candle late, checks each monitored timeframe's own review date, reduces replay memory, and loads detailed dashboard reviews on demand. Those fixes remain included. See [the findings and measured limits](PREDEPLOY_REVIEW.md).

## Start here

1. Open the app locally or follow [WEBSITE_SETUP.md](WEBSITE_SETUP.md) to put it on Render.
2. Enter your actual Coinbase fee per side. The initial 0.4% is an assumption until confirmed.
3. Click **Start event collection** and check source freshness. Then edit **Coins to practice on** (or choose **Use suggested 30 coins**), choose the timeframes and history length, then click **Practice on real market history**.
4. Review the historical results, then use **Start learning & paper trading** for ongoing practice on new prices.

Historical practice now suggests 30 Coinbase USD markets spanning established coins, smart-contract networks, DeFi, scaling networks and more volatile tokens. Up to 60 tickers can be entered. Short names such as HBAR and full names such as HBAR-USD are accepted; the submitted list is saved. Suggested names are requests, not a guarantee of current availability. The app checks Coinbase product metadata at run time and reports unavailable listings individually. If metadata cannot be fetched, that failed check is recorded and the candle endpoint must still supply real prices.

The dashboard defaults to separate **15-minute, hourly and 6-hour** studies, with **five years** requested. Optional 5-minute studies are supported. Requests are bounded to one year at 5m, five years at 15m and eight years at 1h/6h. Every report shows requested/effective history, actual candle dates and the percentage of the effective window covered. A younger listing cannot supply history before it existed. At least 3,000 observed candles remain required; a 6-hour study therefore needs at least 750 observed days. The daily context uses only completed daily candles available at each historical signal. See [the data design, sources and replay results](MARKET_COVERAGE_RESEARCH.md).

Each coin/timeframe has its own model, simulated account, result, cache identity and resumable checkpoint. Practice finishes without starting monitoring or order runners. Existing runners keep their current state. Only the configured **Decision interval** in Settings may install a qualified forward profile. Secondary timeframe studies cannot overwrite or delete it. Six-hour models remain research only and cannot install a forward profile; coarser candles need a separate execution-precision review before enabling that trading interval. Changing timeframes requires that timeframe's qualification; the app does not choose a winner from the highest backtest profit. Previously reviewed prices remain reviewed across timeframe and history-length changes.

The background automatic learner studies up to ten of the scanner's liquid Coinbase USD markets at the configured decision interval, using the last selected lookback (five years by default), subject to the interval limits. Those reviews retain completed studies from other coins and timeframes. Qualified models can open paper trades and learn after closure. Unqualified markets stay out of the account.

Larger plans can take hours. Coins and timeframes are processed sequentially; unavailable or insufficient data is reported while the rest continue. Completed download chunks, candidate labels and results are saved. A restart within 24 hours reuses the current study's cutoff and completed candidates; an interrupted candidate restarts. Shorter requests retain older cached candles so another report can still export its exact inputs. The dashboard counts the union of observed market hours per coin, avoiding duplicate hours across overlapping timeframes. Training examples and individual account studies may still overlap and are not independent samples or a combined portfolio.

Each decision uses only information available at the past signal close, and learning waits for the outcome. Gaps are never replaced with generated prices. Indicators restart with 240 observed candles of warmup after each gap; daily-context strategies require 21 consecutive complete UTC days. A training position interrupted by missing prices has no known outcome and cannot teach the model; an account test interrupted while holding a position is incomplete and cannot qualify.

Pause entries keeps existing paper positions monitored. Stop stops automatic learning and the paper runner. Closing a browser leaves a running server alone; a computer or server restart stops the runners. Reopen the app and resume them after checking its status.

## Trade finances on the main screen

The **Trade finances** panel above the learning controls shows completed trades,
money won, money lost, net profit/loss, wins, losses, exact break-even results and
win rate. Amounts use each trade's result after costs. Choose **Historical tests**,
**Paper account**, or **Coinbase bot**; their totals stay separate. Historical tests
can show one market or the sum of separate market simulations, with partial or
unavailable reports clearly marked. Training examples and alternative test runs
do not count as account trades. Test-window exits are identified separately.

Paper and Coinbase totals use the entire saved closed-trade journal, including
trades older than the visible table. Open or unfilled orders are excluded. Existing
saved historical reports can populate the panel without retraining. Failed refreshes
keep the last known numbers with a visible stale notice. Coinbase totals require
the existing access-token protection. This display does not start any runner.

## What learns

The model learns relationships between entry-time indicators and the trade's eventual result after costs. Successful and failed trades both update its estimates. It chooses among 22 stop/target variants within seven defined trade types: trend pullback, volume breakout, range reclaim, combined confirmations, daily trend/momentum, volatility expansion, and support with RSI recovery. The three new families use completed daily context and multi-day holding limits with the existing account-risk caps. See [the strategy research review](STRATEGY_RESEARCH.md) for sources, exact rules and limitations. Each variant combines an overall estimate with evidence for rising, falling, or sideways conditions when enough examples exist. The templates remain long-only, so bearish conditions can mean no eligible trades or training examples.

Historical training explores signal-matched setups even when their modeled costs or reward would block a trading entry. These independent hypothetical examples still pay all modeled fees, slippage and spread, so costly losses can be learned. They are not account returns. Policy tests and paper/live trading keep the cost and net-reward checks, evidence requirements, and account-risk limits. Historical policy tests also apply the configured daily loss halt. Reports compare the updating policy with pooled learning, frozen learning, holding cash, and buying and holding the market. These comparisons can show deterioration; they do not select a winner after seeing the final test.

An affordable setup now needs its own completed cost-eligible evidence. Rejected expensive examples remain in overall memory and reports but cannot supply missing eligible samples, forecast weights or error margins. The dashboard shows those counts separately, including errors for positive affordable forecasts. Six additional models predict follow-through failure, giveback, fee-erased gains, near break-even, targets and time exits. Their saved entry estimates are scored only after closure against a historical-frequency baseline; they are diagnostics, not entry or exit controls.

Historical practice and ongoing monitoring download completed BTC-USD daily candles for broader-market trend, momentum, volatility and relative strength. A model trained with that context pauses new entries when it is missing or stale. Existing position management continues. Older bundles without Bitcoin candles retain explicitly unavailable context; their replays cannot measure this feature's benefit. Each run records its data, costs, reviewed boundary and declared comparisons. Reusing a reviewed report never supplies fresh qualification.

This is a small online machine-learning model. It learns entry preferences and strategy selection within those trade types; it does not autonomously invent arbitrary executable strategies or train a language model.

The scanner watches up to 30 active Coinbase USD markets under the default settings. Automatic historical learning studies the first ten in that volume-ranked list. It does not study every Coinbase asset at once. V11.12 includes selected news and official calendar context, with explicit coverage; it does not parse full articles, infer sentiment, or include on-chain data. See MARKET_EVENTS.md.

## Learning from failed trades and fuller candle context

V11.5 adds **Whole-account break-even experiment** inside the loss-study panel. Its separate model learns from its own actual simulated exits, including near-break-even rewards, and reruns later entries, cooldowns and learning after different exits. Both models pay full costs and use the same risk limits. The experiment is reported at ordinary and higher costs, with separate earlier periods and selected-trade-feedback controls; it cannot select or qualify a different trading model. Completed training checkpoints are kept separately for the two models, so practice performs more work but can resume either study. Old models require fresh practice. Reports 16, 17 and 19 are reviewed history and cannot provide fresh confirmation for a new revision.

Adaptive paper monitoring and Coinbase signal export now require 241 continuous completed decision-timeframe candles, matching historical warmup. Each strategy retains its daily-data and other entry checks. The legacy non-adaptive workflow still requires all four timeframes. Newly completed signal timing, quote freshness, account controls and separate Coinbase activation remain in effect.

V11.4 gives losses and near-break-even outcomes extra review attention. Under each market's learning results, open **Loss and break-even study** for outcome counts and priority examples. Near break-even is within 0.10R of zero after costs; these outcomes retain their actual positive or negative reward. Reviews show entry conditions, fee drag, net favorable/adverse marks and giveback. Fixed 1-, 4- and 24-hour after-exit windows remain pending or unknown when sufficient candles are unavailable. A report-only exit experiment tests a fee-covered break-even stop after a prior candle closes at +1 net R. It does not automatically change exits or relabel results.

Independent simulated training no longer takes the longer pause after a losing streak. It keeps routine entry spacing, recorded prices and full modeled costs. Actual account pauses and risk limits remain in effect. All reviewed outcomes count once; displayed deep-review examples are a bounded sample. Paper and settled Coinbase journals retain the available close-time review, with unknown price paths left explicit. Model and report versions changed: run **Practice on historical data** again after deploying. Reviewed reports 16 and 17 cannot supply fresh confirmation for this revision.

V11.3 learns recent net outcomes in comparable cost, intraday and daily-trend conditions. Its diagnostics distinguish stop losses, time-exit losses and gross gains erased by fees. A context with enough recent losing evidence blocks entries; later completed successes can restore it. The report compares the memory adjustment with the same learner without that adjustment. See [OUTCOME_MEMORY_RESEARCH.md](OUTCOME_MEMORY_RESEARCH.md) for the declared rules, research sources and measured limits. The earlier cost-model work is documented in [LEARNING_IMPROVEMENTS.md](LEARNING_IMPROVEMENTS.md).

Practice now retries remaining internal gaps, first directly and then using complete smaller Coinbase candles. It also downloads separate daily candles so an intraday gap need not erase daily context. If daily retrieval fails, the report names the fallback to complete intraday days. Intraday indicators still restart at gaps, and missing daily candles still reset daily warmup. An explicit Practice action rechecks both sources before the automatic deadline; identical observations reuse completed training. New external data could not be downloaded in the development environment, so actual recovery of the supplied gaps is still unverified.

Each market offers **Download candles & report** for reproducible analysis of its actual saved data. Separate daily inputs, when used, are included as `daily-candles.csv` with their own checked hash. Bitcoin inputs are exported as `bitcoin-daily-candles.csv` with a separate checked hash. Add `--daily-csv daily-candles.csv --bitcoin-csv bitcoin-daily-candles.csv` to an offline `--csv --learning` command when the bundle contains both files. Missing or changed cached inputs prevent an export from claiming an exact match.

## Paper and real trading

The main button starts **paper trading**. Real Coinbase orders still require account configuration and separate explicit activation. Follow [COINBASE_SETUP.md](COINBASE_SETUP.md). The existing Coinbase pilot remains limited to BTC-USD, ETH-USD, and SOL-USD, $500 maximum capital, $150 maximum entry spend, and one position at a time.

Paper and Coinbase models begin from the qualifying historical model, then learn from separate journals. Simulated paper wins do not train the real Coinbase model. Real feedback is added only when the position is fully closed and its quantities, values, and fees have settled.

## Run locally

Use Python 3.10 or newer; offline verification used Python 3.12.

- Windows: extract the ZIP into a new folder and run run_windows.bat.
- Mac/Linux: open a terminal in the extracted folder and run chmod +x run_mac_linux.sh, then ./run_mac_linux.sh.

The launcher installs dependencies and opens the app in your browser. Keep the computer awake and its Python process running. For the website route, upload all extracted files and folders to GitHub and use the included Render configuration.

## Upgrading an existing installation

Use the V11 source files, preserve your database and persistent storage, and stop an older process before starting another. The new engine requires fresh qualification. Do not replace a live order journal with a blank one while a Coinbase position remains.

Your database is research.sqlite3 by default. Set RESEARCH_DB_PATH and RESEARCH_DATA_DIR for persistent hosted storage; the included Render template already does this. Keep Coinbase keys outside the source folder and GitHub.

Qualified markets are reviewed every 28 days while the controller runs. Rejected markets retry after a day and failed downloads after an hour. Changes to tested fee, sizing, interval, or daily-loss settings require a new review. Models expire after 30 days without fresh qualification. Retried reviews may overlap old test periods; they are not independent proof of improvement. A new historical model replaces the forward model on its next use, while the old trade journal and reports remain saved. This history/exploration update requires fresh practice with the new policy and report versions. Existing downloaded candles are reused when available; older reports are labeled **Updated learner · practice again** until replaced.

To download real history and run accelerated practice without starting the server:

```sh
python run_research.py --coinbase --learning --symbol BTC-USD --interval 1h --days 1095 --fee 0.004 --out learning-result.json
```

Add `--end 2025-01-01` to replay a past period ending before that UTC date. Use a different symbol or interval for a separate experiment. The command records the source and date boundaries; it does not install models or start trading. Completed download chunks are reused from `data/automatic`, or the folder specified by `--cache-dir`. [Coinbase's historical candle API](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) supplies the recorded prices; trades, fees and fills are modeled by this program.

To evaluate an existing historical CSV:

```sh
python run_research.py --learning --csv BTC-USD_1h.csv --symbol BTC-USD --interval 1h --fee 0.004 --out learning-result.json
```

The CSV needs chronological, completed candles with `ts` in UTC milliseconds and `open,high,low,close,volume` columns. Optional `quote_volume,trades` columns are supported. Supply the actual fee fraction per side. CSV source authenticity is not independently verified and is labeled accordingly.

[What the learner does and how it is tested](V11_LEARNING.md) · [Verification and limits](VERIFICATION.md) · [Change history](CHANGELOG.md)
