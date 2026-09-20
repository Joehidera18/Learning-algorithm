# Observed news and trade reviews — V11.13

The learner records selected news sources and official calendars, joins the versions known at each signal close, and learns from later net outcomes. V11.13 expands that context and records what arrived between a paper signal, entry and closure. This does not establish that news predicts returns or explains why a particular trade lost.

## Sources and coverage

| Source | Information / asset scope | Check interval | Freshness after success |
| --- | --- | --- | --- |
| Fed monetary RSS | Policy announcements; all markets | 15 minutes | 1 hour |
| Fed regulatory RSS | Regulatory announcements; all markets | 15 minutes | 1 hour |
| SEC press releases | Regulatory announcements; all markets | 15 minutes | 1 hour |
| BLS calendar | Scheduled national economic releases | 15 minutes | 24 hours |
| Fed meeting calendar | FOMC meeting start dates | 15 minutes | 24 hours |
| Coinbase status Atom | Operational incidents | 5 minutes | 1 hour |
| CoinDesk RSS | Crypto reporting; headline asset matches | 5 minutes | 1 hour |
| BBC World RSS | World reporting; all markets | 5 minutes | 1 hour |
| Ethereum Foundation blog | Project publications; ETH | 15 minutes | 24 hours |
| Bitcoin Core releases | Client releases; BTC | 15 minutes | 24 hours |
| AvalancheGo releases | Client releases; AVAX | 15 minutes | 24 hours |
| Polkadot SDK releases | Client releases; DOT | 15 minutes | 24 hours |
| XRPL rippled releases | Client releases; XRP | 15 minutes | 24 hours |
| Solana Agave releases | Client releases; SOL | 15 minutes | 24 hours |

The background scheduler checks which sources are due every 30 seconds, with at most three simultaneous requests, 12-second socket timeouts and a 2 MB response limit. Failed attempts also start their retry interval. Publisher delays, fetch duration and scheduler delay add to the intervals above. Redirects from the fixed HTTPS endpoints are reported for review. This is not execution at breaking-news latency.

The collector saves headline metadata, links, timestamps and revisions, not full articles. BBC World is broad reporting, not a classifier restricted to wars or financially relevant events. Reporting can repeat unverified claims. Project releases can be prereleases, client updates or documentation announcements; they do not establish a mainnet activation date or trading direction. Dedicated project coverage includes six named assets, not every scanned coin.

The dashboard shows recent reporting, project publications from the last 30 days, upcoming dates, topic coverage and individual source errors. **Start event collection** runs independently of trading. Historical practice and automatic learning also start collection. Collection continues after practice; its own **Stop event collection** button stops it. Settings and observations survive restart on the configured persistent database. The ordinary trading Stop button stops trading and learning, with a separate visible event control.

BLS dates use Eastern time with daylight-saving conversion. FOMC entries describe the **start of the meeting, date only**; no statement-release hour is invented. Missing future entries become withdrawn only after a complete successful calendar fetch. Explicit cancellations remain distinct. A failed request cannot withdraw a schedule.

## Learned inputs

The existing 32 inputs are extended by 15 event inputs, for 47 total:

- The fraction of configured sources with a recent successful check.
- Five counts of relevant announcements in the preceding 24 hours: macro, regulation, crypto reporting, exchange operations and world reporting.
- A count of relevant project publications in the preceding 30 days.
- Counts of known scheduled events due within 24 hours and seven days.
- Six topic-specific source coverage values, using applicable project asset scopes.

The old seven event inputs retain their order; the eight additions follow them. Counts use fixed bounded scales. No input has a prescribed bullish/bearish sign. Only resolved, costed outcomes train the coefficients. Losses and net break-even trades remain valid feedback without increasing position risk to manufacture learning.

Topic coverage measures recent source checks, not completeness or truth. `null` in recorded context means no applicable configured source; zero means configured sources were unavailable or stale. Both map to zero in that topic's numerical feature. The global source fraction remains across all configured sources; topic values make its limits explicit. Older compatible archives without source definitions have unknown topic coverage, rather than coverage inferred from future articles.

Project feeds use fixed asset tags even when a release title omits the coin's name. Other headlines match selected major names and unambiguous tickers. Macro/regulatory items and unrecognized asset mentions remain broad context. This is limited matching, not complete entity resolution. SEC publications are not automatically classified as enacted law. Article meaning, jurisdiction, economic actual/consensus values, token unlock schedules and on-chain measurements are not parsed.

If all collection is unavailable, the event vector is zero. Previously observed announcements may remain visible after a feed goes stale; this does not establish that no newer news exists. Risk rules, costs and qualification remain enforced. Policy v17/report 19 require fresh practice; prior models are not silently resized into event-trained models.

A study with recorded event coverage also trains an independent price-only control on the same candles, costs and review boundaries. Ordinary- and higher-cost differences are reported. This comparison cannot select or promote a strategy. Without historical event coverage, a price replay provides no evidence of a news-related edge.

## Paper-trade review

| Record | Timestamp and purpose |
| --- | --- |
| Signal snapshot | Available by the completed signal candle; the saved learning vector uses this snapshot |
| Entry snapshot | Available at the actual local entry decision, alongside the quote timestamp; review only |
| After-entry observations | Revisions becoming available after entry and by the local close decision; review only |

