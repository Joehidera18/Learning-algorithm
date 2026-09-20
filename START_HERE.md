# CryptO V11.16 — complete combined version

This package contains the V11.16 learning improvements and the Reddit VWAP
strategy research tool in the same application. It includes the application,
dashboard, tests, setup instructions and retained research records.

## What is included

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

Use Python 3.12. Extract the ZIP, open a terminal inside `CryptO-V11.16`, and run:

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
credentials or a running server. Models from before V11.16 need fresh practice;
old reports remain viewable. An active registered forward study cannot silently
change its source code; see [FORWARD_STUDY.md](FORWARD_STUDY.md).

## Use the two workflows

1. **Main learning:** enter your actual Coinbase fee, choose the coins/timeframes,
   and select **Practice on real market history**. Review the reports before
   starting ongoing paper learning.
2. **Reddit strategy:** open **Advanced research → Test the Reddit strategy**,
   enter one to three Coinbase USD markets, choose the history length and fee,
   and select **Backtest VWAP strategy**. Download its comparison when complete.

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

No Reddit-strategy market profit result is available: the prior Coinbase minute
download failed. Passing software tests establishes software behavior, not
strategy profitability. Neither the $10–$15 daily goal nor a sentiment-related
profit benefit has been demonstrated.

See [FORECAST_RESPONSE_RESEARCH.md](FORECAST_RESPONSE_RESEARCH.md) for the main
learning comparisons, [VWAP_RESEARCH.md](VWAP_RESEARCH.md) for the strategy
protocol, and
[the combined validation record](research_baselines/combined-release-validation.json)
for integration checks. The combined source is on `improve/learning-reliability`
in [pull request #16](https://github.com/Joehidera18/Learning-algorithm/pull/16).
