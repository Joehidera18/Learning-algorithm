"""Dashboard payloads stay small while exact reports and finances remain available."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from lab.paper_store import save_state
from lab.service import Service

BASE = Path(__file__).resolve().parents[1]


class StudyReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = Service(BASE, root/'state.sqlite3', root/'data', token='test-private-access-token')
        self.headers = {'Authorization':'Bearer test-private-access-token'}
        self.report = {'symbol':'BTC-USD','interval':'15m','fingerprint':'fixture-15m',
            'validated':False,'historical_examples':20,'data_hours':24,
            'data_quality':{'rows':3000},'holdout':{'trades':2,'net_pnl':-1.,
                'feedback':{'large_fixture':'x'*100000}}, 'holdout_stressed':{'net_pnl':-2.},
            'holdout_trades':[{'pnl':2.,'reason':'TARGET'},{'pnl':-3.,'reason':'STOP'}],
            'model':{'private_training_state':'fixture'},
            'trade_reviews':{'cases':[{'details':'y'*100000}]},
            'data_selection':{'segments':[{'start_ts':0,'end_ts':86400000}]}}
        self.secondary = dict(self.report, interval='6h', fingerprint='fixture-6h', research_only=True)
        for report in (self.report,self.secondary):
            save_state(self.service.autolearn.db_path, 'learning_result_'+report['fingerprint'], report)
        self.service.autolearn.state['results'] = [
            {k:v for k,v in r.items() if k not in ('model','holdout_trades')}
            for r in (self.report,self.secondary)]

    def tearDown(self):
        self.service.autolearn.stop()
        self.service.agent.stop()
        self.temp.cleanup()

    def test_summary_keeps_finances_and_coverage_without_copying_large_details(self):
        before = copy.deepcopy(self.service.autolearn.state)
        code, result, _ = self.service.handle('GET','/api/learning/status',headers=self.headers)
        self.assertEqual(code,200)
        self.assertEqual(result['market_data_hours'],24)
        for summary in result['results']:
            self.assertTrue(summary['report_summary'])
            self.assertNotIn('trade_reviews',summary)
            self.assertNotIn('feedback',summary['holdout'])
            self.assertEqual(summary['trade_finances']['money_won'],2.)
            self.assertEqual(summary['trade_finances']['money_lost'],3.)
            self.assertEqual(summary['trade_finances']['net_pnl'],-1.)
        self.assertLess(len(json.dumps(result)), len(json.dumps(before))*.05)
        result['results'][0]['holdout']['net_pnl']=999
        self.assertEqual(self.service.autolearn.state,before)

    def test_details_require_authentication_and_exact_study_identity(self):
        query={'symbol':'BTC-USD','interval':'6h','fingerprint':'fixture-6h'}
        self.assertEqual(self.service.handle('GET','/api/learning/report',query=query)[0],401)
        code, detail, _ = self.service.handle('GET','/api/learning/report',query=query,headers=self.headers)
        self.assertEqual(code,200)
        self.assertEqual(detail['interval'],'6h')
        self.assertEqual(detail['trade_reviews'],self.secondary['trade_reviews'])
        self.assertFalse(detail['report_summary'])
        self.assertNotIn('model',detail)
        self.assertNotIn('holdout_trades',detail)
        for change in ({'interval':'1h'},{'fingerprint':'fixture-15m'},{'symbol':'ETH-USD'}):
            with self.subTest(change=change):
                self.assertEqual(self.service.handle('GET','/api/learning/report',
                    query={**query,**change},headers=self.headers)[0],400)

    def test_full_export_keeps_exact_models_cases_and_ledgers(self):
        self.assertEqual(self.service.autolearn.export()['results'],[self.report,self.secondary])
