# V12.1 stock backtesting and responsiveness verification

Date: 23 September 2026 UTC. Baseline: main commit
`f004c02b634988c955edb0e5afed48df8ce2bd51` (V12).

## Local performance measurement

A generated, completed stock-learning report was copied into 100 saved job rows
in a temporary database. Each summary contained 85,114 bytes. Both versions
called `StockService.overview()` and JSON serialization 12 times against that
same fixture construction. No real account files or market downloads were used.

| Measurement | V12 baseline | V12.1 |
| --- | ---: | ---: |
| Median overview processing | 115.314 ms | 1.599 ms |
| Maximum of 12 calls, including first call | 232.678 ms | 111.451 ms |
| Serialized overview response | 10,732 bytes | 10,732 bytes |
| Saved learning jobs in database | 100 | 100 |

The median dropped about 98.6%, or 72× for this local workload. Previously,
Python decoded all 100 summaries/models before discarding most of them. The new
query reads only eight metadata rows for the dashboard. Response contents remain
small in both versions; this is a server-work reduction, not a claim that every
hosted page is 72× faster. Calendar initialization affects the first call.

Additional changes:

- Learner status reads metadata without report/model JSON. Opening one result
  fetches its saved summary; full exports retain the model and source data.
- Strategy status retrieves summaries in one query instead of opening each job.
- Routine forward-account status excludes trade arrays before Python decoding;
  journal exports retain all trades.
- Scripts/styles are served from memory with content-versioned URLs and ETags.
  Versioned assets are publicly cacheable; private API responses and HTML remain
  `no-store`. Gzip is negotiated for eligible text/JSON responses.
- Polls run after completion, every 30 seconds when idle or eight seconds when
  active. Hidden tabs pause. Requests time out after 20 seconds, or 60 seconds
  for report/download operations. Unchanged results are not rebuilt.
- Learning tables and backtest journals load on demand. Journal previews are
  limited to the latest 100 exits with a scrollable table; exports are complete.
  External chart frames use lazy loading.

## Verification

The full Python regression suite passed: **530 tests in 141.822 seconds**.
After the final HTTP/CLI refinements, the affected stock performance, stock-only
routing and strategy modules passed again: **50 tests**.

```sh
python3 -m unittest discover -s tests
python3 -m unittest tests.test_stock_performance tests.test_stock_only_app tests.test_strategy_lab
node tests/check_equity_browser.js
node tests/check_strategy_lab_browser.js
node tests/check_stock_dashboard_browser.js
```

Browser checks passed: **27 total** (8 learner, 10 backtesting, 9 dashboard).
They use local generated fixtures and block/replace external chart requests.
No fixture result is presented as market performance. Checks cover:

- Authentication, existing login migration, stock presets and supported intervals.
- Lazy learning results, full exports, source candles and forward-account stop.
- Backtest configuration, persisted queue, cancellation and mode restrictions.
- Completed, incomplete and legacy report rendering; unavailable P/L stays unknown.
- Journal loading across a concurrent status refresh, window selection and full export.
- Request timeout and recovery, unavailable services and inert hostile text.
- Dashboard account marks, research links, desktop and 390-pixel phone layouts.

Backend regressions additionally verify compact reads even with an unreadable
saved report; full-model/journal preservation; authenticated report routes;
static cache validation and gzip roundtrips; invalid settings rejected before
queueing; frozen common cutoffs; actual report/journal P/L reconciliation; and
missing required context blocking entries.

Report version 3 records the new settings, source coverage, window timestamps,
metrics and all three trade journals. Earlier named-strategy reports remain
saved but require a fresh run for eligibility. Stock execution remains long-only,
unleveraged and simulated. The release does not establish profitable trading.

## Deployment limits

Public probes of the existing Render site's home page, health, strategy page and
stock overview timed out from this workspace (roughly 22–24 seconds). No current
host CPU, memory, worker logs or deployed version could be verified from those
probes. This does not prove a hosting outage or establish the cause of every
observed delay. Local tests do not verify provider entitlements or new live-market
backtest results.

The same GitHub repository and Render service are retained. Automatic deployment
is disabled in the repository configuration. After merging, deploy the latest
commit on the existing service and verify `/api/health` reports `app_version`
`12.1`. Then check `/backtests` with the existing app token. No hosting plan, disk,
service identity or broker-order capability is changed by this release.
