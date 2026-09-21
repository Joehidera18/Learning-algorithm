# V11.18 recorded-market findings

All 25 reports are inconclusive. The update improves experiment control, data visibility, restart recovery and paper risk checks; it has not demonstrated dependable trading profits. No result was used to tune rules, raise risk or activate trading.

## Fixed data windows

Each final window was selected by a declared calendar lookback before reading results. BTC data is Binance spot USDT, and XRP data is Coinbase Exchange USD. Source archive/member or dataset hashes were verified. Their venue prices and fee assumptions are not interchangeable.

| Market | Interval | Days requested | Observed candles | Internal missing | First candle UTC | Last close UTC |
| --- | --- | ---: | ---: | ---: | --- | --- |
| BTCUSDT | 1m | 14 | 20,160 | 0 | 2026-09-06 18:50 | 2026-09-20 18:50 |
| BTCUSDT | 4m | 60 | 21,600 | 0 | 2026-07-22 18:48 | 2026-09-20 18:48 |
| BTCUSDT | 5m | 90 | 25,920 | 0 | 2026-06-22 18:50 | 2026-09-20 18:50 |
| BTCUSDT | 15m | 180 | 17,280 | 0 | 2026-03-24 18:45 | 2026-09-20 18:45 |
| BTCUSDT | 30m | 180 | 8,640 | 0 | 2026-03-24 18:30 | 2026-09-20 18:30 |
| BTCUSDT | 1h | 365 | 8,760 | 0 | 2025-09-20 18:00 | 2026-09-20 18:00 |
| BTCUSDT | 4h | 730 | 4,380 | 0 | 2024-09-20 16:00 | 2026-09-20 16:00 |
| XRP-USD | 15m | 180 | 17,255 | 25 | 2026-03-20 05:00 | 2026-09-16 05:00 |

Intervals overlap and are not independent market evidence. All candles are historical development observations, including later chronological windows. The combined row count must not be described as unique observed market time.

## Later-window account results

Every row is a separate $500 simulation. Fees are 0.4% per side; modeled slippage is 0.05% plus 0.05% half spread per side. The higher-cost scenario multiplies all three by 1.5. Higher costs can reject different trades, which explains cases where that account has a better net result but much less evidence. No exchange fee tier was verified by this replay.

| Market / interval | Recipe | Variant | Standard net | Closed trades | Higher-cost net | Higher-cost closed |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| BTCUSDT / 1m | vwap_adaptation | bands | $0.00 | 0 | $0.00 | 0 |
| BTCUSDT / 1m | vwap_adaptation | profile | $0.00 | 0 | $0.00 | 0 |
| BTCUSDT / 1m | vwap_adaptation | delta | $0.00 | 0 | $0.00 | 0 |
| BTCUSDT / 1m | vwap_adaptation | trend | $0.00 | 0 | $0.00 | 0 |
| BTCUSDT / 4h | breakout_retest | breakout | $-14.73 | 8 | $0.41 | 1 |
| BTCUSDT / 4h | breakout_retest | retest | $-2.08 | 3 | $0.00 | 0 |
| BTCUSDT / 4h | exit_rules | fixed | $-14.73 | 8 | $0.41 | 1 |
| BTCUSDT / 4h | exit_rules | break_even | $-14.73 | 8 | $0.41 | 1 |
| BTCUSDT / 4h | exit_rules | trailing | $-14.73 | 8 | $0.41 | 1 |
| BTCUSDT / 4h | exit_rules | six_hour | $-12.70 | 8 | $1.21 | 1 |
| BTCUSDT / 4h | learning_control | frozen | $0.00 | 0 | $0.00 | 0 |
| BTCUSDT / 4h | learning_control | updating | $0.00 | 0 | $0.00 | 0 |
| XRP-USD / 15m | breakout_retest | breakout | $-1.08 | 3 | $5.75 | 1 |
| XRP-USD / 15m | breakout_retest | retest | $2.88 | 2 | $5.70 | 1 |
| XRP-USD / 15m | exit_rules | fixed | $-1.08 | 3 | $5.75 | 1 |
| XRP-USD / 15m | exit_rules | break_even | $-1.08 | 3 | $5.75 | 1 |
| XRP-USD / 15m | exit_rules | trailing | $-1.08 | 3 | $5.75 | 1 |
| XRP-USD / 15m | exit_rules | six_hour | $-1.08 | 3 | $5.75 | 1 |
| XRP-USD / 15m | learning_control | frozen | $0.00 | 0 | $0.00 | 0 |
| XRP-USD / 15m | learning_control | updating | $0.00 | 0 | $0.00 | 0 |

BTC 1m, 4m, 5m, 15m, 30m and 1h had zero later-window trades for all three new recipe families. The ordinary breakout had respectively 94, 81, 114, 69, 40 and 43 attempted entries, all rejected by the cost check. Lowering the assumed fee without a verified tier would change the question rather than establish a working improvement.

XRP retest improved standard net by $3.96 with only two trades, but under higher costs it trailed the control by $0.05 with one trade each. BTC 4h retest reduced standard losses by $12.64, but had no higher-cost trades. The shorter 4h exit reduced standard losses by $2.02; both variants still lost money at standard costs. None meet the evidence floor. All updating/frozen later accounts stayed in cash, so the added experiment does not establish that learning helps.

The VWAP adaptation used real one-minute BTC data, independently of Coinbase. Across the whole window it found 43 band setups, 15 profile setups, two delta setups and one trend setup. Its execution/cost checks produced no entries in either window or cost scenario. These are signal counts, not executed or profitable trades. The original private Reddit strategy has not been reproduced exactly.

## Verification and reproduction

- 452 Python tests passed, including new checks for retest causality, next-candle trailing protection, seed isolation, checkpoint reuse, cancellation, worker ownership, request validation, bounded AI requests, stale quotes and concentration sizing.
- Existing learning and finances JavaScript checks passed. The stock page passed 14 local browser checks; the experiment page passed seven, including mobile layout, token access, queue/retry/export, empty evidence and injection handling.
- Saved release ledgers and summary contain every variant/window/cost account, including zero-trade and negative findings. Accounts are not summed into a hypothetical portfolio.
- Software checks used artificial fixtures. Historical findings above used verified recorded market data; no real-money performance or paid AI call was tested.

See [EXPERIMENTS.md](../EXPERIMENTS.md) for exact rules and commands. The full ledgers are in [experiments-v11.18-ledgers.json.gz](experiments-v11.18-ledgers.json.gz); the website reads [experiments-v11.18.json](experiments-v11.18.json).

Current source digest: `260fc868276b8b6fe1650ba9dcb25d8505e3eafa657f0842c37b3d75a3a21eae`. The legacy VWAP module uses its own filename-plus-bytes digest: `55a408404cf1fc4e8dd14b431876c842e5c0a9305569dc19180879755fe8e84c`.