Signal and entry snapshots persist across restart and cannot be rewritten by a later correction. Closure preserves those snapshots and adds up to 20 later revisions, their full count, a truncation indicator and separate quote/decision timestamps. Positions without prior evidence receive no invented news history. The dashboard exposes publications, observation times and known schedules alongside existing net P&L, costs, forecasts and path reviews.

The saved recent/upcoming lists are bounded display samples; counts and the exact study archive retain the broader record. Descriptive completed-trade groups overlap and exclude end-of-test valuations. These associate results with observed conditions; they do not identify a headline as the cause of a loss. After-entry news never becomes an earlier input or a reward for merely trading.

## Preventing hindsight and duplicate evidence

Every revision distinguishes provider publication, local first observation, availability and occurrence/scheduled time. Availability is the later of publication and observation. An old article fetched today cannot enter yesterday's decision. BLS entries without publication timestamps use zero for that unknown field; observation still controls availability. A schedule does not become a known result when its time passes.

Provider GUIDs/Atom IDs identify revisions before falling back to a URL. Known tracking parameters and fragments are removed when detecting repeated links, while article-identifying parameters remain. One canonical URL counts once. This does not provide semantic deduplication across different story URLs.

Revisions and source polls are immutable. Conflicting polls for one source at one timestamp are rejected atomically. New studies pin and hash source definitions, event revisions and poll records. Interrupted studies retain that snapshot. Exact exports include `market-events.json`; a changed hash is rejected.

Current feeds cannot replace a timestamp-verified historical news archive. The surviving supplied price bundles lack that archive. This collection starts prospective observation history; it cannot explain multiyear prices using information the system did not have. Imported timestamps are structurally validated, not independently certified. The snapshot limit remains 500,000 combined event versions and polls; larger collections require a storage/indexing extension.

## Measured verification

The 20 September 2026 UTC adapter check recorded **1,163 versions**, with **13 of 14 sources available**. Coinbase status timed out and exchange-topic coverage was zero. All seven added adapters loaded successfully. These are local observations; the deployed host must report its own health.

The supplied XRP 15-minute archive has **105,062 candles**. Every new event was first observed after its test period, so the replay correctly reports **zero historical coverage**. Primary results remain six trades, **−$12.749657 net**, $4.562520 fees and no qualification. The higher-cost primary account selects zero trades. Original weights, calibration and forecast-audit values match V11.11; all 15 event coefficients remain zero. Only old descriptive scope strings are excluded from forecast-audit equality. The frozen diagnostic still has three trades and +$8.329271; it is not promoted.

This verifies timing and reproducibility, not improved profitability. See [the replay](research_baselines/observed-news-replay.json), [verification](VERIFICATION.md) and [review record](research_baselines/observed-news-review.json). Artificial tests exercise world/project coefficient updates after resolved outcomes; they are software checks, not market-performance evidence.

Reproduce the current-news/old-price check with `scripts/check_event_replay.py`, the unchanged bundle, recorded event archive and earlier `compare_eligible_learning.py` result. To replay an exported event/candle bundle:

```bash
python run_research.py --learning --csv candles.csv --daily-csv daily-candles.csv \
  --events-json market-events.json --symbol XRP-USD --interval 15m --out event-study.json
```

Use the original fee/slippage settings and add `--bitcoin-csv bitcoin-daily-candles.csv` if that study used Bitcoin context. No external candles or trading-performance improvement are claimed in this follow-up. The unavailable newer `learning-results 9(1).json` and `AVAX-USD_5m_learning-data.zip` have not been analyzed.

## Sources and remaining research

Official references are the [Fed RSS directory](https://www.federalreserve.gov/feeds/feeds.htm), [SEC RSS directory](https://www.sec.gov/about/rss-feeds), [BLS calendar](https://www.bls.gov/schedule/news_release/) and [FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm). Reporting comes from [BBC World RSS](https://feeds.bbci.co.uk/news/world/rss.xml) and [CoinDesk RSS](https://www.coindesk.com/arc/outboundfeeds/rss); incidents come from [Coinbase status](https://status.coinbase.com/).

Project provenance is the [Ethereum Foundation blog](https://blog.ethereum.org/) and maintainer release histories for [Bitcoin Core](https://github.com/bitcoin/bitcoin/releases), [AvalancheGo](https://github.com/ava-labs/avalanchego/releases), [Polkadot SDK](https://github.com/paritytech/polkadot-sdk/releases), [XRPL rippled](https://github.com/XRPLF/rippled/releases) and [Solana Agave](https://github.com/anza-xyz/agave/releases).

Economic surprise inputs need release-time actual values and expectations known beforehand. [FRED/ALFRED documentation](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) explains historical vintages; date-level vintages alone do not establish intraday availability. That numerical adapter remains unimplemented. Verified activation/unlock calendars, wider regulatory coverage, article interpretation, source corroboration and a forward price-only shadow account are separate tasks. The existing historical control is not a live shadow account.

[The screenshot concept review](NEWS_AND_CONCEPT_REVIEW.md) distinguishes repaired structure helpers from concepts still outside the adaptive training vector. Full original course videos were not verified. Engine `market-structure-v11.13-observed-news`, policy `online-net-r-v17-observed-news`, report 19. Profitability remains unproven.
