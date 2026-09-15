# V11 learning design and evidence

The main workflow now trains and operates a small adaptive trading policy automatically. The delivery includes source code and offline behavior checks. It does not include a pretrained profitable model, downloaded years of Coinbase candles, or a connected trading account.

## The learning loop

1. Load up to 30 active Coinbase USD markets, ranked by current trading volume.
2. Request up to 1,095 days of completed candles for the first five markets. Newer listings may supply less history. Validate all supplied prices, then use only the continuous suffix after the latest gap. Disclose excluded candles and actual hours used; reject fewer than 3,000 consecutive candles or any invalid prices. Missing prices are never invented. A late gap can exclude most of a download.
3. Collect hypothetical resolved examples for 16 candidate rules across four families, using only the development portion of the history.
4. Learn an estimated net result in R for each candidate from the features present at entry. One R is that trade's modeled initial stop risk after costs.
5. Test the whole adaptive policy on three later expanding windows and a final 20% holdout, with 24-hour gaps before tests. Models make decisions before learning their outcomes; outcomes become available only at the exit candle's end.
6. Replay the final period with 50% higher modeled fees and slippage. Also show diagnostic replays with learning disabled and with pooled learning without regime adaptation or cost screening before ranking. Compare with cash and buy-and-hold after costs. The diagnostics cannot replace the updating policy or change qualification.
7. Install a model only if it passes the historical checks, then update the paper model from actual completed paper trades. The separately enabled Coinbase runner updates a separate model from settled real trades.

Each policy test starts with a $500 account and one position. Results for different coins or windows are not added into a fictitious combined return. The system's simultaneous multi-market paper account still needs forward observation.

## What the model learns

Each of the 16 candidates has a pooled regularized linear model of net R and separate models for observed BULL, BEAR, and CHOP entry conditions. A stochastic-gradient update adjusts the pooled and matching regime model after an observed outcome. This is one outcome counted once, not two independent examples. Feature scales are fixed in code, so future test data cannot influence normalization.

After at least 15 examples in a regime, its prediction is blended with the pooled prediction using weight `n / (n + 50)` for the regime estimate. Sparser regimes use the pooled estimate. The recent-return check uses the matching regime after 15 examples, allowing recent sideways losses to coexist with positive evidence in rising conditions. These fixed thresholds need evaluation on actual prices. The templates remain long-only and can have no eligible bearish examples.

The 13 inputs include a constant, RSI, quote-volume z-score, ADX, ATR percentage, 20- and 50-bar momentum, a quote-volume OBV proxy, candle-volume pressure, close location within the candle, two regime flags, and candle-range expansion. All are taken from the entry signal candle. Model forecasts are estimates, not calibrated win probabilities or promises of profit.

The trade templates stay defined in advance. Learning changes which eligible template and stop/target variant is preferred under current conditions. It does not write new Python code, use a language model, ingest social media, or bypass price, cost, and account-risk controls.

A candidate needs at least 30 completed training observations, a positive exponentially weighted recent result, and an estimated net result of at least 0.10 R to be eligible. Cost and net-payoff checks at the known signal close run before ranking, so an expensive favorite cannot hide a feasible alternative. Actual execution still rechecks the future entry gap and costs; it never uses that future open to rank another candidate. The best qualifying estimate wins. These thresholds are engineering hypotheses, not empirically established optimums.

Learning uses bounded influence: the target R and individual gradient errors are clipped to ±3, model weights are bounded, and a small regularizer limits growth. The learning rate declines with observations but has a floor so later feedback still matters. Full losses remain in cash, realized net R, drawdown, and daily risk bookkeeping; only their influence on a single model update is capped. Recent performance uses an exponential update weight of 0.03.

A loss can reduce preference for a similar setup; a success can increase it. Neither result identifies the cause of a trade, and repeatedly updating a weak model can make performance worse. The changing-policy tests therefore also report deterioration relative to the frozen diagnostic.

## Training examples versus account returns

The development labels are independently funded hypothetical trades from each template. This lets the system continue studying later conditions even if a hypothetical template depleted its cash earlier. Their profit totals are not reported as a tradable portfolio. Samples from similar templates can overlap and are correlated.

All later policy evaluations use ordinary $500 account accounting, modeled fees on both sides, slippage, the assumed 0.05% half-spread, position sizing, and the existing entry/exit rules. They do not reset capital after each trade. They allow no same-candle reentry, apply stop-first ambiguity handling, and assume adverse fills through stop gaps.

Policy replays now stop new entries after the configured daily equity loss, reset at the next UTC day, and continue monitoring existing positions. The replay uses the prior close as the new day's baseline and conservative intrabar adverse marks bounded by a stop fill. A temporary loss can latch the halt even if the price recovers. This approximates the paper account's tick-based risk control; OHLC cannot reconstruct every intrabar event or a combined multi-market account. Reports include fees, gross P&L and halted days.

The pooled diagnostic uses the same trained pooled seed, costs, sizing and daily halt, while disabling regime adaptation and cost screening before ranking. It is an isolated comparison of the changes, not an exact replay of an earlier released version. Negative differences remain visible. Buy-and-hold invests $500 at the first executable final-test open and liquidates at its last close after modeled costs; its exposure differs from the policy.

