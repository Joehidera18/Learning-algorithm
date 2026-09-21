"""Causality, restart and isolation checks. Fixtures are not market evidence."""
import copy
import json
import math
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from lab.continuous import DEFAULTS, ContinuousLearner
from lab.execution import simulate
from lab.exit_management import TRAILING_EXIT
from lab.experiments import run_experiment, retest_features, fixed_params, assess_pair, digest
from lab.experiment_jobs import ExperimentJobs, ExperimentHistory
from lab.experiment_planner import validate_plan, ai_plan, planner_context, built_in_plan
from lab.paper_store import init_continuous_db, db_connect
from lab.portfolio_risk import hourly_returns, correlation, related_risk
from lab.service import Service
from tests.test_execution import candles, features, PARAMS

BASE = Path(__file__).resolve().parents[1]
STEP = 900000


class ControlledExperimentTests(unittest.TestCase):
    def retest_path(self):
        rows = candles(270)
        fs = [None if i < 240 else {"regime":"BULL", "volume_z":1., "rsi":60.,
              "_atr":2., "breakout55":i == 240} for i in range(len(rows))]
        rows[240].update(open=100., high=101.2, low=100., close=101.)
        rows[241].update(open=100.4, high=100.8, low=100.1, close=100.6)
        return rows, fs

    def test_retest_is_later_causal_and_does_not_move_the_original_level(self):
        rows, fs = self.retest_path()
        p = fixed_params(DEFAULTS)
        result = retest_features(rows, fs, STEP, p)
        self.assertFalse(result[240]["breakout55"])
        self.assertTrue(result[241]["breakout55"])
        self.assertEqual(result[241]["_experiment_retest_level"], 100.2)
        self.assertEqual(result[:242], retest_features(rows[:242], fs[:242], STEP, p))
        self.assertTrue(fs[240]["breakout55"])
        self.assertFalse(fs[241]["breakout55"])

    def test_missing_or_invalidating_candle_clears_pending_retest(self):
        for kind in ("gap", "breach", "expiry"):
            rows, fs = self.retest_path()
            if kind == "gap":
                for row in rows[241:]: row["ts"] += STEP
            elif kind == "breach":
                rows[241]["low"] = 98.
            else:
                rows[253] = dict(rows[241], ts=rows[253]["ts"])
                for row in rows[241:253]: row.update(open=102., high=102.2, low=101.8, close=102.)
            result = retest_features(rows, fs, STEP, fixed_params(DEFAULTS))
            self.assertFalse(any(f and f["breakout55"] for f in result), kind)

    def test_trailing_stop_is_effective_only_in_the_next_candle(self):
        rows = candles(245)
        rows[241].update(open=100., high=103., low=99., close=102.8)
        rows[242].update(open=102.8, high=103., low=100.7, close=101.)
        fs = [f if i == 240 else None for i, f in enumerate(features(245))]
        with patch("lab.engine.evaluate_signal", return_value=(70,None)):
            m, trades = simulate(rows, fs, 240, len(rows), 500, .01, 0., 0.,
                dict(PARAMS, exit_policy=TRAILING_EXIT), bar_interval_ms=STEP)
        t = trades[0]
        self.assertEqual(t["entry_ts"], rows[241]["ts"])
        self.assertEqual(t["trailing_active_ts"], rows[242]["ts"])
        self.assertEqual(t["exit_ts"], rows[242]["ts"])
        self.assertEqual(t["reason"], "TRAILING_STOP")
        self.assertAlmostEqual(t["exit"], 100.8)
        self.assertAlmostEqual(m["net_pnl"], t["pnl"])

    def test_zero_trades_are_not_an_improvement_and_checkpoint_reuse_is_exact(self):
        rows = candles(3100)
        saved = {}
        checkpoint = {"load": saved.get, "save": lambda k,v:saved.update({k:v})}
        first = run_experiment(rows, "FIXTURE-USD", "15m", "exit_rules", DEFAULTS, checkpoint=checkpoint)
        self.assertTrue(all(c["status"] == "insufficient_evidence" for c in first["comparisons"]))
        with patch("lab.experiments.simulate", side_effect=AssertionError("A completed account was replayed")):
            second = run_experiment(rows, "FIXTURE-USD", "15m", "exit_rules", DEFAULTS, checkpoint=checkpoint)
        self.assertEqual(first["variants"], second["variants"])
        self.assertFalse(first["eligible_for_trading"])
        self.assertEqual(len(saved), 16)

    def test_learning_seed_cannot_see_changed_evaluation_prices(self):
        rows = candles(3100)
        for i, row in enumerate(rows):
            v = 100+5*math.sin(i/12)+i*.002
            row.update(open=v, high=v+.8, low=v-.8, close=v+.1)
        a = run_experiment(rows, "FIXTURE-USD", "15m", "learning_control", DEFAULTS)
        modified = copy.deepcopy(rows)
        for row in modified[int(len(rows)*.7):]:
            for k in ("open","high","low","close"): row[k] *= 1.5
        b = run_experiment(modified, "FIXTURE-USD", "15m", "learning_control", DEFAULTS)
        self.assertEqual(a["seed"]["sha256"], b["seed"]["sha256"])
        self.assertLessEqual(a["seed"]["last_label_ts"], a["development_end_ts"])
        frozen = a["variants"][0]["windows"]["later"]
        self.assertEqual(frozen["standard"]["model_updates"], 0)
        self.assertEqual(frozen["higher_cost"]["model_updates"], 0)
        self.assertEqual(frozen["standard"]["model_sha256"], a["seed"]["sha256"])

    def test_reduced_losses_do_not_get_a_profitable_label(self):
        def account(net): return {"closed_trades":40,"metrics":{"complete":True,"net_pnl":net}}
        comparison = assess_pair(account(-20), account(-10), account(-30), account(-15))
        self.assertEqual(comparison["status"], "lower_loss_only")
        missing = account(10);missing["metrics"]["complete"] = False
        self.assertIsNone(assess_pair(account(0),missing,account(0),account(10))["net_difference"])


class ExperimentJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/"test.sqlite3"
        self.data = Path(self.tmp.name)/"data"
        init_continuous_db(self.db)
        self.manager = ExperimentJobs(self.db, self.data)

    def tearDown(self):
        self.manager.shutdown()
        self.tmp.cleanup()

    def enqueue(self, manager=None):
        manager = manager or self.manager
        with patch.object(manager, "resume"):
            result = manager.start({"symbol":"BTC-USD","interval":"15m","days":40,"recipes":["breakout_retest"]}, DEFAULTS)
        return manager.get(result["ids"][0])

    def test_duplicate_requests_and_export_preserve_the_original_costs(self):
        with patch("lab.experiment_jobs.time.time", return_value=1789952400):
            first, second = self.enqueue(), self.enqueue()
        self.assertEqual(first["id"],second["id"])
        self.assertEqual(self.manager.status()["total_jobs"],1)
        self.assertEqual(first["manifest"]["settings"]["fee_rate"], .004)
        self.assertIsNone(self.manager.get(first["id"], full=True)["result"])

    def test_restart_reuses_snapshot_and_completed_accounts(self):
        job = self.enqueue()
        rows = candles(3100, start=job["manifest"]["cutoff_ts"]-3100*STEP)
        original_patch = self.manager._patch
        account_progress = []

        def interrupt_after_one(ident, **kwargs):
            if kwargs.get("status") == "testing":
                account_progress.append(kwargs)
                if len(account_progress) == 2:
                    self.manager.stop_event.set()
            return original_patch(ident, **kwargs)

        with patch.object(ExperimentHistory, "_history", return_value=rows), patch.object(self.manager, "_patch", side_effect=interrupt_after_one):
            with self.assertRaises(InterruptedError):
                self.manager._run_job(job)
        recovered = ExperimentJobs(self.db, self.data)
        try:
            with patch.object(ExperimentHistory, "_history", side_effect=AssertionError("Snapshot should be frozen")), \
                 patch("lab.experiments.simulate", wraps=simulate) as replay:
                recovered._run_job(recovered.get(job["id"]))
            self.assertEqual(replay.call_count,7)
            saved = recovered.get(job["id"], full=True)
            self.assertEqual(saved["status"], "complete")
            self.assertEqual(saved["progress"]["attempts"],2)
            self.assertEqual(saved["result"]["data_sha256"],saved["progress"]["data_sha256"])
        finally:
            recovered.shutdown()

    def test_cancellation_wins_against_late_completion_and_code_changes_stop_resume(self):
        job = self.enqueue()
        self.manager.cancel(job["id"])
        self.manager._patch(job["id"],status="complete",message="A late worker update")
        self.assertEqual(self.manager.get(job["id"])["status"], "cancelled")
        self.manager.code_hash = "changed"
        with self.assertRaises(ValueError): self.manager.retry(job["id"])

    def test_two_processes_cannot_own_the_same_queue(self):
        self.manager.blocked = lambda:True
        job = self.enqueue()
        self.manager.resume()
        other = ExperimentJobs(self.db, self.data)
        try:
            other.resume()
            self.assertIsNone(other.worker)
            self.assertEqual(other.get(job["id"])["status"],"queued")
        finally:
            other.shutdown()

    def test_service_access_and_parameter_boundaries(self):
        service = Service(BASE, self.db, self.data, token="test-access-token")
        try:
            self.assertEqual(service.handle("GET","/experiments")[0],200)
            self.assertEqual(service.handle("GET","/api/experiments/status")[0],401)
            headers={"Authorization":"Bearer test-access-token","Content-Type":"application/json"}
            for body in ({"symbol":"AAPL","interval":"15m","days":90,"recipes":["exit_rules"]},
                         {"symbol":"BTC-USD","interval":"1m","days":365,"recipes":["exit_rules"]},
                         {"symbol":"BTC-USD","interval":"15m","days":90,"recipes":["exec_code"]}):
                self.assertEqual(service.handle("POST","/api/experiments/start",body=body,headers=headers)[0],400)
            self.assertEqual(service.handle("GET","/api/experiments/coverage",headers=headers)[1]["quote_currency"],"USDT")
        finally:
            service.experiments.shutdown()
            service.forward.shutdown()
            service.events.stop(persist=False)


