# Controlled research in CryptO V11.18

Open **Experiments** in the existing Crypto + Stocks navigation. The page keeps
the hypothesis, costs, source, outcomes and failures together. It never installs
a winning backtest into the trading account.

## What changed

The unfinished seven-timeframe work is integrated: **1m, 4m, 5m, 15m, 30m, 1h,
4h**. Six-hour reports remain readable as legacy research. Closed 4m, 30m and 4h
Coinbase bars are built only from complete smaller Coinbase buckets. The archive
coverage table includes all 15 coins and explicitly identifies missing candles,
zero-volume observations and its September 20, 2026 cutoff. Binance/USDT archives
remain separate from Coinbase/USD; the large archives are not placed in the
Render application filesystem.

Three fixed recipe families are available. Choose one market, interval and
history window, then queue one to three comparisons:

| Question | Control | Challenger |
| --- | --- | --- |
| Does a retest improve a breakout entry? | Existing 55-bar volume breakout | First later confirmed retest of the original broken level |
| Does a different exit help? | Fixed stop/target and 12h deadline | Fee-covered break-even, a trailing stop, or a 6h deadline |
| Does continued learning help? | Frozen development seed | Same seed, updated only by that account's normally closed trades |

The fixed breakout uses the existing candidate with 2 ATR initial stop, 2.5R
target, volume-z minimum zero, 12h deadline and 15-minute cooldown. Its existing
regime, volatility, RSI, cost, net reward and loss-streak checks remain active.
The retest arms only after a qualifying breakout and expires after 12 bars. A
later candle must touch within 0.25 of the breakout-time ATR of the frozen level,
close above the level and close at or above its open. A low more than 0.5 ATR
below the level invalidates it. No same-candle breakout/retest is assumed. Gaps
clear pending retests and restart indicator warmup.

The trailing rule activates after a completed candle earns at least 1 net R and
places the next candle's stop one initial stop distance behind the close. Stops
never loosen. The original target remains. A 6h deadline resolves at the first
available candle close at or after six hours; on 4h data that can be eight hours.
Earlier exits can change subsequent entries and cooldowns, so comparisons rerun
whole independent accounts rather than editing old trade profits.

## Evidence and costs

Every variant/window/cost scenario has its own $500 account. The app snapshots
the configured fee, slippage, risk, position fraction and daily loss limit when
the job is queued. The assumed half spread is 0.05% per side. A second account
multiplies fees, slippage and half spread by 1.5. Different costs can reject
different entries; a higher-cost account can therefore have a higher return with
far fewer trades. That is not a fee benefit or a matched-trade result.

The first 70% of observations precede later evaluation. A 24-hour purge separates
development labels/accounts from the later window. Indicators may use preceding
completed prices. The learning seed uses the existing 22 candidates, cost-eligible
development labels and the chronological entry/closure trainer. It is copied for
both accounts and both cost scenarios. Continued learning receives only its own
closed account outcomes; no hidden shadow-trade updates or future labels occur.
News, independent daily or Bitcoin context are not added to these three simple
recipes. This comparison does not claim to reproduce the full production learner.

The interface reports net P&L, higher-cost P&L, normally closed trades, end marks,
drawdown, profit factor, model updates and entry rejection reasons. JSON exports
include the trade ledger and historical bootstrap ranges. End-window liquidation
contributes to account P&L but cannot count as normally closed evidence or teach
the model. An open position interrupted by absent candles makes that account's
return unavailable.

**These are development replays, including when chronological.** Previously seen
history does not become unseen by changing an interval, parameter or recipe.
At least 30 normally closed trades in every compared account are required even
for a preliminary historical lead. Lower losses are labelled as lower losses;
no-trade results are insufficient evidence. No outcome qualifies a model.
Overlapping timeframes and repeatedly reused data are not independent evidence.

The existing registered 30-day study remains the route for prospective learning
comparisons on saved 15m/1h models. It is a new-price candle simulation, not actual
quote fills. Source changes invalidate its registered attempt. Retest and trailing
recipes have no automatic prospective-trading connection.

