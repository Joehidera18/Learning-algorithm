# CryptO V11.18 — complete combined version

This package combines the existing learning and Reddit VWAP research with the
Crypto + Stocks website, seven requested candle intervals and the new Experiments
section. It includes the app, tests, setup instructions and retained research.

## What is included

- Stock research for 20 companies, updating provider market widgets and watchlists.
- Seven active intervals: 1m, 4m, 5m, 15m, 30m, 1h and 4h, plus the dated inventory
  of all 15 downloaded coin archives. Source gaps and venues remain explicit.
- Saved controlled comparisons, bounded research suggestions and optional AI
  planning, with fresh-quote and related-market risk checks for paper entries.
- Forecast-response learning from completed, cost-eligible examples, with the
  existing risk and qualification checks.
- Timestamped news and Alternative.me Fear & Greed observations, with source
  attribution and missing/stale coverage shown in the dashboard.
- A consistent default set of 15 coins for historical practice, monitoring and
  automatic learning.
- The Reddit strategy tester under **Advanced research → Test the Reddit
  strategy**: VWAP re-entry alone, then added volume-profile levels, delta
  divergence and trend filtering. Every variant reports fees, slippage, partial
  exits, trade counts, drawdown and a higher-cost comparison.
- Existing trade finances, loss reviews, paper trading, historical learning and
  the separate 30-day continued-learning study.

The combined version also corrects the daily-loss calculation for VWAP partial
exits: targets crossed at a candle's open are filled before assessing the later
price path. The loss check uses the quantity still open. Actual stop losses
continue to trigger the daily pause.

## Open it locally

Use Python 3.12. Open a terminal at the repository root and run:

```sh
python -m venv .venv
```

Activate the environment with `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\activate` in Windows Command Prompt. Then run:

```sh
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. Existing hosting instructions and access-token
settings are in [WEBSITE_SETUP.md](WEBSITE_SETUP.md). When uploading extracted
source, keep `app.py`, `render.yaml`, `requirements.txt`, `lab/`, `static/` and
`templates/` directly at the repository root.

For an existing installation, preserve its database, data directory and exports
before updating. The source package does not contain your account database,
credentials or a running server. Models from before V11.18 need current validation;
old reports remain viewable. An active registered forward study cannot silently
change its source code; see [FORWARD_STUDY.md](FORWARD_STUDY.md).

## Use the workflows

1. **Main learning:** enter your actual Coinbase fee, choose the coins/timeframes,
   and select **Practice on real market history**. Review the reports before
   starting ongoing paper learning.
2. **Reddit strategy:** open **Advanced research → Test the Reddit strategy**,
   enter one to three Coinbase USD markets, choose the history length and fee,
   and select **Backtest VWAP strategy**. Download its comparison when complete.
3. **Controlled comparisons:** open **Experiments**, choose a market, interval and
   fixed history window, then queue the entry, exit or learning-control question.
   Read [EXPERIMENTS.md](EXPERIMENTS.md) for the rules and optional AI integration.
4. **Long-term stocks:** open **Stock research** for the 20-company catalog,
   investment cases, dated sources, catalysts and updating market widgets.

The Reddit tester needs recorded **one-minute candles**. Existing 5m/15m/1h/6h
exports cannot reconstruct the missing minute paths. Its volume profile and delta
are candle-based estimates with declared assumptions; the original author's
private implementation is not available. It produces a separate research report
and does not install a trading model. An offline CSV runner is also included in
[VWAP_RESEARCH.md](VWAP_RESEARCH.md).

## What the results establish

The retained V11.16 comparison improved one previously reviewed XRP 15m account
from **-$12.75 across six trades to +$6.35 from one trade** after modeled costs.
AVAX 15m remained **-$5.61**; DOT 15m and XRP 6h made no trades. All four remain
unqualified. These are separate $500 simulations, not a combined portfolio or
evidence of reliable future profits.

V11.18 adds 24 fixed entry/exit/learning comparisons across BTC's seven requested
intervals and XRP 15m, plus the four-variant VWAP adaptation on 14 days of recorded
BTC one-minute Binance/USDT candles. All remain inconclusive. The VWAP test made
no trades after its execution checks at the configured costs; it does not prove
compatibility or profitability on Coinbase/USD. See the
[full release findings](research/experiments-v11.18-results.md).
Neither the $10–$15 daily goal nor a sentiment-related profit benefit has been demonstrated.

See [FORECAST_RESPONSE_RESEARCH.md](FORECAST_RESPONSE_RESEARCH.md) for the main
learning comparisons, [VWAP_RESEARCH.md](VWAP_RESEARCH.md) for the strategy
protocol, and
[the combined validation record](research_baselines/combined-release-validation.json)
for the earlier integration checks. The current source remains in
[Joehidera18/Learning-algorithm](https://github.com/Joehidera18/Learning-algorithm).
