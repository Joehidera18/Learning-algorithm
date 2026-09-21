# Stock learning and paper practice — V11.19

Open **Stock practice** (`/stock-practice`) on the existing app. This extends the
shared strategy, online learning, execution and feedback engines to **US-listed
USD stocks and ETFs**. It does not submit stock orders.

## Use it

1. Select one of the 20 researched companies, SPY/QQQ/IWM/DIA/AAPL/MSFT, or type
   another US listing. Begin with one year of hourly history or five years of
   daily history. All requested intraday frames are present: 1m, 4m, 5m, 15m,
   30m, 1h and 4h; daily candles are also available for swing research.
2. Choose **day** (close at each regular session end) or **swing** (carry positions
   overnight, with a 120-hour elapsed-time deadline). Daily bars require swing mode.
3. Review separate stock cost assumptions and fractional/whole-share sizing.
   Choose **Train & compare**. Progress, failures and completed reports are saved.
4. Review coverage, resolved examples, net returns, costs, drawdown and the
   individual trade ledgers. Export results or download the exact input candles.
5. Choose **Start forward practice** on a completed run with learning examples.
   The app registers the time, freezes the seed and follows subsequently completed
   candles. A new signal must close after registration before a later candle can
   fill it. No pre-registration profit is credited to this forward account.

Forward practice is delayed OHLC simulation, not a broker paper account or a live
execution feed. Prices have a minimum 20-minute lag. Account entries use the
model's evidence and cost filters; remaining in cash is a valid outcome. Meanwhile
the same 22 candidate setups collect cost-eligible, independently funded examples
from new prices. They update the learner **only after their exits become known**.
Overlapping examples are never summed as portfolio returns or counted as account
trades. Account feedback is not applied again on top of these examples.

## Market mechanics

- The NYSE regular-session calendar applies to these US NYSE/Nasdaq listings.
  `pandas-market-calendars` supplies holidays, exceptional closures, early closes
  and daylight saving. Extended/overnight sessions are intentionally excluded.
- All intraday bars start from 09:30 America/New_York. Final bars end at the
  actual close: normally a 2-minute final 4m bar, 30-minute final 1h bar and
  150-minute final 4h bar. These shortened observed bars retain their real close
  timestamp; they are not padded or joined to the next session.
- Derived candles require every expected source candle. No interpolation,
  forward filling, synthetic prices or mixing of providers is used.
- Indicator warmup crosses scheduled closures. A genuinely missing scheduled
  candle resets indicator warmup. An open account encountering such a gap becomes
  incomplete instead of receiving invented exits or subsequent returns.
- Daily context uses completed exchange sessions. Session VWAP uses share volume
  and resets at the open. Crypto's UTC-day and Bitcoin context are not imported.
- Signals use closed candles and fill at the next observed open. Existing stops
  crossed by an opening gap fill at that opening price plus adverse slippage.
  Existing targets crossed at the open use the target level conservatively,
  before any later intrabar low/high. Other stop/target ambiguities assume stop first.
- Day mode expires a prior-session entry signal and closes surviving positions at
  the final session candle close, charging costs. This close is a simulation
  assumption, not a guaranteed closing-auction fill. Swing time exits occur at
  the first observed candle close after the deadline, never while the market is shut.
- Fractional quantities round down to six decimals; whole-share mode rounds down
  to integers at the historical share basis. Future split factors convert those
  quantities back into the adjusted units used by the ledger. Yahoo split records
  supply the factors; Alpaca raw/adjusted bar pairs establish them independently.
  Positions cannot use more than the simulated account's cash cap.
  Session loss limits use the exchange session date. Gaps can exceed intended risk.

## Data providers

| Source | Access | Public/request limits | Adjustment and feed |
|---|---|---|---|
| Yahoo historical chart | No account key; can fail or rate limit | 1m/4m: 29 calendar days in six-day requests; 5m/15m/30m: 59; 1h/4h: 729; daily: 3,650 | Provider split-adjusted OHLC; cash dividends excluded; public research data without an availability guarantee |
| Alpaca market data | Server data key and secret | Up to 180 days for minute frames, 700 for hourly frames, 3,650 for daily; provider retention/entitlement and per-job bounds still apply | Explicit `adjustment=split`; SIP consolidated or IEX-only selected by the user; no silent feed fallback |

