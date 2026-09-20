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

## Updating market displays

**Markets & charts** shows a 20-symbol TradingView market board plus a company
selector with a price/volume chart and dollar/percentage changes. The compact
**Prices & %** view fits phones; **Full quote table** adds absolute change, open,
high, low, and previous close, with sideways scrolling for narrow screens. Each research
profile has **View price & chart**, and the chart links back to its research.
`?tvwidgetsymbol=NYSE:IONQ#marketChartArea` selects a chart on arrival; only symbols
in the research catalog are accepted. **Reload market displays** reconnects the
two frames without reloading the page or resetting the research filters.

Stock quotes can be delayed. The provider's quote timestamp, feed-delay, and
market-status indicators remain visible; the app never invents a market-open
status from weekday/hour calculations. An offline message warns that quotes can
be stale. Loading a frame is not evidence that quotes are current. If a feed or
symbol is unavailable, the provider's message and external chart links remain the
fallback; dated report numbers are never substituted into the market display.

The app embeds the cross-origin frame URLs produced by TradingView's official
widget loaders, using the catalog's `market_symbol` values. It retains provider
branding and attribution. Provider JavaScript runs inside its own origin, without
access to this app's session token or saved stocks. Two frames are mounted, rather
than one feed per research card. Research reloads preserve an existing chart.
No API key, paid data subscription, or server-side quote polling is introduced.

The research API's `live_quotes: false` means the **JSON response is not a quote
feed**. `market_display` describes the separate embedded display. JSON/report
downloads and valuation comparisons retain their explicit research dates; market
data is neither harvested from the frames nor exported as research data.

Provider references, checked September 20, 2026:

- [Market Overview widget](https://www.tradingview.com/widget-docs/widgets/watchlists/market-overview/)
- [Market Data widget](https://www.tradingview.com/widget-docs/widgets/watchlists/market-data/)
- [Symbol Overview widget](https://www.tradingview.com/widget-docs/widgets/charts/symbol-overview/)
- [Data delay and availability FAQ](https://www.tradingview.com/widget-docs/faq/data/)
- [Official embedding tutorial](https://www.tradingview.com/widget-docs/tutorials/iframe/build-page/widget-integration/)

The official loaders used to verify the frame configuration are
`https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js`,
`https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js`, and
`https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js`.
The stock-display update passed seven focused Python tests and 14 browser
scenarios. Browser regression checks use a clearly labelled provider fixture for
deterministic integration checks. A separate provider check received real prices
and percentage changes for all 20 stocks, each marked delayed by TradingView.

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
