# V11.19 recorded stock practice checks

Nine fixed-window runs used recorded Yahoo stock/ETF candles. These are historical development checks, not unseen validation or proof of profitability. Each variant is a separate $500 account. All comparisons were labelled `insufficient_evidence`; every frozen and updating learner account remained in cash. No strategy was promoted.

| Market | Frame / style | Calendar days | Candles | Missing scheduled candles | Earlier resolved examples | Breakout net | Breakout closed trades | Retest net |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SPY | 1m / day | 29 | 7,409 | 1 | 77 | $-3.88 | 5 | $-5.15 |
| SPY | 4m / day | 29 | 1,861 | 1 | 29 | $-3.58 | 3 | $-0.97 |
| SPY | 5m / day | 59 | 3,120 | 0 | 95 | $-2.48 | 3 | $-0.34 |
| SPY | 15m / day | 59 | 1,040 | 0 | 43 | $0.21 | 1 | $0.00 |
| SPY | 30m / day | 59 | 520 | 0 | 17 | $0.00 | 0 | $0.00 |
| SPY | 1h / swing | 365 | 1,732 | 12 | 52 | $-4.99 | 2 | $0.00 |
| SPY | 4h / swing | 729 | 988 | 5 | 16 | $2.59 | 1 | $0.00 |
| SPY | 1d / swing | 1825 | 1,253 | 0 | 194 | $0.72 | 7 | $-0.50 |
| NVDA | 1h / swing | 365 | 1,733 | 11 | 61 | $-7.92 | 4 | $0.25 |

The complete standard/higher-cost results, including all exit and learning variants, are in `stock-practice-v11.19.json`. The reproduction archive retains all nine source snapshots, complete ledgers, learned seeds and manifests. Observations across frames overlap; their counts are not independent evidence. Download cutoffs and provider timestamps are retained per snapshot.

An initial seven-day SPY 4m request produced 490 bars and was rejected because the prescribed warmup and purge left insufficient development history. That failure is retained in the archive. Minute requests were subsequently paginated in six-day blocks over 29 days; the later 4m run had 1,861 observed bars. The protocol was not shortened to force a result.

Missing bars and invalid provider OHLC observations were retained as gaps. No fabricated candles, merged data feeds, extrapolated results or portfolio aggregation were used. Day sessions used actual New York calendar closes, including shortened final bars. The price-only comparison excludes dividends.

The learner gathered examples, but none of these historical account tests met its entry-evidence filters. Forward practice therefore also studies new, cost-eligible candidate setups causally, even while its account is in cash. Those overlapping training examples are not returns or trades of the paper account.

## Reproduce

Install `requirements.txt`. Read the gzip JSON array in `stock-practice-v11.19-reproduction.json.gz`, then pass each successful entry's `snapshot` and `manifest` into `lab.equity_research.run_stock_practice`. The final archive entry is the explicitly retained initial short-window failure. No fresh feed or API key is needed to replay these snapshots.

For a new observation window:

```sh
python scripts/run_stock_practice.py --symbol SPY --interval 1h --days 365 --mode swing --output data/spy-stock-practice.json
```

For a previously exported snapshot use `--snapshot path/to/snapshot.json.gz` with matching `--symbol` and `--interval`. New market data can differ; it must not be substituted into the archived result under the old identity.

Source code SHA-256: `cf2a75c69a0c8ff59fff38bd2f0e94508ac7990141d1a50c2993c2eea2c8b748`.

Reproduction archive SHA-256: `dfd30f53163f61060fe08bcad5037c7e1337570afb974ef1026026d017051c1b`.

Software verification is separate from market evidence. Calendar, causality, stock execution, split/share sizing, persistence and forward-registration tests use synthetic fixtures. The optional Alpaca path is exercised with mocked API responses; no Alpaca credentials were available for a real feed request.
