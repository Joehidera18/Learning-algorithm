"""Generated paths test execution/accounting, never investment performance."""
import unittest

from lab.execution import simulate
from lab.strategy_lab import _default_levels
from strategies import load_strategy

MINUTE = 60_000


def run_path(levels=None, low=99.9, high=104., opening=100., fee=.001, slip=.0005):
    rows = [dict(ts=1609459200000 + i * MINUTE, open=100., high=100.1,
                 low=99.9, close=100., volume=10.) for i in range(242)]
    rows[241].update(open=opening, high=high, low=low, close=opening)
    features = [None] * len(rows)
    features[240] = dict(_atr=1., _close=100.)
    params = dict(load_strategy("trend_pullback_simple").params,
                  max_gap_atr=10., max_cost_r=10., min_net_rr=0.)
    return simulate(rows, features, 240, len(rows), 1000., .005, fee, slip, params,
                    bar_interval_ms=MINUTE, signal_evaluator=lambda f, p: (1., None),
                    level_provider=lambda f: levels if levels is not None else _default_levels(f, params))


class SingleTargetTests(unittest.TestCase):
    def test_default_target_opens_trade_and_full_exit_reconciles_costs(self):
        metrics, trades = run_path()
        self.assertEqual(metrics["signal_funnel"]["entries_opened"], 1)
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["reason"], "TARGET2")
        self.assertFalse(trade.get("partial_fills"))
        quantity = trade["qty_initial"]
        exit_price = 103. * (1 - .0005)
        expected_gross = quantity * (exit_price - trade["entry"])
        expected_fees = quantity * (exit_price + trade["entry"]) * .001
        self.assertAlmostEqual(trade["gross_pnl"], expected_gross)
        self.assertAlmostEqual(trade["fees_paid"], expected_fees)
        self.assertAlmostEqual(trade["pnl"], expected_gross - expected_fees)
        self.assertAlmostEqual(metrics["ending_balance"], 1000. + trade["pnl"])

    def test_ambiguous_single_target_bar_still_stops_first(self):
        _, trades = run_path(low=98., high=104., fee=0., slip=0.)
        self.assertEqual(trades[0]["reason"], "STOP")
        # The strategy's 30% notional cap makes actual risk $4.50 here.
        self.assertAlmostEqual(trades[0]["pnl"], -4.5)

    def test_malformed_or_already_passed_levels_remain_rejected(self):
        for levels in ((98.5, 103., 103., .5), (98.5, 102., 103., 0.),
                       (98.5, 103., 103., -0.1), (98.5, 103., 103., 1.),
                       (98.5, 103., 103., float("nan")),
                       (98.5, float("inf"), float("inf"), 0.),
                       (101., 103., 103., 0.), (98.5, 99., 99., 0.),
                       (98.5, 104., 103., .5)):
            with self.subTest(levels=levels):
                metrics, trades = run_path(levels=levels)
                self.assertEqual(trades, [])
                self.assertEqual(metrics["signal_funnel"]["entry_rejections"],
                                 {"invalid_or_passed_price_levels": 1})

    def test_distinct_partial_targets_keep_their_original_accounting(self):
        _, trades = run_path(levels=(98.5, 102., 103., .5), fee=0., slip=0.)
        trade = trades[0]
        self.assertEqual(len(trade["partial_fills"]), 1)
        self.assertAlmostEqual(trade["pnl"], trade["qty_initial"] * 2.5)


if __name__ == "__main__":
    unittest.main()
