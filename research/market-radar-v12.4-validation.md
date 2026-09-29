# Market Radar V12.4 validation

Local verification completed September 29, 2026 UTC against the existing stock
application. Baseline remote main was
`8eee9a74e8870e938f1bf98a8ea65c9a1dcf2cdf` (V12.3). These checks establish
software behavior, not trading returns or live production performance.

## Automated checks

- Full Python suite: **595 tests passed** before the final feed-address and
  same-headline incident-body refinement.
- After that refinement: **80 affected Python tests passed**, covering Market
  Radar, crypto watch, stock service and AI agent. This includes 23 radar tests.
- Market Radar browser suite: **8 checks passed** using generated evidence,
  actual local HTTP routes and desktop / 390-pixel phone layouts.
- Existing AI agent browser suite: **13 checks passed**.
- Existing stock dashboard browser suite: **9 checks passed**.

The focused checks cover first-fetch baselines, duplicate and timestamp-only
updates, changed incident descriptions, unsafe links/XML, invalid publication
dates, bad-news topics, coverage failures, stop-during-download behavior, restart
preferences, persisted sale tags, calendar edits/cancellation/conflicts, API
authentication, exports and bounded agent evidence. Quote fixtures exercise
weekends, stale/future timestamps, wrong prior sessions, invalid prices and
same-session comparisons. No live orders or paid AI requests were made.

Browser checks cover token access, start/stop, visible source failures, hidden
reprints with a review toggle, safe rendering, saved notes, dated calendar
entries and revisions, asset filtering, AI draft handoff without submission,
exports and navigation. Desktop and phone screenshots were visually reviewed;
the phone page has no horizontal overflow.

The compact radar response is under 2 KB in the integration fixture, and the
combined overview stays under 20 KB. A deliberately blocked feed request does
not make a local status call wait for the network. These are local bounds,
not promises about production latency or all database sizes.

## Live public-source checks

Read-only requests used the actual adapters, the 8-second timeout and the 1 MB
limit. Sources were checked sequentially across the release work, not at one
shared market instant.

| Source | Observed result |
| --- | --- |
| Hedera announcements | Parsed successfully; 6 matching entries |
| Hedera status | Parsed 7 matching entries; 2 entries rejected by timestamp/link validation |
| Intellia investor releases | Parsed successfully; 4 matching entries |
| CRISPR investor releases | Parsed successfully; 1 matching entry |
| Yahoo stock feed | Original endpoint redirected; reviewed and configured its canonical feed endpoint. One timeout, then 12 matching entries with no rejected entries |
| CoinDesk | Parsed successfully; 13 matching entries |
| Federal Reserve monetary policy | Parsed successfully; 2 matching entries |
| Coinbase status | Advertised Atom/RSS endpoints timed out or returned a small HTML error page; rejected and shown as unavailable |

Seven sources produced usable data during the check; the eighth remains a
visible coverage problem. These counts reflect the feed contents and date
filters at that check, not comprehensive coverage. Provider availability may
differ on Render. The UI does not turn an unavailable feed into an all-clear.

The HBAR upgrade and NTLA FDA target starter entries were checked against the
primary links in [MARKET_RADAR.md](../MARKET_RADAR.md). Sources are dated and
must be rechecked for changes. No fresh top-stock ranking was inferred from
these calendar entries.

## What remains unverified

No authenticated production app token or live Alpaca data credentials were
available. Therefore this work does not verify the user's saved watch enablement,
Alpaca subscription, live quotes, OpenAI billing/model access, or production
delivery after deployment. The app's public health endpoint was V12.3 during
review. A GitHub PR does not change the deployed Render version by itself.

After merging and manually deploying, confirm V12.4 in `/api/health`, open
Market Radar, start the desired watches, check source health, and verify a
stock quote's source and timestamp if Alpaca keys are configured. News works
without those keys. Website notifications remain in-app. No forecasting
accuracy, improved profitability, price causation or guaranteed event detection
was measured.
