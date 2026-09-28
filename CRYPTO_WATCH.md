# Crypto breakout watch · V12.3

The active trading engine remains stock paper execution. `/crypto-watch` is a
separate, read-only market observer. It does not place orders, turn on retired
crypto learners, run crypto backtests or perform automatic paid AI research.

## Turn it on

Merge and deploy this update to the existing Learning-algorithm Render service.
Open **Crypto watch**, enter the existing app access token if prompted, then
select **Start watch**. The watch needs `APP_ACCESS_TOKEN`; public market candles
and headlines do not need an OpenAI key. It starts disabled on a new installation.
It remembers an enabled watch and resumes after a normal server restart. Stop
watch persists the disabled state. Keep the existing one-worker deployment.

The server checks 12 Coinbase USD pairs every five minutes: BTC, HBAR, ETH, SOL,
XRP, XLM, LINK, ADA, DOGE, AVAX, LTC and BCH. A closed browser does not stop the
server worker. Alerts are saved in the dashboard, **not delivered to a phone or
email**. Paused/unavailable hosting and failed data feeds interrupt coverage.

## What the signals mean

- **Building interest:** close within 1% below the preceding 20-candle high,
  volume at least twice the preceding 20-candle median, positive 15-minute price
  change and outperformance versus BTC. A breakout has not been confirmed.
- **Breakout observed:** close above that high, at least three times median
  volume, positive momentum and outperformance versus BTC.
- **Already extended:** at least +5% in 15 minutes, +15% in 24 hours, or four
  prior ATRs above the previous high. This takes priority over a breakout label;
  chasing an already large move is not an early warning.
- **Quiet:** no qualifying combination in the latest usable candle.
- **Unavailable/stale:** missing evidence, not an assessment of price direction.

Rules are fixed exploratory heuristics. They are not fitted to HBAR's rally, have
no calibrated success probability and have not demonstrated profitability. BTC
is its own benchmark and does not require relative outperformance of itself.
Each venue's recent median candle turnover is multiplied by 288 as a rough daily
liquidity estimate; values below $250,000 block signals. This is not exact daily
exchange volume or order-book depth.

Each assessment requires 289 contiguous closed five-minute candles for its
24-hour return. No missing candle is invented. The event bar is excluded from
its own resistance, volume and ATR baselines. BTC comparisons require matching
timestamps. Candles older than ten minutes are rejected. Refreshing the page
does not trigger extra provider requests; requests happen in the background.

Coinbase's [candle API documentation](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)
states that intervals without ticks can be missing, and that historical rates
should not be polled frequently. This implementation makes one bounded request
per pair per five-minute scan, with no automatic retries. It is not a streaming
tick feed and cannot capture every intrabar move.

## News and research

An hourly, bounded CoinDesk RSS fetch stores headlines only. Coverage is limited:
it is not a comprehensive official-announcement, social-media or exchange-listing
monitor. Publication time and first observation of each revision are separate.
Finding an old headline today does not imply this app knew it yesterday.

**Investigate with AI** opens a prepared question in the existing agent. It asks
for workspace observations, current primary sources, contrary evidence and token
value capture. Submit the question to start research using the separately
configured OpenAI key. Opening the link does not incur a provider request.
The agent can read compact watch state through its existing workspace tool.

## Evidence, limits and storage

`RESEARCH_DATA_DIR/crypto-watch.sqlite3` stores state, latest assessments, up to
90 days of alert observations and 30 days of headline revisions. Dashboard and
export return the latest 100 alerts and 30 headline revisions. A one-hour
cooldown per symbol/stage limits repeats; the same candle/stage is never logged
twice. First scans and scans following missing or interrupted coverage are
labeled initial snapshots. Alerts are dated when observed, never backdated to
historical bars or news publication dates.

This journal supports later evaluation of false positives, missed moves and
returns after costs. No historical-replay report or outcome accuracy is invented.
No automatic model retraining occurs. A single-venue, five-minute rule set can
miss sudden moves, react after news has been priced in, and produce losing signals.

## HBAR investigation · September 28, 2026

The deployed app reported V12.2, equity execution, and crypto execution disabled.
Inspection found on-demand AI research, but no continuous crypto breakout watch.
That is a monitoring gap; it does not establish whether a stock/crypto strategy
could have predicted this particular move.

A [THG announcement distributed by PR Newswire on September 23, 2026 at 10:02 ET](https://www.prnewswire.com/news-releases/thg-and-ibm-sign-global-partnership-to-bring-idtrust-as-agentic-ai-identity-solution-on-ibm-cloud-catalog-as-know-your-agent-kya-becomes-an-enterprise-priority-302887805.html)
described an IBM partnership involving its Hedera-based IDTrust offering. The
[IBM catalog entry](https://cloud.ibm.com/catalog/content/thg-idtrust-648d7223-f5c2-4ac4-82c8-1fda7687b2b1-global)
corroborates the offering's presence. Its catalog metadata predates the September
announcement, so the press-release date must not be presented as proof of its
first listing. This was a reason to investigate before September 28, not proof of
imminent token appreciation or proof of the rally's sole cause.

Coinbase and Kraken candle retrieval attempts timed out in the development
environment. A real intraday replay was therefore unavailable. Generated test
fixtures verify timing, missing-data handling, persistence and controls; they are
not evidence that these rules would have caught HBAR before its actual rally.
