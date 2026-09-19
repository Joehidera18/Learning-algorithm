# V11.10 predeployment review — 19 September 2026

The review found and corrected two execution/orchestration defects and two scaling problems. The changes remain in draft PR #13. They have not been merged or deployed, and no exchange orders were submitted. Profitability remains unproven.

## Corrected behavior

**Time limits used a candle's opening timestamp but exited at its close.** A 12-hour limit could therefore hold a position for 12h15m on 15m candles, 13h on hourly candles, or 18h on 6h candles. The simulator now measures age at the execution close. A deadline coinciding with the final test close resolves normally instead of becoming an unlearned END mark. Stops and targets inside the deadline candle retain their existing pessimistic ordering. Prices after that candle cannot alter the resolved outcome.

`exit_ts` remains the exit-bar identifier for backward-compatible candle lookup and delayed learning. `exit_time_ts` records the known close time for TIME and END exits, and holding-duration reviews use it. All fixed learning candidates' deadlines align with the supported intervals. Other research parameters that do not align resolve at the first available close at or after the deadline; OHLC data cannot reveal an exact intermediate fill. Six-hour studies remain research only because this correction does not validate coarse intrabar execution.

**Completing a secondary-only study could postpone the main timeframe's review.** The global queue fields were treated as proof that the selected trading interval had been tested. The scheduler now also requires each monitored coin/timeframe's matching history/cost/version scope, its own unexpired review date, and a current profile when its report claims qualification. Existing failed-download and unqualified-study retry periods still apply.

**Background practice retained unused ledgers and equity curves.** It now streams each resolved label and review to its consumer, retaining only the recent losses needed for cooldown decisions. This mode is restricted to independent practice with an outcome consumer; it cannot replace an account ledger or return account performance. Regression comparisons preserve entry times, full-cost rewards, gap censoring, forecasts, reviews, cooldowns and final models. Feature building also releases finished temporary arrays and skips unused full-engine indicators. The five-year capacity fixture produces the exact same feature hash before and after that optimization.

**Every dashboard poll returned every detailed case study.** The status endpoint now sends compact summaries with reconciled finances and candle coverage. Open one detailed learning review to load its full analysis. The authenticated detail route matches the coin, timeframe and report fingerprint; a response for an older report cannot overwrite the displayed current study. Full report/candle exports retain their models, selected trade ledgers and detailed cases. Existing completed reports remain accessible without rerunning practice for display purposes.

Changed historical exits produce different training labels, so the version identifiers are now `market-structure-v11.10-corrected-deadlines`, `online-net-r-v14-corrected-deadlines` and report **16**. Earlier models and cached learning results require rebuilding. Account risk, fees, strategies and qualification thresholds were not relaxed.

## Same-input replay results

Both versions used the supplied LTC archive, its independent daily candles, the same costs and the same end date. Hourly and 6h inputs contain only complete observed 15m buckets. Every supplied price is marked already reviewed; no result is used to tune or qualify a strategy.

| LTC timeframe | Development examples, before → after | Later practice outcomes, before → after | Final account trades, before / after | Net at ordinary and higher costs |
| --- | ---: | ---: | ---: | ---: |
| 15m | 12,282 → 12,317 | 2,836 → 2,848 | 0 / 0 | $0 / $0 |
| 1h | 3,623 → 3,657 | 819 → 833 | 0 / 0 | $0 / $0 |
| 6h | 463 → 491 | 117 → 127 | 0 / 0 | $0 / $0 |

All six before/after reports reject qualification. These are overlapping practice examples, not extra funded trades or independent evidence. Correct timing changes which examples resolve and when later entries can occur. Forecast error is mixed across timeframes, and the compared populations change; these aggregates do not establish a forecasting improvement. No account-profit improvement was measured.

The pinned source/input hashes, costs, rejection reasons and metrics are in [the machine-readable comparison](research_baselines/predeploy-review.json). Earlier four-coin and confirmation studies remain historical records of their original source versions. They should not be described as newly rerun results of this corrected policy.

## Capacity and hosting

| Check | Before | After | What it establishes |
| --- | ---: | ---: | --- |
| Five years of 15m feature rows: 175,200 | 454.0 MiB peak RSS | 412.4 MiB | Synthetic capacity fixture only; identical feature values |
| Full supplied LTC 15m replay: 105,063 candles | 276.4 MiB peak RSS | 253.1 MiB | Local process measurement including the learner |
| One LTC dashboard report, serialized | 876,900 bytes | 3,420 bytes | Summary retains finances; detailed review fetched separately |
| 90 copies at that report size | 75.26 MiB | 0.29 MiB | Payload projection, not a hosted load test |

The capacity fixture repeats supplied OHLC shapes at artificial timestamps. It is never used as market evidence and reports no trading returns. Local runtimes and process-memory numbers are not performance guarantees for Render.

The configured **512 MB** server still has limited headroom for the full five-year plan. Feature building alone reaches about 412 MiB before training, stored reports and web requests. Start with **one year of 15m/1h on a few coins** on that instance. A 6h study needs at least 750 observed days for the existing 3,000-candle minimum. For broad multi-year studies, review a larger instance's price; Render currently documents a **2 GB** web-service size. No paid configuration was changed. See [Render's compute definitions](https://render.com/docs/blueprint-spec).

Disk requirements also grow. At the observed LTC CSV row size, the maximum 60-coin, five-year 15m/1h/6h plan projects about 949 MiB of candles before saved reports, checkpoints, temporary writes and backups. Actual availability and row sizes vary. Check disk headroom before expanding. Render persists files only beneath the mounted disk path; the configured database and research paths are both under `/var/data`. See [Render's disk rules](https://render.com/docs/disks) and [deployment guidance](WEBSITE_SETUP.md).

Coinbase documents native 5m/15m/1h/6h/day candles, a 300-candle limit per request, and missing intervals when no ticks are recorded. The existing download pagination and complete-bucket/gap rules respect those constraints. This review adds no newly retrieved candle history. See [Coinbase's candle specification](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles).

## Reproduction and verification

Run `python -m unittest discover -s tests -v`, `node tests/check_learning_ui.js` and `node tests/check_finances_ui.js`. [VERIFICATION.md](VERIFICATION.md) records the final results and limits.

For a recorded-candle comparison, run the following separately against each pinned source checkout and each interval (`15m`, `1h`, `6h`):

```sh
python scripts/review_predeployment.py --repo /path/to/checkout \
  --bundle '/path/to/LTC-USD_15m_learning-data(1).zip' \
  --interval 15m --out /path/to/replay-result.json
```

Add `--capacity-days 1825` in place of `--interval 15m` for the artificial feature-capacity check. That mode reports a feature hash and memory only. Run each comparison in a fresh process.

After installing `requirements.txt`, `python scripts/check_web_startup.py --out /path/to/web-smoke.json` starts the actual Gunicorn entry point on loopback with a temporary database. It checks public health/assets, private API authentication, invalid plan rejection, the 6h trading restriction, settings persistence and stopped runners after restart. It makes no external market requests and starts no trading or learning jobs.

The replay source hash is `c322b6b433682559c0ea304238acfc02dd758788a6e32cc20f61b7c1cf01fe82`. The subsequent compact-report changes affect only `lab/autolearn.py`, `lab/service.py` and the new `lab/study_reports.py`; the replayed execution, features, learning, costs and aggregation modules are unchanged. The final lab-source hash is recorded in the comparison and verification note. No hosted mobile layout, broad concurrent hosted workload, new external history or real fills are established by these local checks.
