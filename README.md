# CryptO V11 — automatic learning and Coinbase

A trading program that studies market history, learns which setups work in different conditions, tests its decisions on later prices, and updates from completed trades.

**Goal: work toward $10–$15 a day from a $500 account. That return has not been demonstrated.** The supplied models start untrained; the program downloads and studies history when you run it. An initial exported Coinbase-history report exposed training and missing-data limitations addressed in this update. Its profitability still needs a new real-history evaluation.

## Start here

1. Open the app locally or follow [WEBSITE_SETUP.md](WEBSITE_SETUP.md) to put it on Render.
2. Enter your actual Coinbase fee per side. The initial 0.4% is an assumption until confirmed.
3. Edit **Coins to practice on**, then click **Practice on real market history** to train before starting current-market monitoring.
4. Review the historical results, then use **Start learning & paper trading** for ongoing practice on new prices.

Historical practice requests real Coinbase candles for up to three years for your selected coins. The default list contains BTC, ETH, SOL, HBAR, XRP, XLM, ADA, DOGE, AVAX, LINK, LTC, BCH, and DOT. You can enter up to 20 Coinbase USD tickers, separated by commas or spaces; short names such as HBAR and full names such as HBAR-USD are accepted. The last submitted list is saved and restored after reopening the page. Markets are processed one at a time. An unavailable market or insufficient history is reported for that coin while the remaining list continues. The simulated clock advances through the recorded prices as quickly as the computer can process them; one hour of market history does not require one hour of waiting. Downloads still take time. Decisions use only information available at the past signal close, and a result updates learning only after its trade closes. The app keeps observed price sections on both sides of gaps and never replaces missing or unavailable data with generated prices. Invalid or insufficient data produces a failed report.

The practice control uses the candle interval in Settings (5 minutes, 15 minutes or 1 hour), saves qualifying models, and finishes without starting live feeds or trading runners. Existing runners, if already started, keep their current state. Separate later historical periods check what the learner learned. Changing intervals requires a separate qualification; it does not create independent copies of the same market evidence.

The program handles the research work in the background. It loads the market scanner, requests up to three years of history for five liquid Coinbase USD markets, trains models, and tests them on later data. Qualified models can open paper trades and update after those trades close. Unqualified markets stay out of the account.

The first download can take time. Completed download chunks, candidate training labels, and results are saved. A restart within 24 hours resumes the same training cutoff and skips completed candidates; an interrupted candidate restarts. A complete first study of five markets with three years each represents 131,400 market-data hours; these are summed across coins and are not 131,400 independent hours of market history. The dashboard shows the hours actually processed. Indicators restart after each gap with 240 observed candles of warmup. A training trade interrupted by missing prices has no known outcome and cannot teach the model; a policy account test interrupted while holding a position is marked incomplete and cannot qualify.

Pause entries keeps existing paper positions monitored. Stop stops automatic learning and the paper runner. Closing a browser leaves a running server alone; a computer or server restart stops the runners. Reopen the app and resume them after checking its status.

## What learns

The model learns relationships between entry-time indicators and the trade's eventual result after costs. Successful and failed trades both update its estimates. It chooses among 16 stop/target variants within four defined trade types: trend pullback, volume breakout, range reclaim, and combined confirmations. Each variant combines an overall estimate with evidence for rising, falling, or sideways conditions when enough examples exist. The templates remain long-only, so bearish conditions can mean no eligible trades or training examples.

Historical training explores signal-matched setups even when their modeled costs or reward would block a trading entry. These independent hypothetical examples still pay all modeled fees, slippage and spread, so costly losses can be learned. They are not account returns. Policy tests and paper/live trading keep the cost and net-reward checks, evidence requirements, and account-risk limits. Historical policy tests also apply the configured daily loss halt. Reports compare the updating policy with pooled learning, frozen learning, holding cash, and buying and holding the market. These comparisons can show deterioration; they do not select a winner after seeing the final test.

This is a small online machine-learning model. It learns entry preferences and strategy selection within those trade types; it does not autonomously invent arbitrary executable strategies or train a language model.

The scanner watches up to 30 active Coinbase USD markets under the default settings. Automatic historical learning studies the first five in that volume-ranked list. It does not study every Coinbase asset at once, and it does not include news, sentiment, or on-chain data.

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
