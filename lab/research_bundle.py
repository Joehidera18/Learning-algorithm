"""Export one completed run's recorded candles and report, never account secrets."""
import csv
import io
import json
import re
import zipfile

from .data import load_history
from .evaluation import DATA_FIELDS, dataset_digest, canonical_candle
from .paper_store import load_state


def market_bundle(learner, symbol, interval):
    if (not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9]{2,16}-USD",symbol)
            or interval not in ("5m","15m","1h","6h")):
        raise ValueError("Choose a Coinbase USD market and a 5m, 15m, 1h or 6h interval")
    with learner.lock:
        report = next((dict(r) for r in learner.state.get("results", [])
                       if r.get("symbol")==symbol and r.get("interval")==interval), None)
    if not report or report.get("error") or not report.get("data_quality"):
        raise ValueError("A completed learning report is needed for this market")
    if report.get("fingerprint"):
        report = load_state(learner.db_path,"learning_result_"+report["fingerprint"],report)
    path = learner.downloader.data_dir/"history"/f"{symbol}_{interval}.csv"
    if not path.is_file():
        raise ValueError("Recorded candles are not cached here. Complete historical practice before exporting data.")
    # Downloader checkpoints replace files atomically. Read one snapshot and
    # restrict it to this report's range so later downloads are not included.
    quality = report["data_quality"]
    rows = [r for r in load_history(path) if quality["start_ts"] <= r["ts"] <= quality["end_ts"]]
    digest = dataset_digest(rows)
    if len(rows)!=quality["rows"] or (report.get("data_sha256") and digest!=report["data_sha256"]):
        raise ValueError("The cached candles no longer match this report. Run practice again before exporting its data.")
    daily = report.get("daily_data", {})
    daily_content = None
    if daily.get("source") == "independent_daily_candles":
        daily_path = path.with_name(f"{symbol}_1d.csv")
        if not daily_path.is_file():
            raise ValueError("Daily context candles are missing. Run practice again before exporting its data.")
        daily_rows = [r for r in load_history(daily_path)
                      if daily["start_ts"] is not None and daily["start_ts"] <= r["ts"] <= daily["end_ts"]]
        if len(daily_rows) != daily["rows"] or dataset_digest(daily_rows) != daily["data_sha256"]:
            raise ValueError("The cached daily candles no longer match this report. Run practice again before exporting its data.")
        daily_content = io.StringIO(newline="")
        daily_writer = csv.DictWriter(daily_content, fieldnames=DATA_FIELDS)
        daily_writer.writeheader(); daily_writer.writerows(canonical_candle(row) for row in daily_rows)
    bitcoin = report.get("bitcoin_data", {})
    bitcoin_content = None
    if bitcoin.get("source") == "independent_daily_candles":
        bitcoin_path = path.with_name("BTC-USD_1d.csv")
        if not bitcoin_path.is_file():
            raise ValueError("Bitcoin context candles are missing. Run practice again before exporting its data.")
        bitcoin_rows = [r for r in load_history(bitcoin_path)
            if bitcoin["start_ts"] is not None and bitcoin["start_ts"] <= r["ts"] <= bitcoin["end_ts"]]
        if len(bitcoin_rows) != bitcoin["rows"] or dataset_digest(bitcoin_rows) != bitcoin["data_sha256"]:
            raise ValueError("The cached Bitcoin candles no longer match this report. Run practice again before exporting its data.")
        bitcoin_content = io.StringIO(newline="")
        bitcoin_writer = csv.DictWriter(bitcoin_content, fieldnames=DATA_FIELDS)
        bitcoin_writer.writeheader(); bitcoin_writer.writerows(canonical_candle(row) for row in bitcoin_rows)
    from .event_context import digest as event_digest, validate_snapshot
    event_snapshot = report.get("event_snapshot")
    if report.get("event_data",{}).get("data_sha256"):
        if event_snapshot is None or event_digest(validate_snapshot(event_snapshot)) != report["event_data"]["data_sha256"]:
            raise ValueError("The event archive no longer matches this report; run practice again.")
    content = io.StringIO(newline="")
    writer = csv.DictWriter(content,fieldnames=DATA_FIELDS)
    writer.writeheader(); writer.writerows(canonical_candle(row) for row in rows)
    manifest = {"symbol":symbol,"interval":interval,"rows":len(rows),
        "start_ts":quality["start_ts"],"end_ts":quality["end_ts"],"data_sha256":digest,
        "matches_report_data_sha256":True if report.get("data_sha256") else None,
        "market_data":report.get("market_data"),
        "history_request":report.get("history_request"),
        "daily_data":daily,
        "bitcoin_data":bitcoin,
        "event_data":report.get("event_data"),
        "scope":"Recorded candle data and one historical report. Old reports without a data hash can verify dates and count only. No API keys, account database or exchange journal is included."}
    output = io.BytesIO()
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("candles.csv",content.getvalue())
        if daily_content is not None:
            archive.writestr("daily-candles.csv",daily_content.getvalue())
        if bitcoin_content is not None:
            archive.writestr("bitcoin-daily-candles.csv",bitcoin_content.getvalue())
        if event_snapshot is not None:
            archive.writestr("market-events.json",json.dumps(event_snapshot,indent=2,allow_nan=False))
        archive.writestr("learning-result.json",json.dumps(report,indent=2,allow_nan=False))
        archive.writestr("manifest.json",json.dumps(manifest,indent=2,allow_nan=False))
    return output.getvalue(),f"{symbol}_{interval}_learning-data.zip"
