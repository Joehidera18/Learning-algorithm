# Stock-only V12 migration validation

Date: 2026-09-22. Base: `c2e7fb924e6ace44497a5312f303d024b8c321cd`.

## Result

The deployed entry point now constructs `StockService` and exposes a US stock
research, historical learning and forward paper-trading workspace. It does not
construct crypto workers or a Coinbase trader. Existing crypto files are not
opened or rewritten. Stock persistence directories and the deployment resource
identifiers remain unchanged.

## Checks performed

| Check | Result |
| --- | --- |
| Entire Python suite, including archived research regressions | 521 tests passed in 144.104 seconds |
| Focused stock/provider/strategy/migration suite | 80 tests passed |
| Stock learner browser integration | 8 checks passed |
| Strategy Lab browser integration | 7 checks passed |
| New stock dashboard browser integration | 9 checks passed |
| Dashboard desktop and 390-pixel phone screenshots | Inspected; no horizontal overflow or obscured controls |
| JavaScript syntax and changed Python compilation | Passed |
| Git whitespace/conflict-marker check | Passed |
| Real `app.py` import in an isolated data directory | `StockService`, V12.0, equity, paper, crypto disabled, live capability false |
| Startup with the legacy live-enable environment flag set | No crypto runtime attributes and no legacy journal created |

The new integration tests cover token protection, retired API actions, public
stock-only assets, preservation of the old journal, stock-job and account
persistence, source/ticker validation, queue serialization, cancellation and
interrupted-job recovery. Browser checks cover the old login and saved-favorite
migration, stock-specific form links, stock account controls and export,
incomplete-account values, escaped stored text, request failures and layouts.

Stock learner and strategy tests now share a process-wide computation lock.
The named-strategy worker also owns a filesystem lease; queued input includes a
common closed-candle cutoff for decision and context data. Cancelling a job
cannot be overwritten by a late completion. A server-interrupted running job
is marked as an error and does not masquerade as a completed report.

## Boundaries

These checks use generated or mocked local fixtures. Browser market embeds were
replaced with an explicitly labelled fixture during integration testing. The
checks establish application behavior, not successful current market-data
subscriptions, a new profitable strategy, or real-money broker execution.
TradingView's displayed quote delay/availability remains provider-controlled.

The V12 change alters the research source hash. Existing completed stock reports
are retained, but older learner registrations need a fresh stock run before new
forward practice. This prevents silently changing an existing model.

The Render configuration uses manual deployments. GitHub publication and local
verification do not establish the running Render version; confirm V12.0 and
`crypto_enabled: false` at `/api/health` after deployment.