## Planner and saved work

Built-in suggestions use aggregate counts from the latest 100 paper journal
records. No closed journal means explicitly labelled starting hypotheses.
An optional OpenAI planner can order the approved recipe IDs and explain why
they merit testing. It cannot change parameters, invent measured returns, write
code, queue jobs automatically or send orders.

For that optional feature, configure these **server** environment variables:

- `OPENAI_API_KEY`: your API project key; never place it in the browser or GitHub.
- `OPENAI_EXPERIMENT_MODEL`: an available Responses API model supporting strict
  structured output. No model or paid API account is silently provisioned.
- `APP_ACCESS_TOKEN`: at least 16 characters, required for paid planning.

Clicking **Ask AI for a research plan** makes one paid request using aggregate
journal counts and at most 20 experiment summaries. It does not send Coinbase
balances, account IDs, credentials or full trade journals. It uses `store:false`,
a fixed output schema and 1,600 output-token limit, and validates the result again
locally. Failed or ambiguous requests count toward the one-per-minute and
12-per-UTC-day limits; there is no automatic paid retry. Built-in planning works
without this integration. API wiring was tested with controlled responses; an
actual paid model call was not used in release validation. The implementation
follows [OpenAI's structured output documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

The queue saves its fixed cutoff, costs, code hash, data hash, attempts and errors
in SQLite. Recorded inputs and completed account/seed checkpoints are compressed
in the configured research directory. Identical requests at the same cutoff reuse
the same job. One process owns the queue lease. At most 12 jobs can be pending,
100 records are retained, and a job uses no more than 50,000 candles. New jobs
stop when less than 150 MB of filesystem space remains. These resource limits do
not truncate the separately downloadable full candle archives.

Cancelled/failed jobs can resume from the same snapshot and completed checkpoints.
A changed source hash stops automatic continuation. With unchanged code, queued
work resumes when the application starts. During another large historical task,
the queue waits. Heavy new research controls wait for an active experiment to end.
Completed reports are also saved in the database and included in its backup.

Restart recovery needs the saved database and research directory. On Render,
`render.yaml` already specifies `/var/data/research.sqlite3` and
`/var/data/research-data` on a persistent disk. An installation made outside that
blueprint must have equivalent persistence configured. A process can resume saved
work; an ephemeral filesystem erased during deployment cannot recover it.

## Paper risk controls

The paper runner refuses new entries if any open position lacks a fresh quote.
Its new related-market risk limit defaults to **1.5% of marked equity**, alongside
the existing 3% total stop-risk and exposure limits. It uses matched hourly log
returns from the preceding 168 hours, at least 72 matched observations, and
direction-adjusted correlation of at least 0.75. Insufficient or stale history is
counted as related until adequate evidence exists. The sizing decision is stored
with each paper entry. Stops and correlations do not guarantee a maximum loss.
This is a paper-account control; Coinbase's existing flat-account and attached
bracket restrictions remain in place. No funded runner is activated by this update.

Engine identity advances to V11.18, so old passing profiles require current
validation before new entries. Saved reports and model evidence are retained.

## Reproduce and verify

Use the original delivered candle ZIPs. The runner verifies the recorded member
or dataset hash before selecting a fixed final calendar window. For example:

```sh
python scripts/run_controlled_experiments.py --archive /path/BTC-candle-history.zip --interval 15m --days 180 --out /tmp/btc-15m.json
python scripts/run_controlled_experiments.py --archive /path/BTC-candle-history.zip --interval 1m --days 14 --include-vwap --out /tmp/btc-1m.json
python -m unittest discover -s tests -q
node tests/check_learning_ui.js
node tests/check_finances_ui.js
node tests/check_experiments_browser.js
node tests/check_stocks_browser.js
```

Install `requirements.txt` first; browser checks additionally need Playwright and
Chromium. The local browser server uses an isolated temporary database and
artificial fixtures. It never queries a market feed, an AI model or a broker.
The actual historical release comparisons and declared windows are recorded in
`research/experiments-v11.18.json` and `research/experiments-v11.18-results.md`.
