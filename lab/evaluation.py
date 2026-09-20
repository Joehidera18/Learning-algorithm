"""Track known research reuse separately from decision-time causality."""
import json
import hashlib
from pathlib import Path

BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-16.json").read_text())
REVIEWED_THROUGH = {r["symbol"]:r["reviewed_through_ts"] for r in BASELINE["markets"]}
RECENT_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-17.json").read_text())
for _market in RECENT_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
LATEST_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-19.json").read_text())
for _market in LATEST_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
ENTRY_AUDIT_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-v11.6-completed.json").read_text())
for _market in ENTRY_AUDIT_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
CALIBRATION_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-v11.7-completed.json").read_text())
for _market in CALIBRATION_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
PRACTICE_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-v11.8-completed.json").read_text())
for _market in PRACTICE_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
CONTINUITY_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-v11.9-partial.json").read_text())
for _market in CONTINUITY_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
ELIGIBLE_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-v11.10-partial.json").read_text())
for _market in ELIGIBLE_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
RELIABILITY_BASELINE = json.loads((Path(__file__).resolve().parents[1]/"research_baselines"/"report-v11.14-partial.json").read_text())
for _market in RELIABILITY_BASELINE["markets"]:
    REVIEWED_THROUGH[_market["symbol"]] = max(REVIEWED_THROUGH.get(_market["symbol"],0),_market["reviewed_through_ts"])
DATA_FIELDS = ("ts", "open", "high", "low", "close", "volume", "quote_volume", "trades")


def canonical_candle(row):
    values = {**row, "quote_volume":row.get("quote_volume", row.get("volume", 0)*row["close"])}
    return {k:(int(values.get(k, 0)) if k in ("ts", "trades") else float(values.get(k, 0))) for k in DATA_FIELDS}


def dataset_digest(rows):
    digest = hashlib.sha256()
    for r in rows:
        canonical = canonical_candle(r)
        normalized = [canonical[k] for k in DATA_FIELDS]
        digest.update(json.dumps(normalized,separators=(",", ":"),allow_nan=False).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def reviewed_boundary(symbol, supplied=None):
    return max(REVIEWED_THROUGH.get(symbol, 0), int(supplied or 0))


def attribution(trades):
    """Within ONE market account; slippage is already included in gross P&L."""
    families = {}
    for trade in trades:
        row = families.setdefault(trade["strategy_family"],
            {"trades":0, "gross_pnl":0., "fees_paid":0., "net_pnl":0., "slippage_notional":0.})
        row["trades"] += 1
        for key in ("gross_pnl", "fees_paid", "slippage_notional"):
            row[key] += trade.get(key, 0.)
        row["net_pnl"] += trade["pnl"]
    return {"by_family":families,
        "scope":"Selected trades in this market's $500 account. Gross P&L already includes modeled slippage; subtract fees once for net P&L."}
