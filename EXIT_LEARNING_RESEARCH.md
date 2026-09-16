# V11.5: causal exit learning

Declared before running the revised model on the supplied candles:

- Preserve the 22 entry candidates, fees, sizing, account loss limits and qualification requirements.
- Train one separate model with the existing fixed hypothesis: after a completed candle closes at at least +1 net R, raise the stop to fee-covered break-even for the next candle. Keep the original target and time limit; never widen a stop. Gaps can still lose money.
- Collect that model's own development and later-period outcomes using the shared execution engine. Re-evaluate the entire account, including new entry opportunities, cooldowns and subsequent learning after different exits. Do not sum isolated hindsight savings.
- Report ordinary and 1.5x costs, earlier folds, selected-account-feedback controls and any later confirmation. No threshold search or per-market winner selection. This experimental model cannot qualify, replace the approved profile or submit orders.
- Fix adaptive monitoring's unnecessary four-timeframe readiness requirement. Apply the historical model's decision-timeframe warmup and gap checks; entry strategies still enforce their daily-data requirements. Preserve the legacy multi-timeframe workflow.
- Register report 19 as reviewed history. Any new prices must start after the recorded end of each reviewed market; supplied old candles are research reuse.

Research basis: QuantConnect's [research guide](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide) explains why repeated parameter tuning on the same history does not establish generalization. Its [stop-market documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/stop-market-orders) describes stop-triggered market orders and why execution must allow slippage. These support the evaluation and execution rules, not a claim that a break-even exit is profitable.

## What was corrected

Historical adaptive decisions use the selected candle interval and completed daily context. Ongoing paper decisions and Coinbase signal export previously required 241 continuous candles in all four intraday timeframes before consulting that model. A gap or stale cache in an unused timeframe could block a historically eligible setup. Adaptive monitoring now uses the decision interval's history, while individual entry rules still enforce their daily-data requirements. Legacy multi-timeframe readiness, account controls and qualification remain unchanged. Future or old signal candles still cannot trigger a new entry.

The existing per-trade diagnostic only described an alternative exit before the original exit deadline. Summing its avoided losses was not a new account backtest: an earlier close can make a later trade possible and change subsequent learning. The new experimental model learns its own development labels, then runs its own chronological account, independent feedback and selected-account-feedback controls. Its state and action identities cannot be mixed into the current model. Checkpoints 0–21 belong to the current model; 22–43 belong to the separate exit model. Exact resume across interruptions in either study is tested.

Protection is calculated from entry price, both fees and adverse exit execution. The original risk denominator stays fixed after the stop moves. A mathematically zero exit at that calculated stop is recorded as break-even; floating-point cancellation below 1e-10 dollars cannot invent a win or loss. This does not round arbitrary losses or credit a reward bonus. A stop gap retains its actual modeled loss. A high wick alone cannot activate protection, and a same-bar stop takes priority over any later hypothetical gain.

## Measured results

The comparison used the supplied `DOT-USD_15m_learning-data 5.zip` and `AVAX-USD_15m_learning-data.zip`, including their separate daily candles. The AVAX snapshot is the older report-17 bundle; it is not the later report-19 AVAX history. Inputs were validated against the embedded canonical hashes. Both versions used report 19's reviewed-history boundary, so neither dataset supplies fresh confirmation.

| Supplied snapshot | Current model: trades / net | Exit model: trades / net | Exit model at 1.5× costs | Qualified experiment |
|---|---:|---:|---:|---|
| DOT 15m, report 19 | 0 / $0.00 | 0 / $0.00 | $0.00 | No |
| AVAX 15m, report 17 candles | 3 / −$5.61 | 3 / −$5.61 | −$5.99 | No |

**No final-account profit improvement is measured on these two snapshots.** Each test is a separate $500 simulation. The current model's outcomes, training diagnostics, selected trades and model weights/observations match V11.4 exactly when model-version metadata is excluded. The readiness repair affects ongoing signal handling, not the historical policy's entry logic.

The separate DOT model studies 10,872 development examples versus 10,841 for the current model. Near-break-even examples increase from 291 to 368, while profitable examples decrease from 2,506 to 2,470. On AVAX it studies 11,298 versus 11,270 examples; near-break-even examples rise from 229 to 366 and profitable examples fall from 3,016 to 2,956. These are different, overlapping simulated paths, not one-for-one conversions or account money. More break-even outcomes alone are not an improvement in profitability.

The exit model has zero profitable earlier folds for DOT and one for AVAX, compared with zero and two for the current model. Its selected-account-feedback controls also fail profitability: DOT is $0 at both cost levels; AVAX is −$5.61 ordinarily and −$5.54 at higher costs. No winning variant was chosen after reviewing those results. The current model remains the sole source of qualification and forward profiles. The experimental model is excluded from paper and Coinbase order entry.

[The saved comparison](research_baselines/exit-learning-comparison.json) records exact input/source hashes, outcomes, folds and controls. [Report 19's reviewed windows](research_baselines/report-19.json) cover all thirteen markets. Requests for additional data through the hosted app and Coinbase public endpoint timed out during this work; no new candles or live fills were verified. These results justify the new research capability and the readiness correction, but do not justify deploying the alternative exit rule.

## Reproduction

This document records the historical V11.5 experiment. Use a V11.4 checkout at commit `a20b076526c05943805dd04f64bba51e1503d839` for the baseline and a V11.5 checkout at `6718a89164bd383c825594f6cb3551ece04b8014` for the revision. Keep the original attachments unchanged. The baseline below intentionally uses the same report-19 review boundary as that experiment. Later V11.6 changes intentionally alter entry learning and are evaluated separately in [CANDLE_CONTEXT_RESEARCH.md](CANDLE_CONTEXT_RESEARCH.md).

```bash
python scripts/compare_exit_learning.py --repo /path/to/v11.4 --bundle "DOT-USD_15m_learning-data 5.zip" --reviewed-report "learning-results 19.json" --out dot-baseline.json
python scripts/compare_exit_learning.py --repo /path/to/v11.5 --bundle "DOT-USD_15m_learning-data 5.zip" --reviewed-report "learning-results 19.json" --baseline dot-baseline.json --out dot-revised.json --summary dot-comparison.json
```

Repeat the same declared commands with `AVAX-USD_15m_learning-data.zip` and distinct output filenames for the second dataset. The script asserts the current model's exact agreement with V11.4, apart from version identifiers. It records the exit-model results without choosing or promoting it. Runtime depends on the machine; each full revised study now trains two separate models.

The existing main-screen finance changes are included in this update. Training examples and both alternative-policy comparisons remain excluded from account trade totals. Run historical practice again after deploying V11.5; existing finance history remains available.
