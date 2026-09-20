# News, regulation and scheduled events — V11.12

The learner can now record selected news sources and official calendars, join the versions known at each signal close, and learn from the later net outcome. This is event context, not a system that understands every article, predicts surprise announcements, or establishes why a market moved.

## What is collected

| Source | Information | Freshness after a successful check |
| --- | --- | --- |
| Federal Reserve monetary RSS | Policy announcements | 1 hour |
| Federal Reserve regulatory RSS | Banking/regulatory announcements | 1 hour |
| SEC press releases | Regulatory announcements, including proposals and actions | 1 hour |
| BLS calendar | Scheduled national economic releases | 24 hours |
| Federal Reserve meeting calendar | FOMC meeting start dates | 24 hours |
| Coinbase status Atom | Operational incident announcements | 1 hour |
| CoinDesk RSS | Reported crypto headlines | 1 hour |

A separate worker checks every 15 minutes with at most three concurrent requests, 12-second socket timeouts and a 2 MB response limit. Only fixed HTTPS endpoints are fetched; a redirect is reported for review. The collector stores headline metadata, links, timestamps and revisions, not complete articles. This polling is too slow for competing on breaking-news execution latency.

The dashboard's **Market events** panel shows recent announcements, the coming seven days, source errors and freshness, and an event-history download. **Start event collection** works independently of trading. Starting historical practice or automatic learning also starts collection. Collection continues after practice finishes; use **Stop event collection** to stop it. Its enabled state and archive survive a service restart on the configured persistent database. The ordinary trading Stop button stops trading and learning; event collection has its own visible control.

BLS dates use Eastern time with daylight-saving conversion. FOMC entries describe the **start of the meeting, date only**; the implementation does not invent a precise statement-release hour. Schedules can change. Missing calendar items are marked withdrawn when a complete successful calendar fetch omits a previously scheduled future event. Explicit cancellations remain distinct from withdrawals. A failed fetch cannot withdraw a schedule.

## What the model uses

Seven fixed-scale features extend the existing 32 inputs to 39: the fraction of sources recently checked, four counts of relevant announcements during the preceding 24 hours (macro, regulation, crypto reporting and exchange operations), and counts of announced events due within 24 hours and seven days. Counts are bounded using declared scales. They have no assumed bullish or bearish sign: only completed, costed outcomes train the coefficients. Existing outcome heads receive the same entry-time inputs.

Some major coin names and unambiguous tickers are matched in headlines. Macro/regulatory items are broad context; unrecognized asset mentions also remain broad context. The panel and documentation identify this limited matching rather than claiming complete entity resolution. An SEC announcement is not labeled enacted law. Article bodies, legal meaning, jurisdiction, consensus forecasts, actual economic-release values, token unlock schedules and on-chain data are not parsed in this version.

If all feeds are unavailable, the event vector is zero with zero coverage. Partial coverage is explicit. Previously observed announcements can remain visible after a feed becomes stale; this is not a claim that no later news occurred. The existing price/risk rules continue; missing news does not liquidate positions or loosen any trading limits. A model trained without event inputs keeps ignoring them until fresh practice explicitly trains an event-enabled model.

When any recorded event coverage exists in a study, a separate model is trained without event inputs on the same candles, costs and review boundaries. Reports show ordinary- and higher-cost differences. Neither a good difference nor an event-group profit automatically promotes a model. Existing qualification, independent accounts and previously reviewed-history rules remain in force. Learning from prices without historical event coverage remains possible, but that performance does not demonstrate a news-related edge.

Completed-trade summaries group net P&L by the context present at entry, separately identifying unknown coverage. These groups overlap and exclude end-of-test valuations. They describe associations, not causal explanations. Every historical trade retains its entry context in its recorded features; forward paper-trade reviews retain it too.

## Avoiding hindsight

Every revision has a provider publication timestamp, local first-observation timestamp, availability timestamp, occurrence/scheduled timestamp, source URL, status, category and affected assets. Availability is the later of publication and first observation. An old article fetched today therefore cannot enter yesterday's decision. BLS entries without a publication timestamp use zero for that unknown field; their observation time still determines availability.

