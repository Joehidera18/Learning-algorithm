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
   cost stress on the later window. `eligible_for_bot` is true only if the later
   window has at least 20 trades, positive mean R, positive net PnL, and still
   positive mean R at higher costs.

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
