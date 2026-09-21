# Fifteen-coin candle history

58,253,757 observed one-minute candles, plus 33,252,265 derived candles across 4m, 5m, 15m, 30m, 1h and 4h. The download covers all 15 configured coins, with a fixed exclusive cutoff of 2026-09-20 18:50 UTC.

**The history is not gap-free.** Each file begins at the first available candle found for its Binance USDT pair. Missing source observations remain explicitly absent; prices were not invented. Provider-supplied zero-volume candles are counted separately. All larger candles require every underlying minute. Partial first/last larger buckets are excluded.

Binance spot USDT datasets are separate from Coinbase USD history. These files have not been imported into the live Render instance. Historical study processing limits do not truncate these downloadable archives. No profitability or deployment claim is made.

## Available history

| Coin | First available (UTC) | 1m candles | Missing minutes | 1m coverage | Zero-volume minutes |
|---|---|---:|---:|---:|---:|
| BTC | 2017-08-17 04:00 UTC | 4,766,346 | 16,784 | 99.64910% | 23,664 |
| ETH | 2017-08-17 04:00 UTC | 4,774,481 | 8,649 | 99.81918% | 32,136 |
| SOL | 2020-08-11 06:00 UTC | 3,211,961 | 1,449 | 99.95491% | 22,331 |
| HBAR | 2019-09-29 04:00 UTC | 3,667,392 | 2,618 | 99.92867% | 326,026 |
| XRP | 2018-05-04 08:11 UTC | 4,402,568 | 5,911 | 99.86592% | 5,220 |
| XLM | 2018-05-31 09:30 UTC | 4,363,609 | 5,911 | 99.86472% | 105,947 |
| ADA | 2018-04-17 04:02 UTC | 4,427,295 | 5,913 | 99.86662% | 56,395 |
| DOGE | 2019-07-05 12:00 UTC | 3,790,272 | 3,098 | 99.91833% | 356,484 |
| AVAX | 2020-09-22 06:30 UTC | 3,151,449 | 1,451 | 99.95398% | 51,123 |
| LINK | 2019-01-16 10:00 UTC | 4,034,171 | 4,119 | 99.89800% | 130,243 |
| LTC | 2017-12-13 03:32 UTC | 4,605,059 | 8,179 | 99.82271% | 18,196 |
| BCH | 2019-11-28 10:00 UTC | 3,580,895 | 2,355 | 99.93428% | 81,026 |
| DOT | 2020-08-18 23:00 UTC | 3,200,859 | 1,451 | 99.95469% | 21,819 |
| UNI | 2020-09-17 03:00 UTC | 3,158,861 | 1,449 | 99.95415% | 51,229 |
| AAVE | 2020-10-15 03:00 UTC | 3,118,539 | 1,451 | 99.95349% | 79,250 |

## Every requested timeframe

| Coin | 1m | 4m | 5m | 15m | 30m | 1h | 4h |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 4,766,346 | 1,191,567 | 953,259 | 317,742 | 158,859 | 79,419 | 19,827 |
| ETH | 4,774,481 | 1,193,605 | 954,889 | 318,287 | 159,135 | 79,557 | 19,861 |
| SOL | 3,211,961 | 802,985 | 642,390 | 214,128 | 107,062 | 53,527 | 13,372 |
| HBAR | 3,667,392 | 916,838 | 733,475 | 244,487 | 122,240 | 61,112 | 15,262 |
| XRP | 4,402,568 | 1,100,630 | 880,509 | 293,498 | 146,744 | 73,363 | 18,318 |
| XLM | 4,363,609 | 1,090,890 | 872,718 | 290,901 | 145,446 | 72,714 | 18,156 |
| ADA | 4,427,295 | 1,106,811 | 885,454 | 295,145 | 147,567 | 73,774 | 18,420 |
| DOGE | 3,790,272 | 947,558 | 758,051 | 252,679 | 126,336 | 63,160 | 15,773 |
| AVAX | 3,151,449 | 787,856 | 630,287 | 210,093 | 105,044 | 52,517 | 13,119 |
| LINK | 4,034,171 | 1,008,532 | 806,830 | 268,938 | 134,465 | 67,224 | 16,786 |
| LTC | 4,605,059 | 1,151,250 | 921,004 | 306,992 | 153,487 | 76,733 | 19,156 |
| BCH | 3,580,895 | 895,215 | 716,176 | 238,722 | 119,358 | 59,672 | 14,903 |
| DOT | 3,200,859 | 800,209 | 640,169 | 213,387 | 106,691 | 53,341 | 13,325 |
| UNI | 3,158,861 | 789,710 | 631,770 | 210,588 | 105,292 | 52,642 | 13,151 |
| AAVE | 3,118,539 | 779,629 | 623,705 | 207,899 | 103,947 | 51,969 | 12,982 |

