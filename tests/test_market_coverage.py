"""Study orchestration and coverage tests; fixtures are not profitability evidence."""
import csv
import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from lab.autolearn import AutoLearner
from lab.coinbase_feed import CoinbaseClient
from lab.data import INTERVAL_MS, load_history
from lab.data_repair import aggregate_complete
from lab.evaluation import dataset_digest
from lab.paper_store import load_state, save_state
from lab.research import cost_signature
from lab.research_bundle import market_bundle
from lab.service import Service
from lab.study_plan import history_coverage, normalize_plan, study_days, unique_market_hours
from tests.test_adaptive import install

BASE = Path(__file__).resolve().parents[1]


def bars(count, step, end):
    return [{'ts':end-(count-i)*step, 'open':100., 'high':101., 'low':99.,
        'close':100., 'volume':1., 'quote_volume':100., 'trades':0} for i in range(count)]


class StudyPlanTests(unittest.TestCase):
    def test_limits_and_duplicate_timeframes_are_explicit(self):
        self.assertEqual(normalize_plan(['15m', '1h', '15m'], 2920, '15m'), (['15m', '1h'], 2920))
        self.assertEqual(normalize_plan(None, 1825, '6h'), (['6h'], 1825))
        self.assertEqual([study_days(iv, 2920) for iv in ('5m','15m','1h','6h')], [365,1825,2920,2920])
        for intervals, days in [([],1825), (['4h'],1825), ('1h',1825), (['1d'],1825),
                                (['1h'],True), (['1h'],365.5), (['1h'],2921)]:
            with self.subTest(intervals=intervals, days=days), self.assertRaises(ValueError):
                normalize_plan(intervals, days, '15m')

    def test_hours_union_timeframes_but_keep_distinct_coins_and_gaps(self):
        hour = 3600000
        def report(symbol, ranges):
            return {'symbol':symbol, 'data_selection':{'segments':[
                {'start_ts':a*hour, 'end_ts':b*hour} for a,b in ranges]}}
        reports = [report('BTC-USD', [(0,24),(30,48)]), report('BTC-USD', [(6,42)]),
                   report('ETH-USD', [(0,24),(30,48)])]
        self.assertEqual(unique_market_hours(reports), 48+42)
        self.assertEqual(unique_market_hours([{'symbol':'BTC-USD','data_hours':24},
            {'symbol':'BTC-USD','data_hours':48}, {'symbol':'ETH-USD','error':'missing'}]), 48)

    def test_report_distinguishes_requested_effective_and_observed_history(self):
        end = 1800000000000//900000*900000
        coverage = history_coverage(bars(96,900000,end), '15m', 2920, end)
        self.assertEqual(coverage['requested_days'], 2920)
        self.assertEqual(coverage['effective_days'], 1825)
        self.assertTrue(coverage['capped'])
        self.assertEqual(coverage['available_span_days'], 1)
        self.assertAlmostEqual(coverage['coverage_pct'], 100/1825)


class MultiStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = Service(BASE, self.root/'test.sqlite3', self.root/'data')
        self.a = self.service.autolearn
        self.settings = dict(self.service.agent.settings)
        products = patch.object(self.service.agent.client, 'products', return_value=[{
            'id':s, 'base_currency':s[:-4], 'quote_currency':'USD', 'status':'online'}
            for s in ('BTC-USD','ETH-USD')])
        self.products = products.start()
        self.addCleanup(products.stop)

    def tearDown(self):
        self.a.stop()
        self.service.agent.stop()
        self.temp.cleanup()

    def history(self, symbol, interval, days, end_ms):
        step = 86400000 if interval == '1d' else INTERVAL_MS[interval]
        return bars(30 if interval == '1d' else 3000, step, end_ms//step*step)

    def learned(self, rows, symbol, settings, *args, **kwargs):
        step = INTERVAL_MS[settings['decision_interval']]
        return {'symbol':symbol, 'interval':settings['decision_interval'], 'validated':False,
            'historical_examples':3, 'cost_signature':cost_signature(settings),
            'data_quality':{'start_ts':rows[0]['ts'], 'end_ts':rows[-1]['ts'], 'rows':len(rows)},
            'data_hours':len(rows)*step/3600000,
            'data_selection':{'segments':[{'start_ts':rows[0]['ts'], 'end_ts':rows[-1]['ts']+step}]},
            'replay':{'test_end_ts':rows[-1]['ts']+step}, 'rejection_reasons':['Fixture only']}

    def study_fixture(self, intervals):
        with patch.object(self.a.downloader, '_history', side_effect=self.history), patch(
                'lab.autolearn.learn_history', side_effect=self.learned):
            self.a.study(['BTC-USD'], self.settings, intervals=intervals)

    def test_secondary_only_study_cannot_postpone_primary_review(self):
        self.study_fixture(['6h'])
        self.assertTrue(self.a._needs_review(['BTC-USD'], self.settings))

    def test_primary_review_checks_its_report_scope_deadline_and_profile(self):
        self.study_fixture(['15m','6h'])
        primary, secondary = self.a.state['results']
        self.assertFalse(self.a._needs_review(['BTC-USD'], self.settings))
        for changed in ({'review_scope':'old'}, {'next_review_at':0}, {'validated':True}):
            with self.subTest(changed=changed), patch.dict(primary, changed):
                self.assertTrue(self.a._needs_review(['BTC-USD'], self.settings))
        with patch.dict(primary, {'validated':True}):
            install(self.a.db_path, self.settings)
            self.assertFalse(self.a._needs_review(['BTC-USD'], self.settings))
        with patch.dict(self.a.state, {'results':[secondary]}):
            self.assertTrue(self.a._needs_review(['BTC-USD'], self.settings))
        with patch.dict(self.a.state, {'practice_history_days':2920}):
            self.assertTrue(self.a._needs_review(['BTC-USD'], self.settings))

    def test_api_saves_selected_plan_and_rejects_invalid_plan_before_fee_change(self):
        for payload in ({'intervals':[]}, {'history_days':2921}, {'intervals':['1h'],'history_days':True}):
            code, _, _ = self.service.handle('POST','/api/learning/practice', body={
                'symbols':['BTC'], 'fee_rate':.001, **payload}, headers={'Content-Type':'application/json'})
            self.assertEqual(code, 400)
            self.assertEqual(self.service.agent.settings, self.settings)
        with patch.object(self.a, '_run_history') as run:
            code, _, _ = self.service.handle('POST','/api/learning/practice', body={
                'symbols':['BTC'], 'intervals':['15m','1h','6h'], 'history_days':2920},
                headers={'Content-Type':'application/json'})
            self.assertEqual(code, 202)
            self.a.worker.join(5)
            self.assertEqual(run.call_args.args[2:], (['15m','1h','6h'],2920))
        restored = AutoLearner(self.a.db_path, self.root/'data', self.a.agent, self.a.research_manager)
        self.assertEqual(restored.status()['practice_intervals'], ['15m','1h','6h'])
        self.assertEqual(restored.status()['history_days'], 2920)
        self.assertFalse(self.service.agent.runtime['running'])

    def test_independent_models_coverage_failure_continuation_and_saved_results(self):
        def download(symbol, interval, *args, **kwargs):
            if (symbol,interval) == ('ETH-USD','1h'):
                raise ValueError('Fixture gap')
            return self.history(symbol,interval,*args,**kwargs)
        with patch.object(self.a.downloader,'_history',side_effect=download) as history, \
                patch('lab.autolearn.learn_history',side_effect=self.learned) as learn:
            reports = self.a.study(['BTC-USD','ETH-USD'], self.settings,
                intervals=['15m','1h','6h'], history_days=2920)
            self.assertEqual(len(reports),6)
            self.assertEqual(learn.call_count,5)
            self.assertEqual(len({r['fingerprint'] for r in reports if 'fingerprint' in r}),5)
            self.assertEqual([c.args[2] for c in history.call_args_list if c.args[0]=='BTC-USD'],
                [1825,1855,2920,2950,2920,2950])
            self.assertIn('Fixture gap',reports[4]['error'])
            self.assertNotIn('error',reports[5])
            self.assertEqual(self.a.status()['completed_studies'],6)
            self.assertEqual(self.a.status()['completed_markets'],2)
            self.assertEqual(reports[0]['history_request']['effective_days'],1825)
            # An automatic single-timeframe review must not discard other studies.
            self.a.study(['BTC-USD'],self.settings)
        self.assertEqual(len(self.a.status()['results']),6)
        self.assertEqual(len(self.a.export()['results']),6)

    def test_another_timeframe_uses_existing_reviewed_price_boundary(self):
        with patch.object(self.a.downloader,'_history',side_effect=self.history), \
                patch('lab.autolearn.learn_history',side_effect=self.learned) as learn:
            reports = self.a.study(['BTC-USD'], self.settings, intervals=['15m','1h'])
        self.assertGreaterEqual(learn.call_args_list[1].kwargs['reviewed_through_ts'],
            reports[0]['replay']['test_end_ts'])

    def test_secondary_interval_cannot_replace_or_delete_forward_profile(self):
        profile = install(self.a.db_path,self.settings)
        secondary = {**self.settings,'decision_interval':'1h'}
        for validated in (False,True):
            self.a._install({'symbol':'BTC-USD','interval':'1h','validated':validated,
                'cost_signature':cost_signature(secondary)},'secondary')
            self.assertEqual(load_state(self.a.db_path,'adaptive_profile_BTC-USD'),profile)
        self.a.state['results'] = [{'symbol':'BTC-USD','interval':iv} for iv in ('15m','1h','6h')]
        save_state(self.a.db_path,'adaptive_paper_BTC-USD',{'fingerprint':profile['fingerprint'],'forward_trades':7})
        self.assertEqual(self.a.status()['active_markets'],['BTC-USD'])
        self.assertEqual(self.a.status()['forward_learning_trades'],7)

    def test_six_hour_studies_cannot_install_a_forward_model(self):
        profile = install(self.a.db_path,self.settings)
        with self.assertRaises(ValueError):
            self.service.agent.configure({'decision_interval':'6h'})
        with patch.dict(self.service.agent.settings,{'decision_interval':'6h'}):
            self.a._install({'symbol':'BTC-USD','interval':'6h','validated':True,
                'cost_signature':cost_signature(self.service.agent.settings)},'six-hour-study')
        self.assertEqual(load_state(self.a.db_path,'adaptive_profile_BTC-USD'),profile)

    def test_timeframe_checkpoints_survive_other_studies_and_restart(self):
        seen = []
        def interrupted(rows,symbol,settings,*args,checkpoint,**kwargs):
            seen.append(settings['decision_interval'])
            if settings['decision_interval']=='1h':
                checkpoint['save'](0,{'completed':'candidate'})
                raise InterruptedError('Fixture stop')
            return self.learned(rows,symbol,settings)
        with patch.object(self.a.downloader,'_history',side_effect=self.history), \
                patch('lab.autolearn.learn_history',side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                self.a.study(['BTC-USD'], self.settings, intervals=['15m','1h'])
        job = load_state(self.a.db_path,'learning_job_BTC-USD_1h')
        restored = AutoLearner(self.a.db_path,self.root/'data',self.a.agent,self.a.research_manager)
        def resumed(rows,symbol,settings,*args,checkpoint,**kwargs):
            self.assertEqual(settings['decision_interval'],'1h')
            self.assertEqual(checkpoint['load'](0),{'completed':'candidate'})
            return self.learned(rows,symbol,settings)
        with patch.object(restored.downloader,'_history',side_effect=self.history), \
                patch('lab.autolearn.learn_history',side_effect=resumed) as learn:
            restored.study(['BTC-USD'],self.settings,intervals=['15m','1h'])
            self.assertEqual(learn.call_count,1)
        self.assertIsNone(load_state(self.a.db_path,'learning_job_BTC-USD_1h'))
        self.assertIsNone(load_state(self.a.db_path,'learning_candidate_'+job['fingerprint']+'_0'))
        self.assertEqual(len(restored.status()['results']),2)

    def test_history_length_invalidates_only_its_timeframe_job(self):
        hourly = {**self.settings,'decision_interval':'1h'}
        old = self.a._job('BTC-USD',hourly,1095)
        other = self.a._job('BTC-USD',self.settings,1825)
        new = self.a._job('BTC-USD',hourly,2920)
        self.assertNotEqual(old['scope'],new['scope'])
        self.assertEqual(load_state(self.a.db_path,'learning_job_BTC-USD'),other)

    def test_automatic_study_retains_selected_longer_history(self):
        self.a.state['practice_history_days'] = 2920
        hourly = {**self.settings,'decision_interval':'1h'}
        with patch.object(self.a.downloader,'_history',side_effect=self.history) as history, \
                patch('lab.autolearn.learn_history',side_effect=self.learned):
            reports = self.a.study(['BTC-USD'],hourly)
        self.assertEqual(history.call_args_list[0].args[2],2920)
        self.assertEqual(reports[0]['history_request']['effective_days'],2920)

    def test_unavailable_product_skips_requests_and_metadata_failure_is_reported(self):
        self.products.return_value = [dict(self.products.return_value[1])]
        with patch.object(self.a.downloader,'_history',side_effect=self.history) as history, \
                patch('lab.autolearn.learn_history',side_effect=self.learned):
            reports = self.a.study(['BTC-USD','ETH-USD'],self.settings)
            self.assertIn('not currently an available',reports[0]['error'])
            self.assertEqual({c.args[0] for c in history.call_args_list},{'ETH-USD'})
            self.products.side_effect = TimeoutError('metadata offline')
            reports = self.a.study(['BTC-USD'],self.settings,retry_failed=True)
            self.assertEqual(reports[0]['market_data']['product_check']['status'],'unavailable')
            self.assertFalse(reports[0]['market_data']['synthetic_fallback'])


class HistoryCacheTests(unittest.TestCase):
    def test_shorter_download_preserves_older_candles_and_exact_report_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            service = Service(BASE,root/'test.sqlite3',root/'data')
            a = service.autolearn
            end = 1800000000000//INTERVAL_MS['6h']*INTERVAL_MS['6h']
            rows = bars(3004,INTERVAL_MS['6h'],end)
            cache = a.downloader.data_dir/'history'
            cache.mkdir(parents=True)
            path = cache/'BTC-USD_6h.csv'
            with path.open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            with patch.object(a.downloader.client,'candles',side_effect=AssertionError('already cached')):
                short = a.downloader._history('BTC-USD','6h',365,end_ms=end)
            self.assertEqual(len(short),365*4)
            self.assertEqual(load_history(path),rows)
            a.state['results']=[{'symbol':'BTC-USD','interval':'6h','data_quality':{
                'start_ts':rows[0]['ts'],'end_ts':rows[-1]['ts'],'rows':len(rows)},
                'data_sha256':dataset_digest(rows),'history_request':{'requested_days':1825}}]
            content, name = market_bundle(a,'BTC-USD','6h')
            self.assertEqual(name,'BTC-USD_6h_learning-data.zip')
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                manifest=json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['rows'],3004)
                self.assertEqual(manifest['history_request']['requested_days'],1825)

    def test_six_hour_feed_and_aggregation_do_not_invent_missing_subcandles(self):
        step=INTERVAL_MS['6h']; end=1800000000000//step*step
        client=CoinbaseClient()
        with patch.object(client,'_get',return_value=[[int((end-step)/1000),99,101,100,100,1]]) as request:
            rows=client.candles('BTC-USD','6h',limit=1,end_ms=end)
        self.assertEqual(request.call_args.args[1]['granularity'],21600)
        self.assertEqual(rows[0]['ts'],end-step)
        source=bars(48,900000,end)
        result=aggregate_complete(source,900000,step,end-2*step,end)
        self.assertEqual(len(result),2)
        result=aggregate_complete(source[:5]+source[6:],900000,step,end-2*step,end)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['ts'],end-step)


if __name__ == '__main__':
    unittest.main()
