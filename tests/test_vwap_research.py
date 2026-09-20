"""Synthetic fixtures verify causality/accounting, never profitability."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.continuous import DEFAULTS
from lab.execution import simulate
from lab.paper_store import init_continuous_db, load_state, save_state
from lab.vwap_research import (MINUTE, Moments, build_vwap_features, price_levels,
    run_vwap_research, validate_minute_rows, VwapResearchManager)


def minute_rows(n=4320):
    start = 1609459200000
    rows = []
    for i in range(n):
        price = 100+2*math.sin(i/37)+.4*math.cos(i/7)
        rows.append({'ts': start+i*MINUTE, 'open': price-.02, 'high': price+.1,
            'low': price-.1, 'close': price, 'volume': 10+i%11})
    return rows


def execution_case(path, fee=0., slip=0., daily_loss_limit=None):
    rows = [{'ts': 1609459200000+i*MINUTE, 'open': 100., 'high': 100.1,
             'low': 99.9, 'close': 100., 'volume': 10.} for i in range(241+len(path))]
    for index, item in enumerate(path, 241):
        rows[index].update(item)
    features = [None]*len(rows)
    features[240] = {'_atr': 1., '_close': 100., 'stop': 99., 'target1': 102., 'target2': 103.}
    params = {'family': 'vwap_test', 'direction': 'LONG', 'stop_atr': 1., 'rr2': 3.,
              'max_gap_atr': 10., 'max_cost_r': 10., 'max_notional_fraction': 1., 'time_stop_hours': 4.}
    return simulate(rows, features, 240, len(rows), 500., .01, fee, slip, params,
        bar_interval_ms=MINUTE, daily_loss_limit=daily_loss_limit,
        signal_evaluator=lambda f, p: (1., None), level_provider=price_levels)


class VwapResearchTests(unittest.TestCase):
    def test_divergence_uses_confirmed_extremes_and_expires(self):
        rows = minute_rows()
        for r in rows:
            r.update(open=99.9, high=100.2, low=99.8, close=100., volume=10.)
        first, second = 1440+160, 1440+185
        rows[first].update(open=97., high=97.1, low=95., close=96.)
        rows[second].update(open=96., high=96.1, low=94., close=95., volume=1.)
        for r in rows[first+1:second]:
            r['volume'] = 50.
        rows[1440+209].update(open=99.6, high=99.7, low=99.4, close=99.5)
        features, _ = build_vwap_features(rows)
        self.assertFalse(features[1440+179]['delta_divergence'])
        self.assertTrue(features[1440+209]['delta_divergence'])
        self.assertEqual(features[1440+209]['divergence']['confirmed_ts'], rows[second+2]['ts']+MINUTE)
        self.assertFalse(features[1440+239]['delta_divergence'])

    def test_weighted_population_variance(self):
        m = Moments()
        m.add(10., 1.)
        m.add(12., 3.)
        self.assertAlmostEqual(m.mean, 11.5)
        self.assertAlmostEqual(m.sigma, math.sqrt(.75))

    def test_completed_bars_and_pivots_are_prefix_invariant(self):
        rows = minute_rows()
        full, _ = build_vwap_features(rows)
        prefix, _ = build_vwap_features(rows[:3023])
        self.assertEqual(prefix, full[:3023])
        modified = copy.deepcopy(rows)
        for r in modified[3023:]:
            for k in ('open', 'high', 'low', 'close'):
                r[k] *= 3
            r['volume'] *= 1000
        changed, _ = build_vwap_features(modified)
        self.assertEqual(changed[:3023], prefix)
        for i, f in enumerate(full):
            if f:
                self.assertEqual(f['known_at_ts'], rows[i]['ts']+MINUTE)
                self.assertEqual(f['known_at_ts'] % (30*MINUTE), 0)
                if f['divergence']:
                    self.assertLessEqual(f['divergence']['confirmed_ts'], f['known_at_ts'])
                    self.assertGreaterEqual(f['divergence']['confirmed_ts'], f['divergence']['ts']+3*MINUTE)

    def test_gap_invalidates_session_and_previous_day_profile(self):
        rows = minute_rows(4*1440)
        del rows[1440+300]
        features, _ = build_vwap_features(rows)
        start = rows[0]['ts']
        self.assertFalse(any(f for r, f in zip(rows, features) if start+DAY_PLUS_GAP <= r['ts'] < start+2*86400000))
        for r, f in zip(rows, features):
            if f and start+2*86400000 <= r['ts'] < start+3*86400000:
                self.assertFalse(f['profile_touch'])

    def test_input_rejects_coarser_future_duplicate_and_invalid_prices(self):
        rows = minute_rows()
        self.assertTrue(validate_minute_rows(rows)['valid'])
        coarser = minute_rows(3000)
        for i, r in enumerate(coarser):
            r['ts'] = rows[0]['ts']+i*5*MINUTE
        with self.assertRaisesRegex(ValueError, 'Coarser'):
            validate_minute_rows(coarser)
        for mutate in (lambda x: x[10].update(ts=x[9]['ts']),
                       lambda x: x[10].update(high=1.),
                       lambda x: x[10].update(volume=float('nan')),
                       lambda x: x[-1].update(ts=4102444800000)):
            bad = copy.deepcopy(rows)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_minute_rows(bad)

    def test_partial_targets_charge_every_fee_and_reconcile(self):
        m, trades = execution_case([{'high': 102.5, 'close': 102.},
                                    {'open': 102., 'low': 101.5, 'high': 104., 'close': 103.}], .001, .0005)
        t = trades[0]
        q = t['qty_initial']
        expected_gross = q*.5*(102*(1-.0005)-t['entry']) + q*.5*(103*(1-.0005)-t['entry'])
        expected_fees = .001*q*(t['entry']+.5*102*(1-.0005)+.5*103*(1-.0005))
        self.assertAlmostEqual(t['gross_pnl'], expected_gross)
        self.assertAlmostEqual(t['fees_paid'], expected_fees)
        self.assertAlmostEqual(t['pnl'], expected_gross-expected_fees)
        self.assertAlmostEqual(m['ending_balance'], 500+t['pnl'])
        self.assertEqual(t['entry_ts'], 1609459200000+241*MINUTE)
        self.assertEqual(len(t['partial_fills']), 1)
        self.assertEqual(t['review']['path_basis'], 'unavailable')

    def test_two_targets_same_bar_split_instead_of_crediting_full_second_target(self):
        m, trades = execution_case([{'high': 104., 'close': 103.}])
        self.assertAlmostEqual(trades[0]['r_multiple'], 2.5)
        self.assertAlmostEqual(m['net_pnl'], 12.5)

    def test_stop_first_even_when_both_targets_touched(self):
        _, trades = execution_case([{'low': 98., 'high': 104.}])
        self.assertAlmostEqual(trades[0]['r_multiple'], -1.)
        self.assertNotIn('partial_fills', trades[0])

    def test_known_opening_target_cross_precedes_later_stop(self):
        _, trades = execution_case([{}, {'open': 104., 'low': 98., 'high': 105.}])
        self.assertEqual(trades[0]['reason'], 'TARGET2')
        self.assertAlmostEqual(trades[0]['r_multiple'], 2.5)
        _, trades = execution_case([{}, {'open': 102.1, 'low': 98., 'high': 102.5}])
        self.assertEqual(trades[0]['reason'], 'STOP')
        self.assertAlmostEqual(trades[0]['r_multiple'], .5)

    def test_daily_loss_halt_uses_quantity_remaining_after_opening_targets(self):
        for opening, high in ((104., 105.), (102.1, 102.5)):
            with self.subTest(opening=opening):
                metrics, trades = execution_case([{}, {'open': opening, 'low': 98., 'high': high}],
                    daily_loss_limit=.006)
                self.assertGreater(trades[0]['pnl'], 0.)
                self.assertEqual(metrics['halted_utc_days'], 0)
        # An actual stop loss still pauses entries for the rest of the UTC day.
        metrics, trades = execution_case([{}, {'low': 98.}], daily_loss_limit=.006)
        self.assertLess(trades[0]['pnl'], 0.)
        self.assertEqual(metrics['halted_utc_days'], 1)

    def test_partial_then_stop_and_partial_then_end_reconcile(self):
        for last, reason, result_r in (({'open': 101., 'low': 98., 'high': 101.}, 'STOP', .5),
                                      ({'open': 101., 'low': 100., 'high': 101., 'close': 101.}, 'END', 1.5)):
            m, trades = execution_case([{'high': 102.1, 'close': 102.}, last])
            self.assertEqual(trades[0]['reason'], reason)
            self.assertAlmostEqual(trades[0]['r_multiple'], result_r)
            self.assertAlmostEqual(m['net_pnl'], sum(t['pnl'] for t in trades))

    def test_incomplete_open_account_does_not_invent_a_gap_exit(self):
        rows = minute_rows(400)
        features = [None]*len(rows)
        f = {'_atr': 10., '_close': rows[240]['close'], 'stop': 80., 'target1': 120., 'target2': 130.}
        features[240] = f
        rows[242:] = [dict(r, ts=r['ts']+MINUTE) for r in rows[242:]]
        params = {'family': 'fixture', 'stop_atr': 1., 'rr2': 3., 'max_gap_atr': 10.}
        m, trades = simulate(rows, features, 240, len(rows), 500., .01, 0, 0, params,
            bar_interval_ms=MINUTE, signal_evaluator=lambda f, p: (1, None), level_provider=price_levels)
        self.assertFalse(m['complete'])
        self.assertIsNone(m['net_pnl'])
        self.assertEqual(trades, [])

    def test_report_retains_all_variants_costs_and_no_trade_results(self):
        result = run_vwap_research(minute_rows(), 'BTC-USD', DEFAULTS)
        self.assertEqual(len(result['results']), 4)
        self.assertFalse(result['eligible_for_trading'])
        self.assertEqual(result['learning_updates'], 0)
        for variant in result['results']:
            for window in variant['windows'].values():
                for key in ('standard', 'higher_cost'):
                    a = window[key]
                    self.assertAlmostEqual(a['metrics']['net_pnl'], sum(t['pnl'] for t in a['trades']))
                    self.assertAlmostEqual(a['metrics']['gross_pnl']-a['metrics']['fees_paid'], a['metrics']['net_pnl'])
        json.dumps(result, allow_nan=False)

    def test_manager_persists_research_without_changing_models(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root)/'db.sqlite3'
            init_continuous_db(db)
            save_state(db, 'validated_profiles', {'BTC-USD': {'sentinel': True}})
            manager = VwapResearchManager(db, Path(root))
            with patch.object(manager, '_history', return_value=minute_rows()):
                manager.start(['BTC-USD'], 7, DEFAULTS)
                manager.worker.join(10)
            self.assertFalse(manager.worker.is_alive())
            self.assertEqual(manager.status()['status'], 'complete')
            self.assertEqual(load_state(db, 'validated_profiles', {}), {'BTC-USD': {'sentinel': True}})
            self.assertIn('trades', manager.export()['results'][0]['results'][0]['windows']['later']['standard'])
            self.assertNotIn('trades', manager.status()['results'][0]['results'][0]['windows']['later']['standard'])

    def test_api_uses_separate_cost_snapshot_and_existing_auth(self):
        from lab.service import Service
        with tempfile.TemporaryDirectory() as root:
            service = Service(Path(__file__).resolve().parents[1], Path(root)/'db.sqlite3', Path(root), token='test-token')
            self.assertEqual(service.handle('GET', '/api/vwap/status')[0], 401)
            headers = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'}
            original = dict(service.agent.settings)
            with patch.object(service.vwap, 'start') as start:
                response = service.handle('POST', '/api/vwap/start', body={'symbols': ['BTC-USD'], 'days': 30, 'fee_rate': .002}, headers=headers)
                self.assertEqual(response[0], 202)
                self.assertEqual(start.call_args.args[2]['fee_rate'], .002)
                self.assertEqual(service.agent.settings, original)
            for fee in (True, float('nan'), -.1, .03):
                response = service.handle('POST', '/api/vwap/start', body={'fee_rate': fee}, headers=headers)
                self.assertEqual(response[0], 400)


DAY_PLUS_GAP = 86400000+300*MINUTE