The historical gate requires at least two positive later windows, at least 30 final-period trades, positive ordinary and stressed final-period net P&L, a positive lower bootstrap bound on mean net R, and final-period drawdown no greater than 15%. The interval is conditional on the chosen learning procedure and sample; it is not a probability of future profit or a complete correction for overfitting.

## Feedback and saved state

Entry vectors and parameters are saved with each paper trade and Coinbase plan. A journal transition to CLOSED and its learning update use the same database transaction. Repeated polling, reconciliation, and restart cannot teach that same closure twice. A database failure rolls both changes back; malformed model feedback is recorded as a learning error without preventing the financial journal from closing.

Paper and Coinbase forward model states are separate. Coinbase feedback uses confirmed net P&L after fees, divided by the planned stop-risk amount. Preview-only results do not train the real model. Changed fee signatures prevent an old-cost result from training a model for different costs.

Both channels initially use the qualified historical model. Saved forward updates survive ordinary process restarts. After a new historical review produces a different model fingerprint, that newly trained model seeds the channel's next use. Previous trade records and reports remain saved; old forward updates are not blindly replayed as if they were independent new examples.

The controller reviews qualified markets every 28 days, rejected markets daily, and download errors after an hour while running. Each market keeps its own deadline, so one rejected market does not force the others to retrain daily. Changes to tested settings (including daily loss limit), engine, policy, report version, or selected training markets trigger review. Resuming with different markets triggers a study immediately; changing only their rank order does not. Identical downloaded data, settings, and versions reuse the saved result. Restarts do not start the controller or exchange trading automatically.

Completed candidate labels and diagnostics are checkpointed in the database. A restart within 24 hours reuses a pinned candle cutoff and skips finished candidates if data, settings and versions match. The interrupted candidate and later evaluations restart. Older jobs or changed inputs discard incompatible training checkpoints; successful jobs remove them. Downloaded chunks and completed reports remain reusable. This upgrade uses policy `online-net-r-v2-regime-costs` and report version 3; older models require fresh qualification.

Under **What has it learned?**, each new report shows training signal matches, simulated entries, completed examples, and the most common reasons entries were blocked. The exported report includes the full breakdown for all 16 candidates and final-test learning rejections. Candidate counts overlap across variants and are not account trade counts. Paper market rows also offer **Candidate checks**, separating missing training evidence from nonpositive recent results or estimated returns below the entry threshold. These diagnostics explain decisions without changing them.

Repeated reviews can use overlapping history and test periods. They are maintenance checks, not successive independent experiments. Selecting today's liquid assets also introduces survivorship and universe-selection bias. Reserve genuinely new prices and examine the forward account journal before drawing conclusions about improvement.

## Controls and practical limits

The paper risk budget remains 0.75% of equity per qualified trade, with 3% total open stop risk, 30% per-position allocation, 100% total allocation, and a daily entry halt at 3% loss from that UTC day's equity baseline. Gaps can exceed these modeled risk amounts. Existing positions remain monitored when entries are paused.

The main button uses paper money. Coinbase remains separately configured and activated, with its original one-position and capital limits. Native protective orders, preview requirements, price caps, order-book checks, settlement reconciliation, and local live opt-in remain in place. Changing model weights does not raise these limits to chase the daily goal.

Three years of 15-minute data is 105,120 candles per coin. The original V11 flat artificial dataset of that size completed in about 5.5 seconds and peaked near 216 MiB. The updated learner's CLI processed 12,000 artificial hourly candles in 0.89 seconds with 40.6 MiB peak child-process memory, generated 411 development labels and three final-period trades, and rejected the model. These are compute checks, not market studies or cloud sizing guarantees. Actual downloads, active-trade datasets, concurrent monitoring, and hosted hardware can take longer and use more memory.

The small Render service is an initial configuration. Monitor memory on real multi-year runs and select a larger instance if needed. Do not increase worker or instance count for one trading account.

## Primary references

- [Scikit-learn: stochastic gradient descent](https://scikit-learn.org/stable/modules/sgd.html) documents incremental regularized linear learning. V11 uses a small custom implementation with its own bounded update rule; it does not claim to reproduce a particular library estimator.
- [River: model evaluation](https://riverml.xyz/dev/recipes/model-evaluation/) and [delayed online evaluation](https://maxhalford.github.io/blog/online-learning-evaluation/) explain predicting before learning and respecting when outcomes become available. V11 applies that principle at trade closure.
- [Scikit-learn: time-series splits](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) explains preserving time order in evaluation. V11 implements its own windows and a 24-hour purge.
- [Coinbase Exchange candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) documents the public history interface used by the existing downloader. Advanced Trade order integration remains separate.
- [CFTC: AI trading-bot advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html) explains why automated or AI-labeled trading cannot support guaranteed-return claims.

The $10–$15 daily target is 2–3% of the starting $500. No result in this delivery demonstrates that level of daily return, a positive expected live return, or an improvement over V10 on actual market data.