The public minute window is still short; holidays, gaps or recent listings may
leave too little data for the training/purge/evaluation protocol;
the app reports that limitation instead of shrinking the learning warmup or
manufacturing additional data. Requested coverage includes the entire requested
session window, so IPOs, unavailable history and actual gaps are visible.

For optional Alpaca data, configure `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in
Render's server environment (the standard `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`
names are also recognized). Keys are never entered into browser fields, returned
by status/export APIs, or committed. Only `data.alpaca.markets` bars are requested;
there is no Alpaca trading adapter. No data subscription was purchased by this
upgrade. Permissions and feed entitlement depend on the user's existing account.

Historical price-only tests exclude cash dividends, reinvestment, borrowing,
margin, settlement and regulatory account rules. Today's chosen watchlist has
survivorship/selection bias. The dated stock research articles and TradingView
widgets are separate from the learner's historical price inputs. This release
does not support options, shorts, international sessions or funded stock execution.

## Research protocol

Each run holds costs, source, cutoff, candle snapshot and source-code hash fixed.
It uses earlier 70% development data with a one-day purge before the later window.
Twenty-two existing strategy candidates supply resolved, cost-eligible training
examples. Chronological training observes labels only after their recorded close.
Six later $500 accounts compare breakout, retest, break-even and trailing exits,
and a frozen/updating model pair. The historical updating account learns only
from its own closed account trades; the forward practice account separately uses
the ongoing candidate-example workflow described above. These feedback modes are
deliberate and must not be treated as the same experiment.

Every account is rerun with fees, slippage and half-spread multiplied by 1.5.
End-window liquidation is reported but excluded from the closed-trade evidence
count. All results remain historical development, with no automatic qualification,
strategy promotion or trading permission. The accompanying buy-and-hold benchmark
invests the full $500 cash budget and excludes dividends; its allocation differs
from the strategies' stop-risk sizing. Cash is the other benchmark.

Defaults are **assumptions**, adjustable independently of crypto: 0.01% fee per
side, 0.05% slippage per side, 0.02% half-spread per side, 0.5% stop risk per trade,
95% maximum stock allocation, and a 2% session loss halt. They are not a specific
broker's commission/fee schedule. Thin stocks and fast markets can cost more.

## Persistence and resource bounds

Stock state is isolated under `RESEARCH_DATA_DIR/equity-practice/`:

- `state.sqlite3`: queued work, results/models and forward registration/journals;
- `snapshots/`: immutable downloaded research bars with integrity hashes;
- `forward/`: frozen history with newly observed bars appended.

The existing crypto-account backup does **not** include this directory. Preserve
the whole research directory on the Render persistent disk; each stock run and
forward journal also has an export. No persistence guarantee is made for an
ephemeral filesystem. Historical retries reuse the original snapshot and rerun
the bounded calculation. They do not count as new evidence.

The stock queue allows 12 pending / 100 saved runs, at most 50,000 normalized
candles per run, one active forward account and 30 saved forward registrations.
New historical jobs require at least 150 MB free disk space. The worker coordinates
with the existing heavier research tasks. A stopped or failed forward account's
last mark is preserved; no liquidation is invented after stopping.

Forward replay deterministically rebuilds its paper account from its frozen seed
and registered start using saved history plus new observed bars. Replaying old
bars does not accumulate duplicate model updates. Provider revisions to overlapping
bars (including a new split adjustment), unbridgeable outages, changed code and
the candle cap pause the account visibly. Register new practice after reviewing
the reason; a running experiment never silently changes its historical prices.

## Sources and verification

- [NYSE regular sessions and holiday calendar](https://www.nyse.com/markets/hours-calendars)
- [Calendar package schedule and early-close handling](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html)
- [Alpaca historical bars: split adjustment, feed selection and pagination](https://docs.alpaca.markets/us/reference/stockbars)
- [Alpaca data authentication and coverage](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [yfinance upstream source documents the Yahoo chart API and adjustment handling](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py)

Run `python -m unittest tests.test_equity_practice -q` for calendar, aggregation,
causality, gap execution, sizing, persistence, auth, source failures and forward
registration checks. Run `node tests/check_equity_browser.js` with Playwright for
the browser workflow. Deterministic test fixtures are not market evidence.

Real recorded-data verification and all findings are retained in
`research/stock-practice-v11.19-results.md` and its reproducible snapshot archive.
