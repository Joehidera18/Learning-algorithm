"""Export/authentication tests use artificial candles, not market evidence."""
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from lab.data import validate_history
from lab.evaluation import DATA_FIELDS, dataset_digest
from lab.service import Service
from tests.test_execution import candles


class ResearchBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = Service(Path(__file__).resolve().parents[1],root/"test.db",root/"data",token="fixture-access-token")
        self.rows = candles(310)
        self.path = self.service.autolearn.downloader.data_dir/"history"/"BTC-USD_15m.csv"
        self.path.parent.mkdir(parents=True)
        self.report = {"symbol":"BTC-USD","interval":"15m","validated":False,
            "data_quality":validate_history(self.rows[:300],"15m"),
            "data_sha256":dataset_digest(self.rows[:300]),
            "market_data":{"provider":"Artificial software test fixture"}}
        self.service.autolearn.state["results"] = [self.report]
        self.write_cache()

    def tearDown(self):
        self.service.autolearn.stop(); self.service.agent.stop(); self.temp.cleanup()

    def write_cache(self):
        with self.path.open("w",newline="") as handle:
            writer = csv.DictWriter(handle,fieldnames=DATA_FIELDS)
            writer.writeheader();writer.writerows(self.rows)

    def get(self, **query):
        return self.service.handle("GET","/api/learning/data",query={"symbol":"BTC-USD","interval":"15m",**query},
            headers={"Authorization":"Bearer fixture-access-token"})

    def test_export_auth_range_hash_and_archive_contents(self):
        code,_,_ = self.service.handle("GET","/api/learning/data",query={"symbol":"BTC-USD","interval":"15m"})
        self.assertEqual(code,401)
        code,data,headers = self.get()
        self.assertEqual(code,200)
        self.assertEqual(headers["Content-Type"],"application/zip")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()),{"candles.csv","manifest.json","learning-result.json"})
            manifest = json.loads(archive.read("manifest.json"))
            self.assertTrue(manifest["matches_report_data_sha256"])
            self.assertEqual(manifest["rows"],300)
            self.assertEqual(manifest["data_sha256"],self.report["data_sha256"])
            exported = list(csv.DictReader(io.StringIO(archive.read("candles.csv").decode())))
            self.assertEqual(len(exported),300)
            self.assertEqual(int(exported[-1]["ts"]),self.rows[299]["ts"])
            self.assertNotIn(b"fixture-access-token",b"".join(archive.read(name) for name in archive.namelist()))

    def test_changed_price_with_same_row_count_cannot_claim_exact_reproduction(self):
        self.rows[250]["close"] += .05
        self.write_cache()
        code,result,_ = self.get()
        self.assertEqual(code,400)
        self.assertIn("no longer match",result["error"])

    def test_missing_data_and_path_traversal_are_rejected(self):
        for query in ({"symbol":"../BTC-USD"},{"interval":"../../secrets"},{"symbol":"BTC-USD\r\nX-Test: true"}):
            with self.subTest(query=query): self.assertEqual(self.get(**query)[0],400)
        self.path.unlink()
        self.assertEqual(self.get()[0],400)

    def test_old_report_is_explicitly_not_digest_verified(self):
        del self.report["data_sha256"]
        code,data,_ = self.get()
        self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIsNone(json.loads(archive.read("manifest.json"))["matches_report_data_sha256"])

    def test_daily_context_is_exported_exactly_and_changed_context_is_rejected(self):
        step=86400000
        rows=candles(24,step=step,start=self.rows[0]["ts"]-21*step)
        daily=self.path.with_name("BTC-USD_1d.csv")
        def write():
            with daily.open("w",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=DATA_FIELDS)
                writer.writeheader();writer.writerows(rows)
        write()
        self.report["daily_data"]={"source":"independent_daily_candles","rows":len(rows),
            "start_ts":rows[0]["ts"],"end_ts":rows[-1]["ts"],"data_sha256":dataset_digest(rows)}
        code,data,_=self.get()
        self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read("daily-candles.csv").decode().splitlines(),daily.read_text().splitlines())
            self.assertEqual(json.loads(archive.read("manifest.json"))["daily_data"]["data_sha256"],dataset_digest(rows))
        rows[-1]["close"]-=.01; write()
        self.assertEqual(self.get()[0],400)
        daily.unlink()
        self.assertEqual(self.get()[0],400)

    def test_bitcoin_context_export_is_hash_checked_and_separate_from_coin_prices(self):
        rows=candles(24,step=86400000,start=0)
        path=self.path.with_name("BTC-USD_1d.csv")
        def write():
            with path.open("w",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=DATA_FIELDS)
                writer.writeheader();writer.writerows(rows)
        write()
        self.report["bitcoin_data"]={"symbol":"BTC-USD","source":"independent_daily_candles",
            "rows":len(rows),"start_ts":rows[0]["ts"],"end_ts":rows[-1]["ts"],"data_sha256":dataset_digest(rows)}
        code,data,_=self.get();self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read("bitcoin-daily-candles.csv").decode().splitlines(),path.read_text().splitlines())
            self.assertEqual(json.loads(archive.read("manifest.json"))["bitcoin_data"]["data_sha256"],dataset_digest(rows))
        rows[-1]["close"]-=.01;write()
        self.assertEqual(self.get()[0],400)
        path.unlink();self.assertEqual(self.get()[0],400)


if __name__=="__main__": unittest.main()
