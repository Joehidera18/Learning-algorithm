# Software verification

Verified locally on September 29, 2026, using Python 3.12.14 and the repository
requirements. Software checks do not establish investment performance.

- Full Python suite (`python -m unittest discover -s tests`): **613 tests passed**
  in 147.102 seconds, including 13 new candidate regressions.
- Browser suite (`node tests/check_strategy_lab_browser.js`): **12 checks passed**
  using Playwright and bundled Chromium against local fixture data. Includes
  exact rules/source display, timeframe restrictions, protected submissions,
  stale/incomplete reports, research-only results despite a positive eligibility
  flag, entry-rejection explanations, exports, cancellation and request recovery.
- Mobile layout at 390 × 844: no horizontal page overflow; the VWAP candidate's
  full rules and source link were displayed and the screenshot inspected.
- All 12 frozen historical combinations completed. Their metrics and journals
  are retained in `outputs/`; no parameter sweep was performed.
- The recorded Python execution-code hashes, plan hash and runner hash match
  the files used for the study. `git diff --check` passed.

The new Python regressions check prior-only relative-volume baselines, missing
bars and missing whole sessions, invariance to future data, session resets,
single-signal behavior, retest expiration, VWAP reclaim requirements, actual
next-open execution with costs, and research-only eligibility. Generated
fixtures verify behavior; their returns are not market evidence.

To replay the browser checks, install Playwright's Chromium as usual, or provide
`@sparticuz/chromium` and set `STOCK_UI_BUNDLED_CHROMIUM=1`. Set `STOCK_UI_PYTHON`
to the Python environment containing the project's requirements if necessary.
The test server disables market-data and brokerage credentials.

Validation was local. No Render deployment or brokerage order was performed.
