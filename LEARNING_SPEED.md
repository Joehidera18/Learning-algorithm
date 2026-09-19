# Historical learning speed without changing the model

This revision optimizes the V11.11 CPU replay. It preserves the same candle history, candidates, independent exit and selection experiments, costs, risk controls and qualification rules. It does not change the statistical model or promise better returns.

## Measured bottlenecks and changes

A `cProfile` run of the primary workflow on the last 20,000 recorded XRP candles made 91,338,346 function calls and took 27.793 seconds under profiling. Simulation accounted for 23.715 seconds cumulatively. Its simple-strategy wrapper ran 2,220,112 times, including a repeated relative import; recursive model copying accounted for 1.510 seconds. These profiler timings locate work rather than establish normal throughput.

The changes are limited to three areas:

- Import the simple-strategy evaluator once at module load, rather than during each candle evaluation.
- Stop constructing unused per-candle rejection counts and equity marks in streaming background practice. The account simulations retain their ledgers, equity curves and risk checks. A streaming caller that explicitly requests a daily loss halt still computes the marks required to enforce it. Trade paths, fees, closure callbacks, gap events and loss-pause diagnostics are preserved.
- Copy model snapshots only when the caller retains them. The final primary learner and the ordinary/higher-cost confirmation seeds are still independent snapshots. Diagnostic account runs no longer create before/after model copies that the caller immediately discards.

No global price cache, extra process or added dependency is introduced. The existing model/report versions stay the same because this change is intended to preserve exact behavior and cached research compatibility.

## Measurement method

`scripts/benchmark_learning_speed.py` starts from a pinned source directory and the supplied candle bundle. Each benchmark is a fresh process, run sequentially. Time covers `learn_history`, including its feature building, candidate training, comparisons and report construction; it excludes downloading, result hashing and writing the benchmark record. CPU time and peak process RSS are recorded separately. This is a local computation measurement, not hosted load or network throughput.

The report digest includes every output field except the top-level creation timestamp. Model weights, entry forecasts, trade ledgers, costs, training diagnostics, alternative-policy comparisons and qualification decisions must all match exactly. A second model-only hash is also checked. A faster run with a changed report fails the comparison.

The XRP case uses all 105,062 supplied 15-minute candles and the normal three-variant workflow. The LTC case uses all 104,966 supplied five-minute candles and the primary workflow with its existing ordinary/higher-cost and other account controls. Both retain their exact independent daily inputs and mark the supplied dates as already reviewed.

Example, with the earlier V11.11 source checked out separately:

```sh
python scripts/benchmark_learning_speed.py --repo /path/to/before --bundle '/path/to/XRP-USD_15m_learning-data 2.zip' --out /tmp/xrp-before.json
python scripts/benchmark_learning_speed.py --repo . --bundle '/path/to/XRP-USD_15m_learning-data 2.zip' --compare /tmp/xrp-before.json --out /tmp/xrp-after.json
```

For the separate LTC check, substitute `LTC-USD_5m_learning-data 2.zip` and add `--primary-only` to both commands. The speed benefit should be measured on the intended server too; download latency, CPU allocation, data volume and running website traffic affect elapsed time.

## Results

| Workload | Before | After | Less elapsed time | Throughput multiple |
| --- | ---: | ---: | ---: | ---: |
| XRP 15m, 105,062 candles, all three policy variants | 123.504 s | 87.392 s | 29.24% | 1.413× |
| LTC 5m, 104,966 candles, primary workflow | 40.740 s | 29.586 s | 27.38% | 1.377× |

Both complete report digests match exactly except for creation time. XRP retains 13,832 learned observations and six final primary trades with -$12.749657 net P&L. LTC retains 11,461 observations and zero final primary trades. All ordinary/higher-cost results, independent experiments that were enabled, forecasts, models and qualification decisions are identical. Faster computation does not remedy the earlier XRP performance regression.

Peak process RSS is 260.25 → 265.46 MiB for XRP and 246.42 → 244.81 MiB for LTC. This optimization does not consistently reduce memory. It adds no unbounded cache, and these measurements do not establish the capacity of a hosted five-year/many-market plan. The earlier hosting limits still apply.

These are one sequential before/after timing pair per workload on Python 3.12.14, with no concurrent benchmark/test jobs. Preliminary profiler and overlapping attempts are excluded from the timing claims. CPU time closely matches elapsed time in the recorded runs. Downloading and actual Render response times were not measured.

The baseline is PR #14 commit `46d22a8b0eeb0ea32499d4860d54efc196ef64c2`, with lab-source SHA-256 `7a8ed7e5d6ceb51048d9b15c982ef8a5eaddb72273fcae69cede17a193221b27`. The optimized lab-source hash is `2cac57102f0ccab81a313ccb513f4424c3539115cb096ac1a5919b083d7a0873`. [The machine-readable record](research_baselines/learning-speed-comparison.json) contains exact sources, input hashes, output hashes, costs, CPU times and memory readings. [Verification](VERIFICATION.md) records the final regression result, including the new streaming daily-halt check.
