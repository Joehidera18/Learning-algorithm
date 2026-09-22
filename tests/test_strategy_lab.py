"""Strategy-lab regressions use generated fixtures, never market performance claims."""
import copy
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lab.strategy_lab import attach_closed_context, attach_features, run_backtest, _summarize
from lab.service import Service, wsgi_application
from lab.website_lab import attach
from strategies import list_strategies, load_strategy, StrategySpec
from strategies.orb_15m import OpeningRange15m
from tests.test_equity_practice import stock_rows, stamp

BASE = Path(__file__).resolve().parents[1]
MINUTE = 60_000
HOUR = 60*MINUTE


def bar(ts, step=MINUTE, close=100.):
    return {"ts": ts, "end_ts": ts+step, "open": close, "high": close,
            "low": close, "close": close, "volume": 100.}


def opening_session(day=0, indices=(0, 1, 2, 3, 4), volume=100.):
    opening = day*86_400_000
    rows, features = [], []
    for i in indices:
        close = 9.5 if i < 3 else 10.2
        row = dict(bar(opening+i*5*MINUTE, 5*MINUTE, close), high=max(10., close), low=9.,
                   volume=volume, session=str(day), session_open_ts=opening,
                   session_close_ts=opening+390*MINUTE)
        rows.append(row)
        features.append({"_close": close, "_atr": 1.})
    return rows, features


class RegistryTests(unittest.TestCase):
    def test_all_strategies_load_with_independent_family_parameters(self):
        self.assertEqual(len(list_strategies()), 5)
        for name in list_strategies():
            strategy = load_strategy(name)
            self.assertEqual(strategy.name, name)
            self.assertEqual(strategy.params["family"], name)

    def test_cli_list_runs_without_market_downloads(self):
        import sys
        result = subprocess.run([sys.executable, 'run_strategy_lab.py', '--list'],
                                cwd=BASE, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), list_strategies())


class ContextTests(unittest.TestCase):
    def test_uses_only_the_latest_expected_closed_bar(self):
        decision = [bar(i*15*MINUTE, 15*MINUTE) for i in range(8)]
        hourly = [bar(i*HOUR, HOUR, 200.+i) for i in range(2)]
        attach_closed_context(decision, '15m', {'1h': hourly})
        self.assertFalse(decision[0]['mtf']['1h']['ready'])
        self.assertEqual(decision[4]['mtf']['1h']['close'], 200.)
        self.assertEqual(decision[7]['mtf']['1h']['close'], 201.)

    def test_missing_middle_and_trailing_bars_are_not_filled_forward(self):
        decision = [bar(i*MINUTE) for i in (59, 60, 119, 120, 179, 180, 239)]
        attach_closed_context(decision, '1m', {'1h': [bar(0, HOUR), bar(2*HOUR, HOUR)]})
        self.assertEqual([r['mtf']['1h']['ready'] for r in decision],
                         [True, True, False, False, True, True, False])

    def test_future_or_empty_context_is_unavailable(self):
        for frames in ({'1h': []}, {'1h': [bar(0, HOUR)]}):
            decision = [bar(0)]
            attach_closed_context(decision, '1m', frames)
            self.assertFalse(decision[0]['mtf']['1h']['ready'])

    def test_unsorted_or_duplicate_context_is_rejected(self):
        for rows in ([bar(HOUR, HOUR), bar(0, HOUR)], [bar(0, HOUR)]*2):
            with self.assertRaisesRegex(ValueError, 'ordered and unique'):
                attach_closed_context([bar(3*HOUR)], '1m', {'1h': rows})

    def test_stock_context_survives_holiday_weekend_and_early_close(self):
        context = stock_rows('1h', '2026-11-27T00:00:00Z', '2026-11-28T00:00:00Z')
        monday = stock_rows('5m', '2026-11-30T00:00:00Z', '2026-12-01T00:00:00Z')[:1]
        attach_closed_context(monday, '5m', {'1h': context})
        self.assertTrue(monday[0]['mtf']['1h']['ready'])
        self.assertEqual(monday[0]['mtf']['1h']['end_ts'], stamp('2026-11-27T18:00:00Z'))
        attach_closed_context(monday, '5m', {'1h': context[:-1]})
        self.assertFalse(monday[0]['mtf']['1h']['ready'])

    def test_stock_missing_intraday_context_is_unavailable_after_due_close(self):
        context = stock_rows('1h', '2026-09-18T00:00:00Z', '2026-09-19T00:00:00Z')
        decisions = stock_rows('5m', '2026-09-18T00:00:00Z', '2026-09-19T00:00:00Z')
        del context[1]
        attach_closed_context(decisions, '5m', {'1h': context})
        before = next(r for r in decisions if r['end_ts'] == stamp('2026-09-18T15:25:00Z'))
        after = next(r for r in decisions if r['end_ts'] == stamp('2026-09-18T15:30:00Z'))
        self.assertTrue(before['mtf']['1h']['ready'])
        self.assertFalse(after['mtf']['1h']['ready'])

    def test_indicators_reset_after_a_missing_decision_candle(self):
        for equity in (False, True):
            rows = stock_rows(moving=True) if equity else [dict(bar(i*MINUTE), high=101., low=99.) for i in range(800)]
            interval = '1h' if equity else '1m'
            del rows[300]
            features, _ = attach_features(rows, interval)
            self.assertIsNotNone(features[299])
            self.assertIsNone(features[300])
            self.assertIsNotNone(features[540])


