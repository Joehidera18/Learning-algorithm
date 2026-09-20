# V11.16: forecast response, observed sentiment and focused practice

## Design fixed before the revised replays

The reviewed 57-study checkpoint contains 56 closed selected trades: 12 wins and
44 losses. Mean predicted net return was +0.379R against -0.482R realized.
None qualified. The three newly reviewed losses were negative before fees and
never approached the existing +1R break-even trigger. Raising risk, reducing
fees in the simulation, or retroactively choosing another exit is not a fix.

This revision keeps candidate strategies, costs, risk limits and entry evidence
requirements unchanged. It adds one forecast hypothesis, with no parameter sweep:

* Each candidate records its **base entry forecast** and learns its relationship
  to the eventual full net return, only after the exit is known. Only eligible
  examples train this response; cost-blocked examples and other coins cannot.
* A recency-weighted affine fit uses a 50-observation half-life. Its slope is
  restricted to [0, 1], with ridge `1 / effective_count` toward slope 1.
  The result is blended with the base forecast by `n / (n + 50)`; effective
  count is capped at 100. Both actual and effective counts must reach 30.
* The response can share evidence across forecast bands for the same candidate,
  addressing sparse positive-band corrections. Existing downside corrections,
  saved-entry error penalties, cost checks and risk limits still apply afterward.
* Forecasts preserve the base value, response adjustment, sample counts and last
  available outcome time. Overlapping examples are not independent evidence or
  confidence intervals. A stronger correction could also suppress good trades.

This is an application hypothesis, not an established profitable trading rule.
The distinction between conditional calibration and prediction accuracy is
discussed by [Gneiting and Resin](https://arxiv.org/abs/2108.03210); that paper does
not validate this affine model or any cryptocurrency strategy.

## Sentiment and event collection

The [Alternative.me API](https://alternative.me/crypto/fear-and-greed-index/)
provides its Bitcoin-focused Fear & Greed value and preceding day's value. We
retain provider date, actual receipt time, source link and revisions. Neither
backfilled data nor a revised value can enter an earlier decision. Missing or
stale values are explicitly unavailable, not neutral. The UI attributes each
displayed value to Alternative.me. No hard-coded "buy fear / sell greed" rule.

When observed sentiment actually covers candles, research also trains a separate
control without that source, retaining other recorded news. Ordinary and stressed
returns are both reported; this comparison cannot select or promote a policy.
The four existing candle bundles contain no observed event archive, so they cannot
demonstrate any benefit from sentiment. It must accumulate prospectively.

Collector results become visible after each completed feed, while other feeds are
still fetching. Historical startup waits at most 15 seconds for readiness. A
failed first feed does not signal successful coverage; failed collection remains
explicitly missing. A historical study freezes its exact input archive.

## Market scope

The default list is BTC, ETH, SOL, HBAR, XRP, XLM, ADA, DOGE, AVAX, LINK, LTC, BCH,
DOT, UNI and AAVE, fixed on 2026-09-20. It retains the user's core markets; it is
not a current market-cap ranking or chosen from backtest winners. Historical
defaults, monitored candidates and the online training capacity now use 15.
Existing custom historical lists/timeframes are preserved until the user chooses
the focused preset. Open positions outside the list remain monitored.

Monitoring verifies active USD pairs and usable volume at startup, excludes
stablecoins/wrapped duplicates and disabled, auction, cancel-only, post-only or
limit-only markets. See [Coinbase product metadata](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-all-known-trading-pairs).
Unavailable members are reported, never silently substituted. Selecting fewer
than 15 monitors the highest-volume available members of this fixed list.

## Comparison protocol

Compare main commit `24e21c77cacd4dba28885a55e0a216eb857c3e67` with V11.16 using
all four supplied bundles (XRP 15m, AVAX 15m, DOT 15m, XRP 6h), the exact uploaded
`learning-results 13(1).json` review boundary, identical price/daily/BTC hashes,
fees and risk. No new strategy or hyperparameter choices after viewing results.
Each result represents its own simulated $500 account, never a combined portfolio.
Keep every outcome, including losses, no-trade runs and stressed-cost results.
All these prices have already been reviewed; none can independently qualify the
revision. There are no matching candle bundles for the newest report-13 studies.

Engine V11.16, report 22 and policy v19 require retraining. Previous reports remain
viewable. No real-money orders or deployment are part of this revision.

## Results

| Separate $500 historical account | Before net | V11.16 net | Trades before → after | Higher-cost before → after |
| --- | ---: | ---: | ---: | ---: |
| XRP 15m | -$12.749657 | +$6.354067 | 6 → 1 | $0 → $0 |
| AVAX 15m | -$5.610306 | -$5.610306 | 3 → 3 | -$4.007496 → -$2.256174 |
| DOT 15m | $0 | $0 | 0 → 0 | $0 → $0 |
| XRP 6h | $0 | $0 | 0 → 0 | $0 → $0 |

XRP improved by $19.103724 on this reviewed history. The revised account's single
trade reached its target; it is a different entry from the earlier account's
winning trade. Its saved base estimate was +0.474378R, reduced by the learned
response to +0.328000R using 70 prior eligible forecasts (64.98 effective samples).
The last available response label preceded this entry. This is one winning trade,
not demonstrated stable daily income. The higher-cost XRP account still trades
zero times. AVAX remains a losing account under both cost assumptions.

Forecast accuracy is mixed. XRP's selected-trade RMSE increases from 1.325279R to
1.366418R, but these are different selected entries and sample counts. On the same
2,515 shadow examples its RMSE also increases slightly, 0.664572R to 0.665410R.
AVAX/DOT/XRP 6h shadow RMSE improve slightly (0.651684→0.651066R,
0.755003→0.754823R and 0.385459→0.383333R). Do not generalize the XRP account gain
into a claim that every forecast or every market improved.

All four final ordinary and stressed account windows complete, and their selected
ledgers reconcile. XRP has an earlier fold interrupted by a position spanning a
data gap; that unknown return remains a disqualifying condition. Every study is
unqualified, with reviewed-history, small-sample and cost/robustness failures
retained. No thresholds were tuned after inspecting these results.

The final automatic-practice scope fix excludes monitored old positions outside
the 15-coin list from new automatic training. Repeating all four replays on that
final source produced identical complete reports except creation timestamps.

* [Complete comparison and input/source identities](research_baselines/forecast-response-comparison.json)
* [Eight full compressed before/after records](research_baselines/forecast-response-records)
* [Validation and live public-source smoke check](research_baselines/forecast-response-validation.json)

Verification: 394 Python tests passed in the full suite. After the final scope fix,
two targeted tests passed, including its new regression (395 distinct tests in
total). Both dashboard checks passed. The direct Alternative.me check returned
two valid observations; Coinbase's product metadata request timed out, so no
claim of verified current availability for all 15 coins is made.

Reproduce each supplied bundle against the pinned main checkout and this branch:

```bash
python scripts/compare_eligible_learning.py --repo /path/to/baseline \
  --bundle /path/to/bundle.zip --reviewed-report '/path/to/learning-results 13(1).json' \
  --out baseline.json
python scripts/compare_eligible_learning.py --repo /path/to/revision \
  --bundle /path/to/bundle.zip --reviewed-report '/path/to/learning-results 13(1).json' \
  --baseline baseline.json --out revised.json
python -m unittest discover -s tests
node tests/check_learning_ui.js
node tests/check_finances_ui.js
```
