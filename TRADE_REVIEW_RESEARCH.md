# V11.4: keep studying losses and near-break-even trades

Declared before examining this revision's AVAX replay, 15 September 2026.

The change targets a concrete limitation: independent historical examples used
the same extended pause after repeated losses as account execution. The learner
also had only coarse exit labels. It could not show whether a loss followed an
observed profit, whether fees consumed a small edge, or what happened after exit.

This revision keeps collecting independently funded examples after a losing
streak, with the candidate's normal entry spacing. Signal rules, costs, gap
checks and actual account pauses still apply. The 22 candidates, risk settings,
minimum evidence, net-return target and qualification requirements are unchanged.

## Fixed research rules

- Near break-even means an actual net result between -0.10R and +0.10R. It receives
  review priority, not a positive reward bonus. R uses the planned dollar stop
  risk including modeled exit costs. A flat price can still produce a net loss.
- Outcomes at or below -1R, smaller losses, near-break-even results and profitable
  trades all remain in the accounting and evidence. No loss is removed because
  it is large. Existing bounded model updates still keep outliers from dominating
  a prediction; aggregate net accounting keeps their full values.
- Close-time reviews record costs, net favorable/adverse marks, giveback, holding
  time and observations such as fees erasing a gain. A 0.5R favorable net mark
  followed by at most +0.1R is labeled giveback; these are descriptive thresholds.
- Detailed examples prioritize losses, near-break-even outcomes, fee-erased gains
  and givebacks. A bounded sample per family/outcome keeps reports manageable.
  Summary counts cover every reviewed completed outcome. Reviewing an example
  never adds another learning observation or changes its net reward.
- After-exit price observations use fixed 1-, 4- and 24-hour windows, starting
  after the exit candle. A window is unavailable until every required candle
  closes, and missing candles keep it unknown. Development reviews cannot read
  beyond the development cutoff. These reports never enter entry features or
  outcome-memory updates.
- One fixed counterfactual moves the stop to a price covering both fees and exit
  slippage only after a previous candle closes at +1 net R. It activates on the
  next candle, retains the original target and actual exit deadline, gives stops
  precedence in ambiguous candles and charges adverse gaps. It is reported as a
  hypothesis, not automatically chosen as a new exit rule or relabeled reward.

Historical simulations use observed OHLC with conservative stop-first ordering.
Paper reviews use observed quotes. Coinbase journals use actual settled amounts;
without a full price path they explicitly leave excursion measurements unknown.
Descriptions are not proof that a feature caused a trade to fail.

## Research basis and limits

Sutton and Barto explain why learning agents need opportunities to explore as
well as act on current estimates. Here, exploration is confined to independent
simulations, where a losing result remains useful evidence.
[Reinforcement Learning: An Introduction](https://incompleteideas.net/book/2/node2.html).

Schaul and colleagues studied prioritizing informative experience in game-based
reinforcement learning, including the sampling bias it creates. This application
uses priority to choose detailed review cases. It does not claim to implement
DQN or use repeated failures as independent market evidence.
[Prioritized Experience Replay](https://arxiv.org/abs/1511.05952).

Testing exit alternatives on already observed trades is hindsight research.
Repeatedly choosing favorable alternatives from the same prices risks fitting
noise. Report 17's reviewed windows are now recorded alongside report 16, so they
cannot provide fresh confirmation of this change.
[The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Validation and measured results

All **209 Python tests passed in 35.972 seconds**. The actual dashboard JavaScript
also passed its mocked-document checks. These cover full-cost break-even, real
losses retaining negative reward, next-candle counterfactual activation,
ambiguous bars, gaps, period cutoffs, post-exit availability, bounded review
sampling, checkpoint resumption and journal persistence. They do not establish
mobile layout, hosted behavior or real exchange fills.

One fixed replay used the supplied AVAX 15m bundle: 105,043 intraday candles and
1,125 separate daily candles, with unchanged data hashes, fees and account risk.
The final source replay took 33.72 seconds. No parameter search was performed.
[The machine-readable comparison](research_baselines/avax-v11.4-comparison.json)
records input and source hashes, ordinary/stressed results and review counts.

| Measurement | V11.3 supplied report | V11.4 fixed replay |
| --- | ---: | ---: |
| Completed development examples | 10,279 | 11,270 |
| Selected final-period trades | 3 | 3 |
| Selected net P&L after costs | -$5.61 | -$5.61 |
| Selected net P&L at stressed costs | -$5.99 | -$5.99 |
| Qualified | No | No |

Independent practice collected **991 additional examples (9.64%)**. Its 11,270
reviewed outcomes comprise 7,505 losses of at least 1R, 520 smaller losses,
229 near-break-even outcomes and 3,016 profits. Longer loss-streak pauses were
skipped 4,195 times in development; that count is not the number of additional
trades. Normal candidate spacing remained. These overlapping examples are not
independent portfolio returns or a promise of more live trades.

The selected losses illustrate distinct questions. The 6–8 March trade never
showed a positive net mark in the conservative observed path, then the next
complete 24-hour window ended 7.07% above its raw exit price. The 16–18 March trade
showed about +0.55R net before finishing at -1R; its next complete 24-hour window
ended 3.08% lower. These observations can motivate entry-timing and exit-policy
research, but do not establish that a wider stop or later exit would improve
future returns. The fixed +1 net R break-even-stop experiment never activated
on any of the three selected trades and changed none of their results. Its
threshold was not retuned after seeing that result.

Detailed development reports retain 82 priority cases while aggregate counts
cover every completed outcome. Both actual selected losses receive reviews.
At-close reviews also accompany newly closed paper and Coinbase journal records;
missing historical quote paths remain unknown. Post-exit windows and exit
counterfactuals currently belong to the historical report, not an asynchronous
live post-exit service.

Report 17 was already reviewed, so this replay contains **no fresh confirmation**.
It establishes more complete practice and diagnosis, not improved profitability.
The existing qualification gates still reject the model. Testing on genuinely
later prices is required before any performance claim.

Reproduce from the project root with the original uploaded files:

```sh
python3 scripts/compare_trade_review.py \
  --bundle 'AVAX-USD_15m_learning-data.zip' \
  --previous-report 'learning-results 17.json' \
  --out research_baselines/avax-v11.4-comparison.json \
  --full-result avax-v11.4-result.json
```

After this revision is merged and deployed, run **Practice on historical data**
again. Engine V11.4, policy v7 and report schema 9 require fresh model/report
generation. The new **Loss and break-even study** appears in each market result.