class OpeningRangeTests(unittest.TestCase):
    def test_complete_range_then_first_break_only(self):
        rows, features = opening_session()
        strategy = OpeningRange15m()
        strategy.prepare(rows, features, '5m')
        self.assertFalse(features[2]['orb']['ready'])
        self.assertTrue(features[3]['orb']['ready'])
        self.assertTrue(features[3]['orb']['first_break'])
        self.assertFalse(features[4]['orb']['first_break'])
        self.assertEqual(strategy.signal(features[3], strategy.params), (None, 'relative_volume_not_ready'))

    def test_any_missing_opening_candle_invalidates_range(self):
        for missing in (0, 1, 2):
            with self.subTest(missing=missing):
                rows, features = opening_session(indices=tuple(i for i in range(5) if i != missing))
                strategy = OpeningRange15m()
                strategy.prepare(rows, features, '5m')
                self.assertFalse(features[-1]['orb']['ready'])
                self.assertEqual(strategy.signal(features[-1], strategy.params), (None, 'opening_range_not_ready'))

    def test_duplicate_or_partial_opening_bar_invalidates_range(self):
        for partial in (False, True):
            rows, features = opening_session()
            if partial:
                rows[1]['end_ts'] -= MINUTE
            else:
                rows.insert(1, dict(rows[0])); features.insert(1, dict(features[0]))
            OpeningRange15m().prepare(rows, features, '5m')
            self.assertFalse(features[-1]['orb']['ready'])

    def test_needs_twenty_complete_prior_opening_ranges_and_filters_news(self):
        rows, features = [], []
        for day in range(21):
            a, b = opening_session(day)
            rows.extend(a); features.extend(b)
        strategy = OpeningRange15m(); strategy.prepare(rows, features, '5m')
        self.assertIsNone(features[19*5+3]['orb']['rvol'])
        last = features[20*5+3]
        self.assertEqual(last['orb']['rvol'], 1.)
        self.assertEqual(strategy.signal(last, strategy.params), (70., None))
        last['news'] = {'ready': True, 'score': -1.}
        self.assertEqual(strategy.signal(last, strategy.params), (None, 'negative_news_filter'))

    def test_warmup_does_not_create_a_second_first_break(self):
        rows, features = opening_session()
        features[3] = None
        OpeningRange15m().prepare(rows, features, '5m')
        self.assertFalse(features[4]['orb']['first_break'])

    def test_unsupported_decision_interval_is_rejected(self):
        for interval in ('30m', '1h', '4h'):
            with self.assertRaisesRegex(ValueError, 'requires'):
                OpeningRange15m().prepare([], [], interval)


