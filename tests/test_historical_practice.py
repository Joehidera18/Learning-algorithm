"""Control-flow tests use fixtures; they do not establish market performance."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lab.adaptive import POLICY_VERSION, approved_profile
from lab.learning_research import LEARNING_REPORT_VERSION
from lab.autolearn import DEFAULT_PRACTICE_SYMBOLS
from lab.service import Service
from tests.test_adaptive import F
from tests.test_execution import candles
from run_research import main

BASE = Path(__file__).resolve().parents[1]


class HistoricalPracticeTests(unittest.TestCase):
    def setUp(self):
        # Event collection has its own adapter tests; keep these replay tests offline.
        event_start = patch("lab.event_store.EventCollector.start")
        event_start.start(); self.addCleanup(event_start.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = Service(BASE, self.root/"test.sqlite3", self.root/"data")
        from lab.study_plan import DEFAULT_PRACTICE_SYMBOLS
        products = patch.object(self.service.agent.client, "products", return_value=[{
            "id":s, "base_currency":s[:-4], "quote_currency":"USD", "status":"online"}
            for s in DEFAULT_PRACTICE_SYMBOLS])
        products.start()
        self.addCleanup(products.stop)

    def tearDown(self):
        self.service.autolearn.stop()
        self.service.agent.stop()
        self.temp.cleanup()

    def test_practice_uses_history_without_starting_live_market_monitoring(self):
        s = self.service
        before = dict(s.agent.settings)
        with patch.object(s.agent, "start", side_effect=AssertionError("No current-market runner")), \
             patch.object(s.coinbase, "start", side_effect=AssertionError("No exchange orders")), \
             patch.object(s.agent.client, "discover_top_usd", side_effect=AssertionError("No live scanner prerequisite")), \
             patch.object(s.autolearn.downloader, "_history", return_value=candles(3000)) as history:
            code, _, _ = s.handle("POST", "/api/learning/practice", body={"symbols":["BTC-USD"]},
                                 headers={"Content-Type":"application/json"})
            self.assertEqual(code, 202)
            # Exercise both complete learning passes. Completion is the contract;
            # five seconds is not a promised training latency under CPU load.
            s.autolearn.worker.join(timeout=30)
        self.assertFalse(s.autolearn.worker.is_alive())
        self.assertEqual(s.agent.settings, before)
        self.assertFalse(s.agent.runtime["running"])
        self.assertEqual(history.call_args_list[0].args, ("BTC-USD", "15m", 1825))
        self.assertEqual(history.call_args_list[1].args, ("BTC-USD", "1d", 1855))
        status = s.autolearn.status()
        self.assertEqual(status["phase"], "completed")
        self.assertFalse(status["enabled"])
        report = status["results"][0]
        self.assertEqual(report["market_data"]["provider"], "Coinbase Exchange")
        self.assertFalse(report["market_data"]["synthetic_fallback"])
        self.assertLess(report["replay"]["training_end_ts"], report["replay"]["test_start_ts"])
        self.assertFalse(report["validated"])

    def test_failed_real_download_never_calls_training_or_installs_a_model(self):
        s = self.service
        with patch.object(s.autolearn.downloader, "_history", side_effect=TimeoutError("Coinbase unavailable")), \
             patch("lab.autolearn.learn_history") as train:
            s.autolearn.start_history(["BTC-USD"])
            s.autolearn.worker.join(timeout=5)
        train.assert_not_called()
        self.assertEqual(s.autolearn.status()["phase"], "error")
        self.assertEqual(s.autolearn.status()["market_data_hours"], 0)
        self.assertIn("Could not load real market history", s.autolearn.status()["message"])
        self.assertIsNone(approved_profile(s.db_path, "BTC-USD", s.agent.settings))

    def test_gap_training_report_download_and_restart_preserve_costed_examples(self):
        s = self.service
        rows = candles(6000)
        del rows[1000]
        def fixture_features(section, *args, **kwargs):
            return {"features":[dict(F, _atr=.01) for _ in section]}
        with patch.object(s.autolearn.downloader, "_history", return_value=rows), patch(
                "lab.learning_research.build_feature_cache", side_effect=fixture_features):
            s.autolearn.start_history(["BTC-USD"], {"fee_rate":.004})
            # Three variants run two practice tracks per candidate and preserve
            # extra forecast diagnostics. This is a bounded persistence check;
            # the real-data reproduction script measures runtime and memory.
            s.autolearn.worker.join(timeout=180)
        self.assertFalse(s.autolearn.worker.is_alive())
        status = s.autolearn.status()
        self.assertEqual(status["phase"], "completed")
        self.assertEqual(status["current_policy_version"], POLICY_VERSION)
        self.assertEqual(status["current_report_version"], LEARNING_REPORT_VERSION)
        report = status["results"][0]
        self.assertEqual(report["data_selection"]["used_candles"], len(rows))
        self.assertEqual(report["data_selection"]["segment_count"], 2)
        self.assertGreater(report["historical_examples"], 0)
        self.assertGreater(report["training_diagnostics"]["totals"]["exploratory_entries"], 0)
        self.assertFalse(report["validated"])
        code, content, headers = s.handle("GET", "/api/learning/export")
        self.assertEqual(code, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        exported = json.loads(content)["results"][0]
        self.assertEqual(exported["training_diagnostics"], report["training_diagnostics"])
        self.assertEqual(exported["trade_reviews"],report["trade_reviews"])
        self.assertEqual(exported['exit_policy_comparison'],report['exit_policy_comparison'])
        self.assertFalse(exported['exit_policy_comparison']['eligible_for_trading'])
        self.assertEqual(report["trade_reviews"]["development"]["examples"],report["historical_examples"])
        self.assertGreater(exported["model"]["observations"], 0)
        self.assertEqual(exported["costs"]["fee_per_side"], .004)
        restarted = Service(BASE, s.db_path, self.root/"data")
        self.assertEqual(restarted.autolearn.status()["results"], status["results"])
        self.assertFalse(restarted.agent.runtime["running"])
        self.assertFalse(restarted.autolearn.status()["enabled"])
        self.assertIsNone(approved_profile(s.db_path, "BTC-USD", s.agent.settings))

    def test_invalid_or_overlapping_request_does_not_change_fee_settings(self):
        s = self.service
        before = dict(s.agent.settings)
        for symbols in ([], ["../../other-USD"], [None], ["BTC-USD"]*61, ["BTC-USDT"], [""]):
            with self.subTest(symbols=symbols):
                code, _, _ = s.handle("POST", "/api/learning/practice",
                    body={"symbols":symbols,"fee_rate":.001}, headers={"Content-Type":"application/json"})
                self.assertEqual(code, 400)
                self.assertEqual(s.agent.settings, before)
        s.research.worker = Mock(is_alive=lambda:True)
        with self.assertRaises(ValueError):
            s.autolearn.start_history(["BTC-USD"], {"fee_rate":.001})
        s.research.worker = None
        self.assertEqual(s.agent.settings, before)

    def test_manual_practice_retries_a_failed_download_before_automatic_deadline(self):
        s = self.service
        with patch.object(s.autolearn.downloader, "_history", side_effect=TimeoutError("Coinbase unavailable")):
            s.autolearn.start_history(["BTC-USD"])
            s.autolearn.worker.join(timeout=5)
        self.assertEqual(s.autolearn.status()["phase"], "error")
        with patch.object(s.autolearn.downloader, "_history", return_value=candles(3000)) as history:
            # Automatic polling retains its backoff; an explicit retry can recover now.
            s.autolearn.study(["BTC-USD"], dict(s.agent.settings))
            history.assert_not_called()
            s.autolearn.start_history(["BTC-USD"])
            s.autolearn.worker.join(timeout=30)
        self.assertEqual([c.args[1] for c in history.call_args_list], ["15m", "1d"])
        self.assertFalse(s.autolearn.worker.is_alive())
        self.assertEqual(s.autolearn.status()["phase"], "completed")
        self.assertNotIn("error", s.autolearn.status()["results"][0])
        self.assertFalse(s.agent.runtime["running"])

    def test_rejected_automatic_start_preserves_fees_during_another_task(self):
        s = self.service
        before = dict(s.agent.settings)
        for controller in (s.autolearn, s.research):
            with self.subTest(controller=type(controller).__name__):
                controller.worker = Mock(is_alive=lambda:True)
                s.autolearn.state["mode"] = "historical_replay"
                try:
                    code, _, _ = s.handle("POST", "/api/learning/start", body={"fee_rate":.001},
                                         headers={"Content-Type":"application/json"})
                    self.assertEqual(code, 400)
                    self.assertEqual(s.agent.settings, before)
                finally:
                    controller.worker = None

    def test_practice_requires_existing_app_authentication(self):
        s = self.service
        s.token = "private-test-token"
        with patch.object(s.autolearn, "start_history") as start:
            code, _, _ = s.handle("POST", "/api/learning/practice", body={},
                                 headers={"Content-Type":"application/json"})
        self.assertEqual(code, 401)
        start.assert_not_called()

    def test_default_practice_includes_requested_coins(self):
        s = self.service
        with patch.object(s.autolearn, "_run_history") as run:
            s.autolearn.start_history()
            s.autolearn.worker.join(timeout=5)
        self.assertEqual(run.call_args.args[0], list(DEFAULT_PRACTICE_SYMBOLS))
        self.assertEqual(run.call_args.args[0][:13], ["BTC-USD", "ETH-USD", "SOL-USD", "HBAR-USD", "XRP-USD", "XLM-USD",
            "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "LTC-USD", "BCH-USD", "DOT-USD"])
        self.assertEqual(len(run.call_args.args[0]), 30)
        self.assertFalse(s.agent.runtime["running"])

    def test_custom_practice_normalizes_deduplicates_and_saves_selection(self):
        s = self.service
        with patch.object(s.autolearn, "_run_history") as run:
            code, _, _ = s.handle("POST", "/api/learning/practice", body={
                "symbols":[" hbar ", "XRP-USD", "xlm", "HBAR-USD", "ADA", "DOGE", "AVAX"],
                "fee_rate":.004}, headers={"Content-Type":"application/json"})
            self.assertEqual(code, 202)
            s.autolearn.worker.join(timeout=5)
        expected = ["HBAR-USD", "XRP-USD", "XLM-USD", "ADA-USD", "DOGE-USD", "AVAX-USD"]
        self.assertEqual(run.call_args.args[0], expected)
        restarted = Service(BASE, s.db_path, self.root/"data")
        self.assertEqual(restarted.autolearn.status()["practice_symbols"], expected)
        self.assertEqual(restarted.autolearn.status()["max_practice_markets"], 60)
        self.assertFalse(restarted.agent.runtime["running"])

    def test_unavailable_coin_does_not_prevent_later_coin_practice(self):
        s = self.service
        def history(symbol, *args, **kwargs):
            if symbol == "HBAR-USD":
                raise ValueError("Requested market history unavailable")
            return candles(3000)
        with patch.object(s.autolearn.downloader, "_history", side_effect=history) as download:
            s.autolearn.start_history(["HBAR", "XRP", "XLM"])
            s.autolearn.worker.join(timeout=30)
        self.assertFalse(s.autolearn.worker.is_alive())
        self.assertEqual([c.args[0] for c in download.call_args_list if c.args[1]=="15m"],
                         ["HBAR-USD", "XRP-USD", "XLM-USD"])
        self.assertEqual([c.args[0] for c in download.call_args_list if c.args[1]=="1d"],
                         ["XRP-USD", "BTC-USD", "XLM-USD"])
        results = s.autolearn.status()["results"]
        self.assertIn("error", results[0])
        self.assertNotIn("error", results[1])
        self.assertNotIn("error", results[2])
        self.assertEqual(s.autolearn.status()["completed_markets"], 3)


class HistoricalCommandTests(unittest.TestCase):
    def test_coinbase_command_passes_dates_and_interval_and_records_the_source(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            out = Path(folder)/"report.json"
            rows = candles(3000)
            with patch("run_research.ResearchManager._history", return_value=rows) as history, \
                 patch("run_research.learn_history", return_value={"validated":False}) as learn:
                code = main(["--coinbase", "--learning", "--symbol", "ETH-USD", "--interval", "1h",
                             "--days", "365", "--end", "2025-01-01", "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(history.call_args_list[0].args, ("ETH-USD", "1h", 365))
            self.assertEqual(history.call_args_list[0].kwargs["end_ms"], 1735689600000)
            self.assertEqual(history.call_args_list[1].args, ("ETH-USD", "1d", 395))
            self.assertEqual(history.call_args_list[2].args, ("BTC-USD", "1d", 395))
            self.assertIs(learn.call_args.args[0], rows)
            self.assertEqual(learn.call_args.args[2]["decision_interval"], "1h")
            result = json.loads(out.read_text())
            self.assertEqual(result["market_data"]["kind"], "recorded_market_candles")

    def test_recorded_bitcoin_context_reaches_the_csv_learner_without_a_download(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            out = Path(folder)/"report.json"
            intraday, daily, bitcoin = candles(3000), candles(40), candles(45)
            with patch("run_research.load_history", side_effect=[intraday,daily,bitcoin]) as load, \
                 patch("run_research.learn_history", return_value={"validated":False}) as learn, \
                 patch("run_research.ResearchManager._history") as history:
                self.assertEqual(main(["--csv","coin.csv","--daily-csv","day.csv","--bitcoin-csv","btc.csv",
                    "--learning","--symbol","ETH-USD","--out",str(out)]),0)
            self.assertEqual([call.args[0].name for call in load.call_args_list],["coin.csv","day.csv","btc.csv"])
            self.assertIs(learn.call_args.kwargs["daily_rows"],daily)
            self.assertIs(learn.call_args.kwargs["bitcoin_rows"],bitcoin)
            history.assert_not_called()

    def test_command_fails_without_substituting_prices_when_coinbase_is_unreachable(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as log:
            out = Path(folder)/"report.json"
            with patch("run_research.ResearchManager._history", side_effect=TimeoutError("offline")), \
                 patch("run_research.learn_history") as train, patch("run_research.load_history") as csv:
                code = main(["--coinbase", "--learning", "--out", str(out)])
            self.assertEqual(code, 1)
            train.assert_not_called()
            csv.assert_not_called()
            self.assertFalse(out.exists())
            self.assertIn("No substitute prices were generated", log.getvalue())

    def test_supplied_csv_keeps_source_unverified_and_supports_other_market_labels(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            out = Path(folder)/"report.json"
            with patch("run_research.load_history", return_value=candles(3000)), \
                 patch("run_research.learn_history", return_value={"validated":False}), \
                 patch("run_research.ResearchManager._history") as history:
                code = main(["--csv", "existing.csv", "--learning", "--symbol", "BTCUSDT", "--out", str(out)])
            self.assertEqual(code, 0)
            history.assert_not_called()
            self.assertEqual(json.loads(out.read_text())["market_data"]["kind"], "provided_ohlcv")

    def test_invalid_download_arguments_fail_before_requesting_data(self):
        with contextlib.redirect_stderr(io.StringIO()), patch("run_research.ResearchManager._history") as history:
            for args in (["--coinbase", "--symbol", "../../BTC-USD"],
                         ["--coinbase", "--end", "2100-01-01"],
                         ["--coinbase", "--days", "29"],
                         ["--coinbase", "--learning", "--bitcoin-csv", "btc.csv"],
                         ["--csv", "existing.csv", "--bitcoin-csv", "btc.csv"],
                         ["--csv", "existing.csv", "--end", "2025-01-01"]):
                with self.subTest(args=args), self.assertRaises(SystemExit) as exc:
                    main(args)
                self.assertEqual(exc.exception.code, 2)
            history.assert_not_called()