class PlannerAndRiskTests(unittest.TestCase):
    def test_unknown_correlation_is_not_treated_as_diversification(self):
        risk = related_risk("BTC-USD", {}, {"ETH-USD":{"risk_usd":3.}}, 1700000000000)
        self.assertEqual(risk["related_open_risk_usd"],3.)
        self.assertTrue(risk["relationships"][0]["unknown"])
        xs={i:math.sin(i) for i in range(100)}
        self.assertAlmostEqual(correlation(xs,{i:2*v for i,v in xs.items()})[0],1.)
        self.assertIsNone(correlation(xs,{i:v for i,v in xs.items() if i>40})[0])
        self.assertEqual(hourly_returns(candles(180,step=3600000),1800000000000),{})

    def test_stale_positions_block_entries_and_related_risk_caps_size(self):
        from tests.test_account_service import PaperAccountTests
        fixture = PaperAccountTests()
        fixture.setUp()
        try:
            fixture.agent.configure({"max_related_risk":.005})
            first = fixture.open()
            self.assertIsNotNone(first)
            fixture.quote("ETH-USD")
            fixture.agent.market["BTC-USD"]["ticker"]["ts"] -= 120000
            self.assertIsNone(fixture.open("ETH-USD"))
            self.assertIn("stale",fixture.agent.market["ETH-USD"]["last_decision"])
            fixture.quote()
            second = fixture.open("ETH-USD")
            self.assertIsNotNone(second)
            total=first["risk_usd"]+second["risk_usd"]
            self.assertLessEqual(total,500*.005)
            self.assertTrue(second["decision"]["portfolio_concentration"]["relationships"][0]["unknown"])
        finally:
            fixture.tearDown()

    def test_ai_plan_cannot_add_parameters_or_duplicate_recipes(self):
        for value in ({"suggestions":[{"recipe":"exit_rules","rationale":"test","risk":1}]},
                      {"suggestions":[{"recipe":"live_order","rationale":"test"}]},
                      {"suggestions":[{"recipe":"exit_rules","rationale":"a"}]*2}):
            with self.assertRaises(ValueError): validate_plan(value)

    def test_ai_api_is_bounded_and_receives_aggregates_only(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/"test.sqlite3";init_continuous_db(db)
            context=planner_context(db,[])
            self.assertIn("No closed",built_in_plan(context)["note"])
            response=Mock(status_code=200)
            response.json.return_value={"status":"completed","output":[{"type":"message","content":[
                {"type":"output_text","text":json.dumps({"suggestions":[{"recipe":"exit_rules","rationale":"Test giveback; no closed trades yet."}]})}]}]}
            with patch.dict("os.environ",{"OPENAI_API_KEY":"fixture-key","OPENAI_EXPERIMENT_MODEL":"fixture-model"}), \
                 patch("lab.experiment_planner.requests.post",return_value=response) as post:
                result=ai_plan(db,context)
                self.assertFalse(result["automatically_queued"])
                payload=post.call_args.kwargs["json"]
                self.assertFalse(payload["store"])
                self.assertNotIn("tools",payload)
                self.assertNotIn("fixture-key",payload["input"])
                with self.assertRaises(RuntimeError): ai_plan(db,context)
                self.assertEqual(post.call_count,1)


if __name__ == "__main__":
    unittest.main()