class FixtureStrategy(StrategySpec):
    name = 'generated_test_fixture'
    params = dict(StrategySpec.params, cooldown_minutes=0, max_cost_r=.8, min_net_rr=.8)

    def signal(self, *_):
        return 70., None

    def levels(self, *_):
        return 99., 101., 102., .5


class ReportTests(unittest.TestCase):
    def fixture(self, gap=False):
        rows = []
        for i in range(1000):
            rows.append(dict(bar((i+int(gap and i >= 851))*MINUTE),
                             high=100.2 if gap and i == 850 else 102., low=99.8))
        return rows

    def run_report(self, rows, **kwargs):
        return run_backtest(FixtureStrategy(), rows, '1m',
                            {'fee_rate': .0001, 'slippage_rate': .0001, 'risk_per_trade': .005}, **kwargs)

    def test_open_position_gap_makes_both_results_unknown_and_ineligible(self):
        result = self.run_report(self.fixture(gap=True))
        self.assertFalse(result['eligible_for_bot'])
        for key in ('later', 'later_higher_cost'):
            account = result[key]
            self.assertFalse(account['complete'])
            self.assertGreater(account['trades'], 20)
            self.assertIsNone(account['net_pnl'])
            self.assertIsNone(account['mean_r'])
            self.assertEqual(account['unresolved_positions'], 1)
            self.assertIn('missing', account['incomplete_reason'])

    def test_complete_generated_fixture_can_pass_both_tests(self):
        result = self.run_report(self.fixture())
        self.assertTrue(result['eligible_for_bot'])
        self.assertTrue(result['later']['complete'])
        self.assertEqual(result['report_version'], 2)

    def test_window_end_loss_is_included_without_inflating_closed_trade_count(self):
        trades = [{'reason': 'T2', 'pnl': 5., 'risk_dollars': 1.} for _ in range(20)]
        trades.append({'reason': 'END', 'pnl': -200., 'risk_dollars': 1.})
        metrics = {'complete': True, 'net_pnl': -100.}
        summary = _summarize(metrics, trades, 'later')
        self.assertEqual(summary['net_pnl'], -100.)
        self.assertEqual(summary['closed_net_pnl'], 100.)
        self.assertEqual(summary['trades'], 20)
        self.assertEqual(summary['window_end_exits'], 1)
        with patch('lab.strategy_lab.simulate', return_value=(metrics, trades)):
            self.assertFalse(self.run_report(self.fixture())['eligible_for_bot'])

    def test_a_single_profitable_stress_trade_is_insufficient(self):
        winners = [{'reason': 'T2', 'pnl': 5., 'risk_dollars': 1.} for _ in range(20)]
        with patch('lab.strategy_lab.simulate', side_effect=[
                ({'complete': True, 'net_pnl': 100.}, winners),
                ({'complete': True, 'net_pnl': 100.}, winners),
                ({'complete': True, 'net_pnl': 5.}, winners[:1])]):
            self.assertFalse(self.run_report(self.fixture())['eligible_for_bot'])

    def test_stock_coverage_does_not_count_closed_exchange_hours_as_gaps(self):
        rows = stock_rows()
        result = run_backtest(FixtureStrategy(), rows, '1h', {'fee_rate': .0001, 'slippage_rate': .0001},
                              stock_execution=True, close_at_session_end=True)
        self.assertEqual(result['coverage']['coverage_pct'], 100.)
        self.assertEqual(result['coverage']['missing_candles'], 0)

    def test_future_prices_do_not_change_earlier_features(self):
        rows = stock_rows(moving=True)
        original, _ = attach_features(rows, '1h')
        changed = copy.deepcopy(rows)
        for row in changed[500:]:
            for key in ('open', 'high', 'low', 'close'):
                row[key] *= 2
        updated, _ = attach_features(changed, '1h')
        self.assertEqual(original[:500], updated[:500])


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Service.__new__(Service)
        self.service.base_dir = BASE
        self.service.data_dir = Path(self.temp.name)
        self.service.token = 'local-test-token'
        attach(self.service)
        self.jobs = self.service.strategy_lab
        self.jobs.worker.join(timeout=2)
        self.jobs.resume = Mock()  # No downloads or market jobs in route tests.
        self.app = wsgi_application(self.service)

    def tearDown(self):
        self.jobs.shutdown()
        self.temp.cleanup()

    def request(self, path, method='GET', token=None, body=None, content_type='application/json'):
        raw = json.dumps(body).encode() if body is not None else b''
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'CONTENT_TYPE': content_type,
               'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': io.BytesIO(raw)}
        if token is not None:
            env['HTTP_AUTHORIZATION'] = 'Bearer '+token
        status = []
        payload = b''.join(self.app(env, lambda code, headers: status.append(int(code.split()[0]))))
        return status[0], payload

    def test_status_start_export_and_unknown_lab_paths_require_token(self):
        for token in (None, 'wrong'):
            for path, method in (('status', 'GET'), ('start', 'POST'), ('export', 'GET'), ('unknown', 'GET')):
                with self.subTest(path=path, token=token):
                    self.assertEqual(self.request('/api/strategy-lab/'+path, method, token, {})[0], 401)
        self.assertFalse(self.jobs.status()['jobs'])

    def test_authorized_catalog_queue_and_public_page_work(self):
        status, payload = self.request('/api/strategy-lab/status', token=self.service.token)
        self.assertEqual(status, 200)
        self.assertIn('orb_15m', json.loads(payload)['catalog']['strategies'])
        status, _ = self.request('/api/strategy-lab/start', 'POST', self.service.token, {'context': ''})
        self.assertEqual(status, 202)
        self.assertEqual(len(self.jobs.status()['jobs']), 1)
        for path in ('/strategy-lab', '/static/strategy-lab.js'):
            self.assertEqual(self.request(path)[0], 200)

    def test_shared_json_validation_still_runs(self):
        self.assertEqual(self.request('/api/strategy-lab/start', 'POST', self.service.token, {}, 'text/plain')[0], 415)
        self.assertEqual(self.request('/api/strategy-lab/start', 'POST', self.service.token, [])[0], 400)

    def test_bad_settings_are_rejected_before_queue_or_download(self):
        for values in ({'decision': '1h'}, {'symbol': '../SPY'}, {'days': True},
                       {'context': ['missing']}, {'news': 'false'}, {'provider': 'missing'}):
            with self.subTest(values=values):
                self.assertEqual(self.request('/api/strategy-lab/start', 'POST', self.service.token, values)[0], 400)
        self.assertFalse(self.jobs.status()['jobs'])

    def test_legacy_results_cannot_remain_eligible(self):
        created = self.jobs.start({})
        self.jobs._patch(created['id'], status='complete', message='old result',
                         result={'eligible_for_bot': True, 'later': {'complete': True}})
        result = self.jobs.get(created['id'])['result']
        self.assertFalse(result['eligible_for_bot'])
        self.assertTrue(result['requires_rerun'])

    def test_queued_stock_run_saves_a_current_report(self):
        created = self.jobs.start({'context': ''})
        job = self.jobs.get(created['id'])
        rows = stock_rows('5m', '2026-07-21T00:00:00Z', '2026-09-19T00:00:00Z', moving=True)
        with patch('lab.equity_data.EquityData.history', return_value={'rows': rows}):
            self.jobs._run({'id': job['id'], 'request_json': json.dumps(job['request'])})
        finished = self.jobs.get(job['id'])
        self.assertEqual(finished['status'], 'complete', finished['message'])
        self.assertEqual(finished['result']['report_version'], 2)
        report = json.loads(Path(finished['result']['report_path']).read_text())
        self.assertEqual(report['strategy'], 'orb_15m')
        self.assertEqual(report['coverage']['coverage_pct'], 100.)


if __name__ == '__main__':
    unittest.main()
