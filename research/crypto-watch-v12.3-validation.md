# Crypto watch validation · September 28, 2026

Repository: Joehidera18/Learning-algorithm. Based on main
`e2e37b53490c11b725f6345ef380b6070aded73b` (merged AI agent update).

## Verified behavior

- The complete Python suite passed: **572 tests**. After adding rolling-restart
  recovery and request pacing, the final affected-module suite passed **66
  tests**, including **19 crypto-watch tests**. There are now 573 discovered
  Python tests in total; the full suite was not repeated after those small edits.
- Browser checks passed: **7 crypto watch, 13 research agent, 9 stock dashboard**.
  These use a real local HTTP app with generated candle/news/AI fixtures and no
  external provider calls. Phone and desktop screenshots were visually reviewed.
- Open/future bars cannot create signals. Event bars do not set their own
  resistance or volume baselines. Missing/stale candles, invalid prices,
  conflicting duplicates, missing BTC comparisons and thin venue liquidity block
  qualifying signals. A large existing move receives the extended warning.
- Observation time is distinct from candle time and news publication time.
  Identical news revisions preserve their first-seen timestamp. New revisions
  receive a new observation timestamp. Initial/gap snapshots are labeled.
- A stopped worker cannot save signals from an in-flight response. Repeated
  starts do not create duplicate workers; an OS lease prevents duplicate scans
  across processes. A restarting worker waits for the old lease to clear.
- Routes require the app token when configured; start/stop are unavailable
  without a configured token. Export and agent handoff work without automatically
  submitting paid AI research. The existing stock order boundary stays disabled
  for real money and crypto.
- Static JavaScript syntax, Python compilation and `git diff --check` passed.

## Responsiveness

Generated populated workspace: 14,041 JSON bytes, with 12 asset states and three
alert observations. Forty local reads measured a median 1.73 ms and maximum
4.17 ms for overview plus JSON serialization. This is a local fixture benchmark,
not a hosted latency guarantee. Provider requests occur on the watch worker,
never in page/status request handlers.

The browser regression exposed a brief UI race: the agent's credential warning
could appear before the submit button updated while a saved thread loaded. The
button now updates immediately after status retrieval. A delayed-thread browser
check verifies that missing credentials disable submission immediately.

## Not verified

Coinbase and Kraken public candle requests timed out here. There is **no real
HBAR replay, historical hit rate or demonstrated profit improvement**. The
fixture breakout at a generated price is not market data. No paid OpenAI request
or production deployment was made during these checks. Render should be checked
after deployment for version 12.3, feed availability, actual closed candle times
and a completed first scan. Documentation: [CRYPTO_WATCH.md](../CRYPTO_WATCH.md).
