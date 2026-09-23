# Stock Lab V12.1

A stock-only research, learning and paper-trading workspace for US-listed stocks
and ETFs. The existing Learning-algorithm repository and Render service remain
the deployment targets.

## Use the app

- **Dashboard:** market session, stock charts, data connections, recent learning,
  strategy jobs and a selected forward paper account.
- **Markets & research:** the existing 20-company research watchlist, catalysts,
  source references, provider market boards, price changes and charts.
- **Stock learner:** train on earlier stock candles; compare six strategies on
  later prices with normal and higher costs. Day or swing holding, fractional or
  whole shares, and configurable stock costs and risk limits.
- **Backtest stocks** (`/backtests`): five named strategies, ticker and candle
  selection, day/swing holding, paper balance, share sizing, optional end date,
  costs and risk controls. Compare development, later and higher-cost results;
  inspect P/L, drawdown, win rate, coverage and a downloadable trade journal.
  Opening-range breakout supports day mode and optional point-in-time news.
- **Paper account:** register a completed learner for new sessions, inspect its
  independently simulated equity, positions and learning updates, stop it, and
  export its journal.

Historical candles support **1m, 4m, 5m, 15m, 30m, 1h, 4h and 1d**. Sessions use
New York exchange holidays, daylight saving and early closes. Missing source
candles are reported and never replaced with invented prices.

The public Yahoo history provider works without keys. Alpaca and Massive are
optional server-configured data providers. Historical requests and forward paper
practice use a minimum 20-minute delay. Market widgets are separate provider
displays; their availability and delay are shown by the provider.

## Run locally

Use Python 3.12:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows use `.venv\Scripts\activate` or `run_windows.bat`.
Open http://127.0.0.1:5000. Configure `APP_ACCESS_TOKEN` on a hosted installation.
[Website setup](WEBSITE_SETUP.md) describes the existing Render deployment and
persistent stock state. [Start here](START_HERE.md) explains the first stock run.

## Migration from the crypto app

`app.py` now constructs `StockService`. It does not construct crypto learners,
Coinbase adapters or traders, crypto event collectors, or crypto experiment
workers. Saved crypto settings cannot start those processes. Old crypto API
requests return HTTP 410 after authentication; crypto dashboard scripts are not
served. Old Experiments links redirect to the stock Strategy Lab.

Existing stock jobs, candles and journals keep their original directories.
The old crypto database and downloads are left untouched. Shared research
utilities and historical crypto modules remain in source for reproducibility,
but have no active web routes. Archived V11 setup notes are in `docs/legacy/`.
The Coinbase SDK is no longer a default web dependency.

A changed research source hash invalidates older learner registrations. Their
records stay available, but start a new stock run before registering a new
forward account. Interrupted named-strategy jobs are marked as errors and need
a new run; partial calculations are not called complete.

## Execution and evidence

This release supports **long-only, unleveraged stock paper trading**. It has no
funded stock-broker order connection. Charts are not used as an execution feed.
Stock learner comparisons start with independent $500 accounts. Named stock
backtests let you set a paper balance from $100 to $1,000,000. Historical
profits are never added to a forward account or combined into a portfolio.
Incomplete account metrics remain unknown. No new profitability claim is made
by this migration.

See [stock practice](STOCK_PRACTICE.md), [strategy methodology](STRATEGY_LAB.md)
and [change history](CHANGELOG.md). Existing dated research is retained with its
original dates; the UI migration is not a fresh investment-research edition.

## Responsiveness in V12.1

Dashboard and learner polls read job metadata without loading all saved models
and reports. Detailed learning results and backtest journals load when opened.
Idle pages poll every 30 seconds; active jobs poll every eight seconds, with
hidden pages paused and requests bounded by timeouts. Static assets use
content-versioned browser caching and ETags. Text responses support gzip.
Authenticated API responses and HTML stay `no-store`.

See [validation and the local before/after benchmark](research/stock-speed-v12.1-validation.md).
Hosted latency still depends on Render load, network conditions and market data
providers; a code benchmark is not a production latency guarantee.
