# Start with Stock Lab V12

Open the same website: https://learning-algorithm-wah5.onrender.com after deploying
V12 from the existing GitHub repository. The home page should say **Stock Lab**
and the health endpoint should report `app_version: 12.0`, `asset_class: equity`
and `crypto_enabled: false`.

1. Enter your existing app access token if prompted. A saved browser session is
   carried forward from the earlier app.
2. On **Dashboard**, choose a stock or ETF. The chart shows provider quotes and
   changes; check its timestamp and delay.
3. Select **Train this stock**. Choose day or swing practice, a timeframe, source,
   available history length, and your cost/risk assumptions. Select **Train &
   compare**. Download failures remain visible and can be retried.
4. Read the later-period results, higher-cost comparison, trade counts and candle
   coverage. Learning examples can overlap and are not account trades.
5. For ongoing simulation, choose **Start forward practice** on a completed run.
   It only considers signals formed after registration. Return to **Dashboard**
   to inspect the paper account, or export its full journal.
6. Use **Strategy lab** to test a named rule separately. Queued/running tests can
   be cancelled. A promising backtest does not automatically place orders.
7. Use **Markets & research** for the 20-company watchlist and dated source notes.

Historical prices and paper fills are delayed. Closed-market intervals follow
the exchange calendar rather than being counted as missing prices. Provider
retention and account subscriptions limit how far intraday history can go.

Your earlier crypto data has not been deleted. Crypto processing and controls
are retired from the running app. Stock runs remain saved, although a learner
from an older source version needs a fresh run before new forward registration.
Real-money brokerage execution is not connected.
