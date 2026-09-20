# Intraday candle coverage (V11.17)

The dashboard and historical practice now offer 1m, 4m, 5m, 15m, 30m, 1h and 4h. Six-hour studies remain readable for compatibility but are no longer a default or a decision option. The monitoring refresh runs every minute; an entry still requires a newly completed decision candle, fresh prices and the existing validation/risk gates.

Coinbase does not provide native 4m, 30m or 4h Exchange candles. These are derived from complete, closed 1m, 15m and 1h windows respectively. Missing source candles prevent a derived candle from being emitted. No interpolation or cross-venue replacement is used. The Markets table reports gaps and zero-volume records in the rolling runtime window; this is distinct from full historical archive coverage.

## Full historical downloads

`scripts/build_coin_candle_library.py` downloads available Binance spot USDT one-minute history from the first public candle to an explicit closed-minute cutoff. It verifies monthly/daily archive checksums, rejects malformed observations individually while preserving valid neighbors, repairs missing ranges with the same venue's public API, and exports seven compressed CSV datasets per coin. Its SQLite work cache and streaming exports bound memory usage. Each output manifest records source URLs/checksums, coverage, remaining gaps, zero-volume records, repair failures and file hashes.

The configured universe is BTC, ETH, SOL, HBAR, XRP, XLM, ADA, DOGE, AVAX, LINK, LTC, BCH, DOT, UNI and AAVE. The workflow runs five coin downloads concurrently and retains its output artifacts for 90 days. The initial job uses a fixed exclusive cutoff of 2026-09-20 18:50 UTC. Subsequent app commits do not restart the initial download.

```bash
python3 scripts/build_coin_candle_library.py --coin HBAR --end-ms 1789930200000 --out datasets/HBAR
```

Use a cutoff that is already in the past. Timestamps are UTC Unix milliseconds. Larger archive candles require every underlying minute; partial boundary buckets are omitted. Provider-supplied zero-volume candles are identified separately from absent records. Historical availability starts at the first available listing candle, not before the coin existed. Genuine exchange outages or unavailable source history cannot be guaranteed gap-free.

These Binance/USDT datasets are separate research inputs. They are not automatically imported into the Coinbase/USD runtime or substituted into its backtests. A deployed Render instance is not changed by a draft pull request. The app's Coinbase practice process retains its own history and reports requested versus effective coverage. Processing limits (1m: 90 days; 4m/5m: 365; 15m/30m: 1,825; 1h/4h: 2,920) limit each study, not the full archive downloader. The existing registered 30-day forward comparison remains limited to its previously supported 15m/1h study protocol.

More history and more timeframe choices are not evidence of profitable trading. Keep out-of-sample, costs, stress tests and prospective qualification gates in place.

For a previously downloaded archive, `scripts/repair_candle_archive.py ARCHIVE.zip --out OUTPUT_DIRECTORY` retries its known gaps and rebuilds only affected higher-timeframe buckets. It preserves existing rows, rejects conflicts, records supplementary source provenance, and emits a new ZIP.
