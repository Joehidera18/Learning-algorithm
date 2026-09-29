# HBAR minute-candle recovery

This one-off research download requests every minute in the HBAR report's
180-day window, from 2026-03-24 09:39 UTC through the exclusive cutoff
2026-09-20 09:39 UTC. The source report received 237,240 candles and listed
21,960 missing minutes. Its 60-request recovery pass retrieved none.

The downloader queries Coinbase Exchange and Coinbase Advanced Trade public
candles separately. It retains each API response, rejects invalid observations,
checks every requested time window, and reports missing minutes and differences
between the two feeds. It never manufactures a candle, assumes a missing minute
had no trades, or automatically mixes conflicting price histories.

Run from the repository root:

```sh
python3 scripts/download_coinbase_minutes.py --symbol HBAR-USD --start-ms 1774345140000 --end-ms 1789897140000 --out candle-recovery-output
```

Outputs include a separate CSV for each provider, the original responses in
compressed checkpoints, and `recovery-report.json`. Preserve the output folder
to resume a interrupted download without repeating completed requests.

The draft recovery branch also runs this command through GitHub Actions so
downloads can proceed when the development workspace cannot reach Coinbase.
The workflow has read-only repository permissions, uses no account secrets,
does not deploy the website, and does not update the production candle cache,
models or trading state. The downloadable artifact retains all returned public
market observations and failures, including zero-candle outcomes.

The result still needs comparison with the report's exact missing timestamps.
Downloading more observations does not establish strategy profitability.

Sources:

- [Coinbase Exchange candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)
- [Coinbase public Advanced Trade candles](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles)

Coinbase Exchange documents that periods without ticks have no candle. An
absent bucket is therefore not, by itself, proof of a failed download or proof
that no trade occurred. Unknown periods remain missing unless actual data or
independent, complete trade coverage resolves them.
