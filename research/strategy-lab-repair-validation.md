# Strategy Lab repair validation — 22 September 2026 UTC

Reviewed base: `361500f6872bb3942a5eb8dba29734c927b8831c`.

## Repairs

- Route Strategy Lab APIs through the existing access-token and JSON validation.
- Restore valid JavaScript and HTML escaping on Stock Practice and Strategy Lab.
- Repair the strategy registry import and make the strategy tests discoverable.
- Require complete standard and cost-stressed account tests before eligibility.
  Missing candles during an open position produce unknown account P/L. Count
  normally resolved trades separately while including end marks in account P/L.
- Reject incomplete opening ranges, use 20 complete prior observed ranges for
  relative volume, and restrict ORB decisions to 1m/5m/15m candles.
- Reset indicators after decision gaps and reject stale context after an
  expected candle is missing. Preserve valid context through exchange closures.
- Build Massive 1h/4h bars from complete 30-minute observations, including early
  closes. Accept identical overlap at snapped download boundaries and reject
  conflicting observations.
- Mark previous lab results for a rerun; retain their stored records while
  suppressing the old eligibility flag in API responses and the website.

## Verification

- Full Python regression run: **506 passed** in 142 seconds.
- One additional end-to-end queue/report regression was then added. All **27
  Strategy Lab tests** passed, covering those 26 earlier tests plus this new
  test: **507 distinct passing Python tests** in the final source tree.
- **8 Stock Practice browser checks passed**: authentication, data-source
  limits, queuing, downloads, forward-paper controls, desktop/phone layouts,
  and hostile text escaping.
- **7 Strategy Lab browser checks passed**: authentication, strategy loading,
  incomplete/legacy report display, supported intervals, queued submission,
  text escaping, unavailable-service errors, and phone layout.
- Python compilation, JavaScript syntax, `git diff --check`, and application
  startup with a temporary database passed. The actual application returned
  401 for an unauthenticated lab catalog and 200 with the test token.

Tests use generated candles, isolated temporary accounts and mocked provider
responses. Massive alignment was checked against the provider's documented
bar grid, regular sessions, early closes, missing half-hours, and chunk overlaps.
No live Massive subscription was exercised and no funded orders were submitted.
These are correctness checks, not evidence of profitable market performance.

## Reproduce

```sh
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q app.py lab strategies news tests
node --check static/stock-practice.js
node --check static/strategy-lab.js
node tests/check_equity_browser.js
node tests/check_strategy_lab_browser.js
```

Install the repository's Python requirements and Playwright/Chromium before
running the checks. The browser scripts can also use `@sparticuz/chromium` with
`STOCK_UI_BUNDLED_CHROMIUM=1`.
