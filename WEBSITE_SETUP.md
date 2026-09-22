# Deploy Stock Lab V12 to the existing Render service

Repository: **Joehidera18/Learning-algorithm**. Website:
https://learning-algorithm-wah5.onrender.com.

## Update the existing service

1. Merge the V12 change to the branch Render deploys, normally `main`.
2. In the existing Render service, use **Manual Deploy → Deploy latest commit**.
   The repository configuration keeps automatic deployments off.
3. Wait for the deploy to finish, then refresh the home page. It should show
   **Stock Lab**. `/api/health` must report `app_version: 12.0`,
   `asset_class: equity`, `crypto_enabled: false`, and `live_capable: false`.
4. Use the same `APP_ACCESS_TOKEN` to open saved stock results and controls.

Keep the existing service, disk and URL. Legacy names in `render.yaml` are
resource identifiers retained to avoid creating replacement infrastructure.
This migration does not change the paid plan or disk size. The web process starts
only the stock learner and named-strategy queue. It never connects a Coinbase
trader, even if old Coinbase environment variables remain configured.

## Server configuration

| Setting | Purpose |
| --- | --- |
| `APP_ACCESS_TOKEN` | Protect account, queue and research API access |
| `RESEARCH_DATA_DIR` | Existing persistent data root, normally `/var/data/research-data` |
| `RESEARCH_DB_PATH` | Preserve the original journal path; the stock app does not open it |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Optional Alpaca stock data credentials; `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` also supported |
| `MASSIVE_API_KEY` | Optional Massive stock candles and news |

Yahoo historical data requires no key. Configured credentials do not prove a
subscription permits a particular feed or historical window. Provider errors are
shown in the run that requested them. Do not place provider secrets in browser
fields, source code or GitHub.

Build: `pip install -r requirements.txt`

Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 300`

Use the repository's Python 3.12 configuration. Keep one worker and instance for
the persistent local queues. The stock learner and named-strategy jobs share one
compute slot. The existing small server may still need shorter requests; this
release does not claim that every allowed window fits in its memory.

## Saved state and restarts

- `RESEARCH_DATA_DIR/equity-practice/`: stock queue, frozen candles, forward
  account journals and snapshots.
- `RESEARCH_DATA_DIR/strategy-lab/`: named-strategy queue and reports.
- Older crypto database and candle directories: untouched, with no active web
  workflow. Keep existing backups if they are needed for your records.

The app resumes queued stock learning and registered stock accounts from their
saved files. A source change causes old learner jobs/registrations to require a
new run, rather than silently changing their model. Interrupted Strategy Lab
jobs become errors; new runs get a frozen cutoff shared by all requested frames.
Existing completed reports remain available. No migration starts a new funded
trade or modifies a broker account.

Quotes on the site are independent
[TradingView displays](https://www.tradingview.com/widget-docs/widgets/charts/symbol-overview/).
Check their [data availability and delays](https://www.tradingview.com/widget-docs/faq/data/).
The learner uses recorded regular-session candles with a minimum 20-minute
cutoff delay. There is no real-money stock execution connector in V12.

## Troubleshooting

- Old crypto home page: inspect the deployed commit and `/api/health`; a GitHub
  merge does not itself establish that Render has deployed it.
- Token prompt: use the service's `APP_ACCESS_TOKEN`, not a provider API key.
- Empty historical run: read its provider message, timeframe limit and coverage.
- Interrupted or source-changed run: submit a new stock run; retain the old
  export for comparison.
- Blank chart: reload the display or follow its TradingView link. The chart
  provider cannot read the app token and its chart is not used for paper fills.
- Missing history after restart: confirm the entire data directory is under the
  existing persistent disk mount.
