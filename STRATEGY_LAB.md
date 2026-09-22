# Strategy lab

Research folder for one strategy at a time. Historical bars only. Nothing here
places a live order.

## What it does

1. You put a strategy in `strategies/` with a `signal(features, params)` function.
2. You pick a **decision** timeframe (1m, 5m, 15m, 30m, 1h, or 4h).
3. You pick optional **context** timeframes. Those bars are attached only after
   they have already closed. A missing higher-timeframe candle is marked
   `ready=False`. The lab does not invent it or skip forward to the next one.
4. The existing paper engine fills on the **next** decision bar open, charges
   fees, and assumes stop-first when a bar is ambiguous.
5. History is split: first 70% development, last 30% later test, plus a 1.5×
   cost stress on the later window. Both later tests must finish with at least
   20 resolved trades, positive mean R and positive account PnL. An unresolved
   position at a candle gap makes account PnL unknown and prevents eligibility.
   Total account PnL includes window-end marks; those marks do not count toward
   the 20 resolved trades. This flag does not authorize or enable live trading.

## Run it

List strategies:

```sh
python run_strategy_lab.py --list
```

Stock opening-range breakout (needs session bars; use 5m decision so the 15m box can form):

```sh
python run_strategy_lab.py --strategy orb_15m --symbol SPY --asset equity --decision 5m --context 15m,1h --days 59 --out reports/spy-orb-5m.json
```

Older structure families:

```sh
python run_strategy_lab.py --strategy trend_pullback_simple --symbol SPY --asset equity --decision 15m --context 1h,4h --days 59 --out reports/spy-15m.json
```

Crypto example, using CSVs you already downloaded (`SYMBOL_15m.csv`):

```sh
python run_strategy_lab.py --strategy breakout_volume_simple --symbol BTCUSDT --asset crypto --decision 15m --context 1h,4h --csv-dir data --out reports/btc-15m.json
```

`orb_15m` is a cash-session strategy. It will skip crypto CSVs that have no `session_open_ts`.
It supports 1m, 5m and 15m decision candles. Every opening candle from the session
open through minute 15 must be present with its full duration. A missing first,
middle or final opening candle invalidates the range. Relative volume needs
20 prior complete observed opening ranges; an incomplete observed range resets
that history. A whole missing session cannot be inferred from absent input.

## Corrected reports (version 2)

Reports from the earlier lab must be rerun. Their saved files are retained, but
the website and export API no longer treat their old eligibility flag as valid.
Current incomplete reports show unavailable account PnL and the stopping reason.

The website uses the same `APP_ACCESS_TOKEN` check and JSON request validation as
the rest of the app. Strategy scripts and pages are public; status, job creation
and report exports require the configured token.

Indicator warmup restarts after missing decision candles. Stock indicators and
coverage use the exchange calendar, including weekends, holidays and early
closes. A context candle is usable only when it matches the latest expected
close; an older observed candle cannot replace a missing one. The final bar of
the previous stock session remains valid until a new context bar is due.

Massive 1h/4h stock data is built from complete 30-minute bars anchored to the
regular-session open. Native Massive hourly bars start on the hour and cannot
be used as 09:30-based stock candles. See [Massive's timestamp documentation](https://massive.com/knowledge-base/article/how-does-massive-treat-hourly-bars-when-querying-regular-trading-hours).
Identical bars repeated by snapped chunk boundaries are deduplicated; conflicting
observations fail the download.

The optional context selector supplies completed candles to a strategy. It does
not add a new entry filter to a strategy that never uses those fields. Strategies
with `require_context` reject unavailable required frames in the shared runner.

## Add a strategy

Copy `strategies/orb_15m.py` or `strategies/structure_family.py`. Give it a new
`name`. In `signal`, return `(score, None)` to enter or `(None, "reason")` to skip.
Optional `prepare(rows, features, interval)` can stamp session levels before the run.

Do not paste a chat transcript into the live Coinbase or stock runner. Promote
only a frozen file after the later-window report passes.

## Data limits

- Yahoo 1m history is about 29 days. A 1m test is not a multi-year study.
- Yahoo 5m history is about 59 days.
- Stock day mode flattens at the regular-session close.
- Gaps on the decision series stop that path. Coverage is written into the report.