A change creates a new version. Tests look up the version available at the decision close. News updates, reschedules, withdrawals and later poll recoveries cannot overwrite past knowledge. A scheduled release does not turn into a known release result merely because its scheduled time passes. Failed or expired collection is unknown coverage, not a zero-news observation.

Interrupted studies pin their event archive, just as candle download cutoffs are pinned. A later collection cannot silently change resumed candidate inputs. Source data, event versions and poll records are hashed into study/experiment identity. A completed bundle includes the exact `market-events.json` used by that report; a changed hash is rejected. Dashboard report details omit the raw archive, which remains in the downloadable bundle and complete export.

The collector does not backfill an independent, timestamp-verified historical news archive. The supplied candle bundles lack that archive. Today's feeds and present-day macro revisions cannot be presented as information available throughout a multiyear backtest. Collection builds prospective history; an external archive would need reliable first-availability and revision records. Manually supplied timestamps are not independently verified by the JSON validator.

## Research and verification

The live adapter check on 20 September 2026 UTC recorded **450 versions**, with six of seven sources available and three upcoming entries within seven days. Coinbase status timed out. An initial check revealed CoinDesk's permanent redirect to its no-trailing-slash feed URL; the fixed source uses that canonical endpoint. Source availability can change and the deployed host must show its own health.

The full supplied XRP 15-minute archive contains **105,062 candles**. All 450 newly collected events were first observed after that archive's test period, so the replay correctly gives them **zero historical coverage**. Its primary final account still makes six trades for **−$12.749657**; the higher-cost account selects zero trades. Original model weights, calibration values and forecast audit data match the earlier V11.11 replay, while the seven additional event weights remain zero. The earlier stored forecast audit predates a descriptive scope-text correction, so only those explanatory strings are excluded from its comparison. This is a causality check, not a profitability improvement. See [the measured record](research_baselines/market-events-replay.json).

A separate deterministic software test uses explicitly artificial prices/events to exercise event-feature training, the independently trained price control and export identity. It is not market-performance evidence. Further tests cover delayed observations, future updates, DST, schedule windows, cancellations/withdrawals, restarts, failed feeds, safe rendering, authentication, pinned inputs and exact exports. See [verification](VERIFICATION.md).

Reproduce the current-news/old-price check with `scripts/check_event_replay.py`; its `--baseline` accepts the earlier `compare_eligible_learning.py` result. Replay a downloaded event/candle bundle with:

```bash
python run_research.py --learning --csv candles.csv --daily-csv daily-candles.csv \
  --events-json market-events.json --symbol XRP-USD --interval 15m --out event-study.json
```

Use the exact reported fee and slippage settings, and add `--bitcoin-csv bitcoin-daily-candles.csv` when the original study used that input. A missing event archive is not replaced with generated events. The archive validator currently bounds a snapshot at 500,000 combined event versions and poll records; larger collections need a reviewed storage/indexing extension. Event comparisons add a separate replay only when event coverage exists. No hosted latency or memory-capacity improvement is claimed for this version.

## Sources and next research needs

The [Federal Reserve RSS directory](https://www.federalreserve.gov/feeds/feeds.htm) and [SEC RSS directory](https://www.sec.gov/about/rss-feeds) provide the official announcement feeds. [BLS's release calendar](https://www.bls.gov/schedule/news_release/) documents its changing calendar and Eastern-time convention. The [FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) provides meetings and links to statements/minutes. [Coinbase status](https://status.coinbase.com/) links its incident feeds; [CoinDesk's feed](https://www.coindesk.com/arc/outboundfeeds/rss) supplies reported headlines.

For later actual/consensus surprise features, economic data must preserve the value available at release rather than today's revised value. The [FRED/ALFRED real-time-period documentation](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) explains that distinction; that numerical-data adapter is not implemented here. Broader international regulators, project-maintained upgrade/unlock calendars, verified entity tagging and measured event-reaction studies are additional work. Do not claim coverage of all current events or advance knowledge of unscheduled outcomes.

Versions: engine `market-structure-v11.12-event-context`, policy `online-net-r-v16-event-context`, report 18. Fresh historical practice is required. Profitability and the benefit of news features remain unproven.
