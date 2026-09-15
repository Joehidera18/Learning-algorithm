"""Control-flow tests use fixtures; they do not establish market performance."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lab.adaptive import approved_profile
from lab.service import Service
from tests.test_execution import candles
from run_research import main

BASE = Path(__file__).resolve().parents[1]


class HistoricalPracticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = Service(BASE, self.root/"test.sqlite3", self.root/"data")

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
            s.autolearn.worker.join(timeout=5)
        self.assertFalse(s.autolearn.worker.is_alive())
        self.assertEqual(s.agent.settings, before)
        self.assertFalse(s.agent.runtime["running"])
        self.assertEqual(history.call_args.args, ("BTC-USD", "15m", 1095))
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

    def test_invalid_or_overlapping_request_does_not_change_fee_settings(self):
        s = self.service
        before = dict(s.agent.settings)
        for symbols in ([], ["../../other-USD"], [None], ["BTC-USD"]*6):
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
            s.autolearn.worker.join(timeout=5)
        history.assert_called_once()
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
            self.assertEqual(history.call_args.args, ("ETH-USD", "1h", 365))
            self.assertEqual(history.call_args.kwargs["end_ms"], 1735689600000)
            self.assertIs(learn.call_args.args[0], rows)
            self.assertEqual(learn.call_args.args[2]["decision_interval"], "1h")
            result = json.loads(out.read_text())
            self.assertEqual(result["market_data"]["kind"], "recorded_market_candles")

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
                         ["--csv", "existing.csv", "--end", "2025-01-01"]):
                with self.subTest(args=args), self.assertRaises(SystemExit) as exc:
                    main(args)
                self.assertEqual(exc.exception.code, 2)
            history.assert_not_called()
