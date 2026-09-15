# Cost-aware learning, V11.2

## Evidence that motivated the change

The supplied `learning-results 12.json` completed 13 markets with 22 variants
each. It contained 130,625 development examples but only 32 selected final-test
trades. No market qualified. The immutable summary and source-file SHA-256 are
in [research_baselines/report-12.json](research_baselines/report-12.json).

SOL earned $9.014 before fees and paid $9.634, leaving a $0.620 loss. HBAR, XRP,
ADA and AVAX also lost before fees. BCH's single $0.168 net win became a $0.032
loss under higher costs. These are separate $500 market simulations. Training
examples overlap, and these results do not demonstrate a portfolio return.

This evidence motivates improving cost conditioning, feedback coverage and
evaluation. It is too sparse to select coins, delete a losing family, fit new
indicator thresholds or promise a profitable strategy. The 22 candidate rules,
stops, targets, holding limits and account-risk settings stay fixed.

## Changes to the learner

1. **Known entry economics.** The model has 19 inputs: the previous 16 plus
   signal-time cost in R, net target reward/risk, and the planned holding limit.
   Inputs use the signal close, never the subsequent open. The original vector
   is saved with the simulated or journaled trade and reused at feedback time.
2. **Comparable-cost evidence.** Each candidate keeps low-cost (at most 0.25 R),
   moderate-cost (at most 0.50 R) and higher-cost observations separately, with
   regime estimates within each group. After 30 examples, the matching cost
   group supplies the prediction and recent-return evidence. Sparser groups
   fall back to the pooled model. An expensive exploratory loss is still
   learned; it does not directly overwrite a sufficiently supported low-cost
   estimate. An outcome increments the global observation count once.
3. **Prediction-error penalty.** Before each weight update, accumulate squared
   clipped prediction error. Deduct `sqrt(mean_squared_error / min(n, 100))`
   from the estimated net R before ranking and applying the 0.10 R threshold.
   The effective count cap limits the benefit from large overlapping samples.
   This is a fixed ranking heuristic, not a calibrated confidence interval or
   a parameter selected by maximizing the supplied report's profit.
4. **Continued historical feedback.** In each later research window, all
   candidates keep independent, fully costed hypothetical positions. The same
   execution engine handles selected and shadow trades. The learning clock
   advances those simulations only through bars that have already closed at
   the account's decision time. Completed shadow outcomes update the model even
   if the account declined the entry. Unknown outcomes across gaps and forced
   end-of-window closes do not become labels. Selected account trades are not
   added a second time to that model. Account cash counts only selected trades.
5. **Feedback control.** Replay the same learner with feedback only from
   selected account trades, at ordinary and 1.5-times costs. This matches the
   journal feedback available between historical reviews. Both control results
   must be complete and profitable as an additional qualification requirement.
   Continuous paper and Coinbase journals remain separate and do not submit
   shadow orders. Historical shadow learning runs during research, not on live
   ticks. A positive control still does not prove future execution performance.

Fees are not reduced to make the result look better. Coinbase uses maker/taker
pricing and an account's tier can change; the user must supply the appropriate
actual fee for the modeled execution. [Coinbase Advanced fees](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees).

## Research reuse and fresh confirmation

The supplied report influenced this revision. Its end timestamps are therefore
recorded as already reviewed for the 13 markets. The controller also pins the
previous report's end when the learner or cost assumptions change. That boundary
is part of the saved-result fingerprint and persists through restarts.

The original final 20% remains visible as a **reused-history research test**.
It can diagnose a change but cannot independently qualify it. When newer prices
exist, a separate confirmation account starts after the review boundary. Its
seed receives only outcomes resolved before that boundary; future outcomes are
released only after their exit candles close. The confirmation must also pass
the existing count, positive-return, stress, uncertainty and drawdown checks.
The selected-account-feedback control must also be complete and profitable on
these later prices at both ordinary and higher costs.
With insufficient new data, the report says so instead of declaring success.

Repeated selection on a backtest raises overfitting risk even if each simulated
decision is causal. This implementation tracks known reuse; it does not claim
to implement a complete multiple-testing correction or calculate PBO.
[Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Reporting and deployment

The dashboard separates historical training examples, final-test account trades
and forward paper-trade feedback. It shows additional shadow examples, the
selected-trade-only control, fresh-confirmation status and per-family gross
P&L, fees and net P&L. Gross P&L already includes adverse modeled slippage; the
slippage-notional diagnostic must not be subtracted a second time.

Each completed market has **Download candles & report**. The authenticated
export bundles that report's saved Coinbase candles, learning result and a
manifest into a ZIP. A canonical candle SHA-256 binds new reports to the exact
cached prices. A changed or missing dataset is rejected instead of silently
substituting newer prices. Older reports without a digest are explicitly marked
unverified by hash. The bundle excludes account credentials and the account
database, and supports a reproducible performance review on the next run.

Versions: engine `market-structure-v11.2-cost-learning`, policy
`online-net-r-v5-cost-context`, report `7`. Existing models and label caches
must be rebuilt. Downloaded market candles, journal records and the persistent
disk are preserved. Deploy on the existing Render service and run **Practice
on real market history** to evaluate the change on its saved prices.

The uploaded report contains summary results and selected trades, not its raw
candles or complete entry-feature/outcome dataset. The public Coinbase request
timed out in this workspace. New market performance therefore remains
unmeasured here. Tests use explicitly artificial fixtures to verify timing,
accounting and state behavior; those fixtures are not profitability evidence.
