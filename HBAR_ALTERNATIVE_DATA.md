# Alternative HBAR spot history

This separate data download covers the original VWAP report's exact window:
2026-03-24 09:39 UTC inclusive through 2026-09-20 09:39 UTC exclusive.
It retrieves Binance and KuCoin HBAR-USDT spot candles, and the HBAR-USD and
HBAR-USDT one-minute members available in Kraken's 2026 Q1/Q2 archives.
The published Kraken archive ends at 2026-07-01 00:00 UTC and cannot cover
the later part of this 180-day window.

```
python3 scripts/download_hbar_alternatives.py --sources binance kucoin kraken --out hbar-alternative-output
```

The command requires Python's standard library and curl. It preserves source
responses and metadata, checks published Binance SHA-256 archive checksums,
validates Kraken ZIP member CRCs and exact HTTP byte ranges, converts timestamp
units explicitly, validates OHLCV and labels every dataset by exchange and pair.
Preserve the output folder to reuse checked request checkpoints.

Binance publishes daily/monthly spot archives and a separate public market-data
API; its post-2024 archive timestamps are microseconds while API timestamps
default to milliseconds. KuCoin returns seconds and orders its price fields
open/close/high/low. Kraken archives use seconds and include trade counts.
Missing turnover or trade-count fields are omitted rather than estimated.

These observations describe different order books. HBAR-USDT is quoted in
USDT, not USD. Use each venue as a separate research dataset; never fill gaps
in Coinbase HBAR-USD with other venues' prices or volume. Raw unknown minutes
remain missing. Provider-supplied zero-volume candles are counted explicitly.
No production history, website, model, trading account or order is changed.

The isolated GitHub Actions job only downloads KuCoin and Kraken because the
Binance public archive is accessible directly in the development workspace.
It uses read-only repository permissions and no account secrets. Actual rows,
failures and coverage are reported only after the download completes.

Sources:

- [Binance public archives and schemas](https://github.com/binance/binance-public-data)
- [Binance public market-data API](https://developers.binance.com/en/docs/products/spot/faqs/market_data_only)
- [KuCoin spot candles](https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines)
- [Kraken quarterly OHLCVT archives](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data)
