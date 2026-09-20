# Crypto + Stocks research

The existing crypto dashboard links to **Stock research** at `/stocks`. This
edition brings the September 20, 2026 research into the same GitHub/Render app:
20 complete company profiles, the five growth priorities, theme and business
profile filters, browser-saved favorites, source links, a catalyst calendar,
valuation comparisons, and authenticated report/watchlist downloads.
The five names from the earlier screenshot (TWST, XYL, TXG, TMO, SDGR) are also
retained as follow-up candidates, clearly marked as needing updated research.

The five priorities are VRTX, AVGO, ALNY, VRT, and BEAM. Priority is an editorial
research ranking, not a profit probability. Market figures refer to September 18,
2026; quote links open the external source for current information. Reload fetches
the edition packaged with the app, not new news or live prices.

## Data and updates

- `research/stock_watchlist.json` contains the structured research and sources.
- `research/stock-watchlist-2026-09-20.md` preserves the full report.
- `lab/stock_research.py` adds server-date review status to a copy of the edition.
- `templates/stocks.html` and `static/stocks.{js,css}` render the section.

To publish a research update, verify source documents and replace the relevant
theses, financial snapshots, and catalyst information. Advance the research date
and edition only when that review actually occurs; update the report and structured
catalog together. `EDITION` in `lab/stock_research.py` must match the JSON edition;
the health endpoint uses that constant. Dates passing never mark a trial, approval, or delivery as
successful. The UI flags elapsed catalyst windows and research older than 30 days.

`GET /api/stocks/research` provides the catalog; append `/VRTX` for one profile,
`/export` for JSON, or `/report` for Markdown. Existing `APP_ACCESS_TOKEN` protection
covers all four. The browser reuses the crypto dashboard's session token. Favorites
contain only tickers, are stored in localStorage, and fall back to memory when
storage is blocked. There is no broker connection or equities order route.

## Verification and deployment

Run `python3 -m unittest discover -s tests`, then the existing Node UI checks in
`tests/check_learning_ui.js` and `tests/check_finances_ui.js`. The stock browser
checks use Playwright with an isolated local test service; see
`tests/check_stocks_browser.js`. No live credentials or account state are needed.
With Playwright and Chromium installed, run `node tests/check_stocks_browser.js`.
An optional `STOCK_UI_BUNDLED_CHROMIUM=1` uses an installed
`@sparticuz/chromium` package instead of Playwright's browser download.

This edition passed 417 Python tests, both existing dashboard JavaScript checks,
and 11 browser scenarios, including desktop/mobile layout, token access, combined
filters, saved-list persistence, company deep links, exports, failed reloads,
elapsed catalyst dates, escaped content, blocked browser storage, and navigation
back to the crypto dashboard. No stock trades or performance tests were run.

This is an addition to `Joehidera18/Learning-algorithm`, deployed at
`https://learning-algorithm-wah5.onrender.com`. The checked-in Render blueprint
has automatic deployments disabled. After deploying the intended commit, verify
`/api/health` reports the stock research version and `/stocks` loads the edition.
Preserve persistent storage. An active registered forward study pins all Python
source in `lab/`; finish/export that study before deploying changed Python source.
This update does not modify that pinning or the crypto trading rules.
