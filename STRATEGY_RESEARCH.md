# Crypto strategy review — 15 September 2026

This update adds research candidates, not a demonstrated profitable model.
The supplied `learning-results 9.json` contains 29,356 completed training
examples across BTC, ETH and SOL; all three failed qualification and made zero
final-test trades. The report contains results, not the underlying OHLC candles,
so it cannot be used to backtest a new signal. Fresh practice on the saved
Coinbase history is required.

## Assessment of the supplied trading posts

- Fixed rules, capped risk, trend expansion and evaluation across market
  conditions are useful ideas to turn into reproducible tests.
- Support/resistance with RSI can be specified precisely. Our interpretation
  below is an experimental rule; it is not a replication of the commenter's
  discretionary trading.
- Fibonacci levels and “order blocks” need objective level selection, entry,
  exit and invalidation rules before their results are testable. The screenshots
  provide neither those details nor evidence sufficient to verify net returns.
- The leveraged BTC and zero-fee DEX claims were not independently verified.
  The promoted public-account page could not be accessed in this review. No
  audited trader record was established, and no performance from those posts
  is used as a model target. Fees, spreads and adverse fills remain charged.

## Primary research and its limits

| Source | Evidence | What it motivates here |
| --- | --- | --- |
| [Liu and Tsyvinski, authors' summary of Risks and Returns of Cryptocurrencies](https://cepr.org/voxeu/columns/risks-and-returns-cryptocurrencies) | Historical time-series momentum, including a weekly Bitcoin relationship. It does not establish a Coinbase intraday strategy or this app's future performance. | Seven-day momentum combined with a completed-day trend filter. |
| [Grobys, Ahmed and Sapkota, Technical trading rules in the cryptocurrency market](https://osuva.uwasa.fi/server/api/core/bitstreams/6d20e4ef-7741-419e-b2ea-0cb103bfa1dd/content) | Their historical multi-coin sample found support for a 20-day moving-average rule; results varied by coin and lookback. These are historical study results, not a current verified account. | A fixed 20-day simple moving average rather than a large parameter search. |
| [Hudson and Urquhart, Technical trading and cryptocurrencies](https://link.springer.com/article/10.1007/s10479-019-03357-1) | Examined moving averages, filter, support/resistance, oscillator and channel rules, with multiple-testing controls. Positive sample findings did **not** persist for Bitcoin in the later test period, though other coins retained predictability. | Separate trend, breakout and reversal hypotheses, later-period testing and permission to reject every candidate. |

These are adaptations and engineering inferences. The papers did not test our
combined filters, daily ATR brackets, Coinbase fees, holding limits or learner.
The volatility and support/RSI combinations have less direct evidence than the
underlying moving-average and momentum concepts. They are hypotheses to test.

## Exact additions: six candidates in three families

All rules use completed decision candles for entries. Daily inputs require 21
consecutive complete UTC days: a current 20-day SMA, its previous value, a
seven-day close return, and 14-day average true range. Partial days are excluded.

| Family | Entry rule | Maximum holding time |
| --- | --- | --- |
| Daily trend/momentum | Last complete daily close above a rising 20-day SMA; seven-day return positive; decision close above the **preceding** 20-bar high; decision RSI 45–75. | 168 hours |
| Volatility expansion | The preceding eight decision-bar ranges average less than 72% of the previous 24; current close breaks the preceding 20-bar high; current range is 1.5–4 times the preceding 20-bar average; RSI at most 78. | 72 hours |
| Support with RSI recovery | Low tests within 0.25 decision ATR of, or below, the preceding 20-bar low; close reclaims that low and exceeds the open; lower wick at least 25% of the candle; previous RSI at most 40, current RSI above 40 and at most 60. | 72 hours |

Each rejects a daily downtrend (daily close below a falling daily SMA), negative
volume z-score, and the existing extreme-volatility conditions. Two fixed
brackets use daily ATR × 0.75 with a 2.5R target, or daily ATR × 1 with a 3R
target. These are gross price multiples: modeled fees and slippage reduce net
reward. After closure, a four-hour cooldown applies, or 24 hours after three
consecutive net losses. The original 16 candidates remain, giving 22 total.

These longer-lived brackets are not trailing-stop or moving-average exits.
Wider price stops reduce position size under the existing dollar-risk budget;
they do not authorize higher account risk. Entry-gap protection still uses the
shorter decision ATR. Paper execution and Coinbase order planning use the same
ATR choice. The new code does not activate funded trading or introduce leverage.

## Causality, costs and evaluation

- Aggregate only recorded candles. A missing base candle resets daily warmup;
  the original families may resume after their own 240-bar warmup. Paper
  trading reuses already-loaded four-hour bars for daily context, bounded by
  the decision close. No larger market-data bootstrap or new dependency is needed.
- Train only outcomes whose exit candle has closed before the training cutoff;
  unresolved end-of-window trades do not become labels. The existing 24-hour
  gap between training and testing is **not** claimed to exceed the new maximum
  hold. Exit-time filtering is the causal boundary for longer trades.
- Keep actual configured fees, assumed spread/slippage, next-bar fills,
  conservative stop ordering and 1.5× cost stress. Keep existing qualification
  sample, positive-return, uncertainty and drawdown requirements.
- Add an original-16-only comparison using the same new entry features,
  pre-test model seed, risk and costs. Its results cannot select the strategy,
  replace a losing expanded policy, or grant qualification. A negative
  difference explicitly reports that the additions hurt this test.
- Repeated tests of already-seen history are not independent validation.
  Any apparent improvement still needs subsequent forward paper evidence.

Engine `market-structure-v11.1-swing-research`, policy
`online-net-r-v4-daily-context`, and report 6 invalidate incompatible model and
label caches. Saved market candles, account data and selected coins are retained.
The three new fixed-scale inputs are daily momentum, distance from the daily
SMA in daily ATR units, and daily ATR as a fraction of price. They enter the same
bounded model alongside the original 13 inputs.

After merging and deploying, run **Practice on real market history**. Review
training counts by strategy and **Effect of adding the three new strategies**.
A missing-history or unqualified result is valid; no profitable result is
assumed. Automated tests use artificial fixtures solely to check correctness;
they are never substituted for the app's real market training data.
