"""Generated fixtures test timing/accounting, never historical profitability."""
import copy
import unittest
from unittest.mock import patch

from strategies import load_strategy
from strategies.intraday_candidates import _session_contexts, MINUTE, STEP
from lab.strategy_lab import run_backtest
from lab.execution import simulate

NAMES = ("orb_5m_rvol", "orb_15m_retest", "vwap_reclaim")
DAY = 86_400_000


def candles(days=16):
    rows = []
    for day in range(days):
        opening = day * DAY
        for i in range(78):
            ts = opening + i * STEP
            rows.append({"ts": ts, "end_ts": ts + STEP,
                "next_ts": ts + STEP if i < 77 else (day + 1) * DAY,
                "session": str(day), "session_open_ts": opening,
                "session_close_ts": opening + 390 * MINUTE, "asset_class": "equity",
                "open": 9.5, "close": 9.6, "low": 9., "high": 10., "volume": 100.})
    return rows


def features(rows):
    return [{"_atr": .5, "_close": r["close"]} for r in rows]


def at(rows, day, bar, **values):
    row = rows[day * 78 + bar]
    row.update(values)
    row["high"] = max(row["high"], row["open"], row["close"])
    row["low"] = min(row["low"], row["open"], row["close"])


class IntradayCandidatesTests(unittest.TestCase):
    def prepared(self, name, rows):
        spec = load_strategy(name)
        f = features(rows)
        spec.prepare(rows, f, "5m")
        return spec, f

    def test_rvol_uses_fourteen_prior_complete_sessions_not_today(self):
        rows = candles()
        at(rows, 14, 0, volume=1000.)
        ctx = list(_session_contexts(rows))[14 * 78]
        self.assertEqual(ctx["prior_sessions"], 14)
        self.assertEqual(ctx["rvol5"], 10.)
        self.assertIsNone(list(_session_contexts(rows))[13 * 78]["rvol5"])

    def test_missing_opening_or_intraday_bar_blocks_session_and_resets_history(self):
        for missing in (14 * 78, 14 * 78 + 2):
            rows = candles()
            del rows[missing]
            contexts = list(_session_contexts(rows))
            after = [c for c in contexts if c["row"]["session"] == "14" and c["elapsed"] >= 20]
            self.assertTrue(all(not c["valid"] and c["rvol5"] is None for c in after))
            next_day = next(c for c in contexts if c["row"]["session"] == "15")
            self.assertEqual(next_day["prior_sessions"], 0)

    def test_missing_entire_session_cannot_be_hidden_in_rvol_baseline(self):
        rows = [r for r in candles() if r["session"] != "5"]
        self.assertIsNone(next(c for c in _session_contexts(rows)
                              if c["row"]["session"] == "14")["rvol5"])

    def test_future_candles_never_change_prefix_signals_or_vwap(self):
        rows = candles()
        at(rows, 14, 0, volume=300.)
        at(rows, 14, 3, close=10.4)
        cut = 14 * 78 + 7
        later = copy.deepcopy(rows)
        for row in later[cut:]:
            row.update(close=100., high=105., low=1., volume=1e9)
        # Even a later gap in this same session cannot erase an earlier signal.
        del later[cut + 2]
        for name in NAMES:
            _, short = self.prepared(name, rows[:cut])
            _, full = self.prepared(name, later)
            self.assertEqual(short, full[:cut], name)

    def test_breakout_one_signal_and_single_target(self):
        rows = candles()
        at(rows, 14, 0, volume=200.)
        at(rows, 14, 1, close=10.2)
        at(rows, 14, 2, close=10.3)
        spec, f = self.prepared("orb_5m_rvol", rows)
        signals = [i for i in range(14 * 78, 15 * 78) if spec.signal(f[i], spec.params)[0] is not None]
        self.assertEqual(signals, [14 * 78 + 1])
        stop, t1, t2, partial = spec.levels(f[signals[0]], spec.params)
        self.assertEqual(stop, 9.)
        self.assertAlmostEqual(t1, 12.6)
        self.assertEqual((t1, partial), (t2, 0.))

    def test_warmup_or_entry_rejection_cannot_create_second_signal(self):
        rows = candles()
        at(rows, 14, 0, volume=200.)
        for i in (1, 2, 3):
            at(rows, 14, i, close=10.2)
        f = features(rows)
        f[14 * 78 + 1] = None
        spec = load_strategy("orb_5m_rvol")
        spec.prepare(rows, f, "5m")
        self.assertEqual(spec.signal(f[14 * 78 + 2], spec.params)[1], "session_signal_already_used")

    def test_real_executor_enters_on_next_open_and_keeps_one_signal(self):
        rows = candles()
        at(rows, 14, 0, volume=200.)
        at(rows, 14, 1, close=10.2)
        at(rows, 14, 2, open=10.2, close=10.3, low=10.1, high=10.4)
        spec, f = self.prepared("orb_5m_rvol", rows)
        metrics, trades = simulate(rows=rows, features=f, start=240, end=len(rows),
            balance=1000., risk=.005, fee_rate=.0001, base_slip=.0001, params=spec.params,
            signal_evaluator=spec.signal, level_provider=lambda feat: spec.levels(feat, spec.params),
            stock_execution=True, close_at_session_end=True, bar_interval_ms=STEP)
        self.assertTrue(metrics["complete"])
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["entry_ts"], rows[14 * 78 + 2]["ts"])
        self.assertAlmostEqual(trades[0]["entry"], 10.2 * 1.0001)
        self.assertEqual(trades[0]["reason"], "STOP")

    def test_retest_needs_a_later_bar_and_expires_after_six(self):
        for age in (1, 6, 7):
            rows = candles()
            at(rows, 14, 3, open=10.1, low=10.1, close=10.3)
            for i in range(4, 3 + age):
                at(rows, 14, i, open=10.1, low=10.1, close=10.3)
            at(rows, 14, 3 + age, open=9.9, low=9.9, close=10.2)
            spec, f = self.prepared("orb_15m_retest", rows)
            self.assertIsNone(spec.signal(f[14 * 78 + 3], spec.params)[0])
            signal = f[14 * 78 + 3 + age]
            self.assertEqual(spec.signal(signal, spec.params)[0] is not None, age <= 6)
            if age <= 6:
                self.assertAlmostEqual(spec.levels(signal, spec.params)[0], 9.85)

    def test_vwap_reclaim_requires_two_below_then_bullish_break(self):
        rows = candles()
        at(rows, 14, 4, open=9.3, close=9.2, high=9.4, low=9.1)
        at(rows, 14, 5, open=9.3, close=9.25, high=9.45, low=9.15)
        at(rows, 14, 6, open=9.3, close=10.4, high=10.5, low=9.25)
        spec, f = self.prepared("vwap_reclaim", rows)
        self.assertIsNotNone(spec.signal(f[14 * 78 + 6], spec.params)[0])
        self.assertAlmostEqual(spec.levels(f[14 * 78 + 6], spec.params)[0], 9.05)
        at(rows, 14, 4, close=10.1)
        spec, f = self.prepared("vwap_reclaim", rows)
        self.assertIsNone(spec.signal(f[14 * 78 + 6], spec.params)[0])

    def test_cumulative_rvol_compares_same_minute_not_full_day(self):
        rows = candles()
        for i in range(6):
            at(rows, 14, i, volume=200.)
        ctx = list(_session_contexts(rows))[14 * 78 + 5]
        self.assertEqual(ctx["cumulative_rvol"], 2.)

    def test_session_vwap_resets_and_entry_window_stops_late_signals(self):
        rows = candles()
        at(rows, 14, 0, volume=200.)
        at(rows, 14, 18, close=10.3)  # 11:05 close is too late.
        spec, f = self.prepared("orb_5m_rvol", rows)
        self.assertEqual(spec.signal(f[14 * 78 + 18], spec.params)[1], "outside_entry_window")
        ctx = list(_session_contexts(rows))[15 * 78]
        self.assertAlmostEqual(ctx["vwap"], (10. + 9. + 9.6) / 3)

    def test_incomplete_future_tail_does_not_invalidate_complete_prior_sessions(self):
        rows = candles()[:14 * 78 + 10]
        for name in NAMES:
            spec, f = self.prepared(name, rows)
            self.assertEqual(f[-1]["day_candidate"]["prior_sessions"], 14)
            self.assertTrue(spec.research_only)
            self.assertEqual(spec.supported_modes, ("day",))
            with self.assertRaisesRegex(ValueError, "requires 5m"):
                spec.prepare(rows, f, "1m")

    def test_positive_fixture_cannot_promote_research_candidate(self):
        rows = [{"ts": i * STEP, "open": 10., "high": 11., "low": 9.,
                 "close": 10., "volume": 100.} for i in range(1000)]
        metrics = {"complete": True, "net_pnl": 100., "return_pct": 10., "ending_balance": 1100.}
        trades = [{"reason": "TARGET", "pnl": 1., "risk_dollars": 1.} for _ in range(25)]
        spec = load_strategy("orb_5m_rvol")
        with patch.object(spec, "prepare"), patch("lab.strategy_lab.attach_features", return_value=([{}]*1000, {})), \
                patch("lab.strategy_lab.simulate", return_value=(metrics, trades)):
            report = run_backtest(spec, rows, "5m", {"fee_rate": .0001, "slippage_rate": .0005})
        self.assertGreater(report["later"]["trades"], 20)
        self.assertFalse(report["eligible_for_bot"])
        self.assertTrue(report["research_only"])
        self.assertEqual(report["strategy_rules"], list(spec.rules))
        self.assertEqual(report["strategy_parameters"]["family"], spec.name)


if __name__ == "__main__":
    unittest.main()
