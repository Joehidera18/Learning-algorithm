# Start with Stock Lab V12.1

Open the same website: https://learning-algorithm-wah5.onrender.com after deploying
V12.1 from the existing GitHub repository. The home page should say **Stock Lab**
and the health endpoint should report `app_version: 12.1`, `asset_class: equity`
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
6. Select **Backtest stocks** on the dashboard or navigation. Choose a ticker,
   strategy, timeframe, day/swing style and paper balance. Open the optional
   controls for a historical end date and trading costs. Select **Run stock
   backtest** and follow its saved progress. Compare the later and higher-cost
   columns, then open **View trade journal** or **Export full backtest**.
   Queued/running tests can be cancelled. A positive test never places orders.
7. Use **Markets & research** for the 20-company watchlist and dated source notes.

Historical prices and paper fills are delayed. Closed-market intervals follow
the exchange calendar rather than being counted as missing prices. Provider
retention and account subscriptions limit how far intraday history can go.

Your earlier crypto data has not been deleted. Crypto processing and controls
are retired from the running app. Stock runs remain saved, although a learner
from an older source version needs a fresh run before new forward registration.
Real-money brokerage execution is not connected.

Named-strategy reports from before V12.1 remain saved but require a fresh run to
verify them under report version 3. The old `/strategy-lab` address still works.