## Files and verification

Each ZIP contains seven gzip-compressed CSV files, README.txt and manifest.json. CSV timestamps are UTC Unix milliseconds; columns include OHLCV, quote volume, trade count and taker-buy volume. The manifest records exact missing ranges, source URLs and hashes, rejected records and repair outcomes. Original valid observations were retained unchanged.

The supplemental repair recovered 103,249 additional valid minutes after rejecting malformed observations individually. Source download ZIPs were checked against GitHub artifact SHA-256 digests. Each output dataset has its own SHA-256 checksum. The source archives were verified against published Binance checksums by the downloader.

BTC's supplemental API retry was blocked by local network policy. Its final file includes recoveries from verified cached responses; unavailable ranges remain recorded as gaps. The original GitHub download completed successfully.

All 105 compressed datasets were read to completion and checked against their manifest hashes and row counts. Two incomplete intermediate outputs were rebuilt before delivery; ETH 15m was reconstructed from verified 1m data and compared with every original valid 15m observation.

| Coin ZIP | Size (MiB) | SHA-256 |
|---|---:|---|
| BTC-candle-history.zip | 314.7 | `3ad3db69818dc165076978806677ce56eb8d9a4f630c3eed5172928f3d61138b` |
| ETH-candle-history.zip | 286.7 | `0cb082b0b7b88a8972b8f6b8f5299a56ad7d425731579abf998333cdff7dc544` |
| SOL-candle-history.zip | 165.3 | `46a0bc700184ca07a1fef0380e88edc7c10a240d7166ed56e438443e19d6dd8f` |
| HBAR-candle-history.zip | 154.6 | `f3a8bd22a08b2ec42bb21a359a2b47e7eec88d5020f84b0c7366abcc171a53d3` |
| XRP-candle-history.zip | 229.5 | `e024136a0dde29dde97dc1eb7148d96e203f54840c53c8e7df45d93d38a74703` |
| XLM-candle-history.zip | 193.9 | `8a068bd2c479b766825cebe2a46d2b445f2c6a65ea86647104549ac78b02a974` |
| ADA-candle-history.zip | 221.5 | `550cdffb0fda61c2131b73587d0569e4cfc46a70dc88fa1b39bd2ff984425f2a` |
| DOGE-candle-history.zip | 185.9 | `ac74c1595fbe4e0941761465a9d57952731933b83a45e1736d9d00922127e296` |
| AVAX-candle-history.zip | 143.6 | `0c93833a30fbf70b4c7fde8f1da92c665c87d90b93bc504edc5ec86c0cf530e5` |
| LINK-candle-history.zip | 192.4 | `e4fa1f52d10f028716a5fc5b296d52835c8eadcb9f3c881430db1c88c9775fe3` |
| LTC-candle-history.zip | 234.7 | `719de73200445815cba9e15532748a3f8bb8a37e1b99626b9a3cbf2880b2901e` |
| BCH-candle-history.zip | 163.4 | `65348549b0b8cd045e5ce68d3d21ccaafb7c34e899d4b6b84902bb726a5208ad` |
| DOT-candle-history.zip | 152.9 | `34592e21868f0cfe191c3da424204b1891329c16b008d02036f75148e648c4c0` |
| UNI-candle-history.zip | 147.7 | `8cf4f2c2526966535bff458faaadbdd8c2218e7644c77113c50f3b1285a7df5c` |
| AAVE-candle-history.zip | 145.4 | `fe193ce23f5652429e0739463b9f15d5a5954fe38efd750671013866c830d2d4` |

Code and timeframe changes: [GitHub PR #20](https://github.com/Joehidera18/Learning-algorithm/pull/20). Original download artifacts: [GitHub Actions run](https://github.com/Joehidera18/Learning-algorithm/actions/runs/35530551374). Those artifacts precede the supplemental repair; these downloaded ZIPs include that repair.
