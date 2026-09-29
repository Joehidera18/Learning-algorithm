# Market Radar — Stock Lab V12.4

Market Radar adds news, a catalyst calendar and watch notes to the existing
research website. It complements the stock learner, named backtests, AI agent
and crypto candle watch. It is an evidence journal, not a return forecast.

## Start on the existing website

1. Merge this update and manually deploy the latest commit to the existing
   Render service. Confirm `/api/health` reports `app_version: 12.4` and
   `market_radar_available: true`.
2. Open `/market-radar` with the same app access token. Click **Start news &
   stock watch**. Public news needs no OpenAI or market-data key.
3. For stock observations, configure `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
   privately in Render, then redeploy. `APCA_API_KEY_ID` and
   `APCA_API_SECRET_KEY` are also accepted. `RADAR_STOCK_FEED=iex` is the default;
   `sip` needs the appropriate subscription. Do not put provider keys in the app
   token field.
4. Start the separate crypto watch if wanted. The page links its status and
   controls; each watch has its own persisted enabled setting.
5. Inspect **Source health & coverage**. Errors, rejected entries and stale
   fetches remain visible. A green fetch is not proof that every story was found.

Both background watches resume after normal restarts if previously enabled.
Stopping a watch preserves its saved evidence and disables its future resume.
News downloads do not run inside status/page requests. The existing single
Render worker, persistent disk and hosting plan are unchanged.

## Assets and personal notes

The watch contains VRTX, ALNY, AVGO, GOOGL, TSM, ETN, NVDA, ARGX, CEG, INSM,
VRT, IBM, BEAM, CRSP, ASML, KEYS, ANET, RBRK, VKTX, IONQ and NTLA; and BTC,
HBAR, ETH, SOL, XRP, XLM, LINK, ADA, DOGE, AVAX, LTC and BCH, as USD pairs.

Every asset stays in coverage when tagged **Watching**, **Holding** or
**Recently sold**. HBAR initially carries the recently-sold tag based on the
owner's stated sale. Tags do not assert broker positions, balances or returns.
Each asset has a saved thesis note, including reasons to reconsider or evidence
that would invalidate the idea. These notes are readable by the AI research
agent; they do not automatically retrain a strategy or change paper positions.

## Sources and discovery times

The enabled worker checks these fixed public endpoints about every five minutes:

| Source | Role / limitation |
| --- | --- |
| [Hedera announcements](https://hedera.com/feed/) | Primary HBAR announcements; not every ecosystem partner's releases |
| [Hedera status](https://status.hedera.com/history.atom) | Primary maintenance and incident updates |
| [Intellia investor news](https://ir.intelliatx.com/rss/news-releases.xml) | Primary NTLA releases |
| [CRISPR investor news](https://ir.crisprtx.com/rss/news-releases.xml) | Primary CRSP releases |
| [Yahoo Finance feeds](https://feeds.finance.yahoo.com/rss/2.0/headline?s=VRTX,ALNY,AVGO,GOOGL,TSM,ETN,NVDA,ARGX,CEG,INSM,VRT,IBM,BEAM,CRSP,ASML,KEYS,ANET,RBRK,VKTX,IONQ,NTLA&region=US&lang=en-US) | Aggregated reporting for the stock list; bounded recent items, not exhaustive coverage |
| [CoinDesk](https://www.coindesk.com/arc/outboundfeeds/rss) | Crypto reporting; title matching can miss developments |
| [Federal Reserve](https://www.federalreserve.gov/feeds/press_monetary.xml) | Primary monetary-policy context |
| [Coinbase status](https://status.coinbase.com/history.rss) | Exchange incidents; returned unusable HTML in the release check |

Company names and unambiguous ticker references select relevant headlines.
Ambiguous words such as LINK and BEAM alone do not establish asset relevance.
Status and Fed notices are operational or broad-market context. Categories
include safety/regulation, security, financing/supply and commercial developments;
they are keyword topics, not sentiment, importance or buy scores. Sponsored,
presale and price-prediction headlines are filtered heuristically, not perfectly.

Each saved revision separates original publication, publisher update and app
discovery times. The initial fetch establishes a baseline and creates no news
alerts. Discovery more than two hours after the publisher update is marked late.
Outages preserve old records and label subsequently found evidence as following
a coverage gap. Missing, future or inconsistent timestamps are rejected rather
than made up. The app cannot reconstruct when an earlier installation saw news.

Fresh, non-general topics create in-app journal entries after the baseline,
subject to deduplication and the source's last successful fetch. Equal normalized
headlines at different URLs are possible reprints, not independent confirmation.
Same-URL revisions hash the feed-supplied body as well as the title, so a changed
incident description is preserved even when its headline stays the same.
Timestamp-only updates with unchanged feed text do not create fresh alerts.
Full articles are not fetched, and the body text is not displayed or archived.
Body changes without a recent publisher update remain evidence, not a claimed
freshly published alert. The default view hides possible reprints and timestamp
updates; the checkbox shows them again.

This is partial public-feed coverage, not a complete SEC, FDA, exchange or
company news service. Source links need human or AI verification of economic
terms, clinical context and opposing evidence. In particular, a partnership
does not establish revenue or token demand just because its headline is positive.

## Catalyst calendar

Record a source link, asset, date, optional UTC time, status and note. Dates are
scheduled or management/regulatory targets; completed and cancelled states are
separate. Date-only entries have day precision, not an invented exact time.
The worker records an approaching event once per saved revision in the next
72 hours. It does not automatically discover or verify all future milestones.

Two starter entries were checked on September 29, 2026 UTC:

- [HBAR mainnet v0.77.2](https://status.hedera.com/incidents/hhd6nw87yrv5):
  September 29 at 17:00 UTC; the September 24 notice expected about 40 minutes
  and service disruption. Check the live status for changes and completion.
- [NTLA lonvo-z](https://www.sec.gov/Archives/edgar/data/1652130/000119312526385194/ntla-ex99_1.htm):
  the September 8 company release reports a March 10, 2027 FDA target action
  date following priority review. This is not approval or an investment-return
  prediction.

Saving a calendar link does not fetch it or certify it. User edits carry a
source-review warning. Conflicting edits require a reload, and the database
retains before/after revisions. Cancelled, changed or past events do not leave
old alerts looking current. Starter sources older than 30 days get a review
warning. Notes and calendar state persist on the existing disk.

## Stock observations and AI research

Optional Alpaca snapshots cover the 21 stocks during regular US sessions,
including exchange holidays and early closes. Quotes must be within ten minutes,
not future-dated, and inside the current session. The prior close must be from
the preceding trading session. See Alpaca's [snapshot reference](https://docs.alpaca.markets/us/reference/stocksnapshots-1)
and [feed coverage](https://docs.alpaca.markets/us/docs/market-data-faq).

- An absolute change of at least 5% from the raw prior close is a **large move
  already observed**.
- An absolute change of at least 2% between two fresh, increasing quote times
  in the same session and feed is a **momentum change**. This is a comparison
  between observations, not a guaranteed exact five-minute return.
- One journal entry is retained per asset, direction, stage and session.
  Initial/gapped observations cannot claim early detection. Stale or unavailable
  data suppresses new price signals. No volume confirmation is inferred.

IEX is a single venue; SIP requires entitlement. Unadjusted closes mean splits
or dividends can cause apparent changes. Snapshots are not a tick stream and
do not provide the paper engine's fill prices. Public crypto candle observations
retain their separate documented rules in [CRYPTO_WATCH.md](CRYPTO_WATCH.md).

**Investigate with AI** opens a draft for the selected asset (HBAR if none is
selected). It asks the existing agent to read the journal, verify primary
sources, explain economics and look for disconfirming evidence. It does not
submit automatically, spend credits, change the calendar or place a trade.
Submitting uses the existing OpenAI configuration and limits. Stock backtests
remain separately authorized through the existing agent/page controls.

## Persistence, routes and limits

State lives in `RESEARCH_DATA_DIR/market-radar.sqlite3`. The active scan retains
up to 90 days / 5,000 news revisions and 90 days / 2,000 journal entries. The
page/API snapshot and export include the latest 50 matching news items, 50
alerts and 50 calendar edits; the UI shows smaller lists. Calendar entries are
capped at 200. Tracking notes and saved calendar state are not age-pruned.
The snapshot is not a full database backup or a point-in-time market dataset.

All `/api/market-radar/*` routes use the existing app authentication. GET `status`
and `export` accept an optional watchlist `symbol`. POST `start`, `stop`,
`tracking` and `catalyst` require a configured app token. Untrusted calendar URLs
are stored for review but never fetched by the server. Fixed source fetches
reject redirects and entity declarations and have 8-second / 1 MB limits.

Website notifications are an **in-app journal only**. Any separately configured
ChatGPT public-news task is independent and cannot read private website notes.
This release adds no phone/email delivery, funded orders, automatic paid AI
research or measured forecasting edge. See [validation](research/market-radar-v12.4-validation.md).
