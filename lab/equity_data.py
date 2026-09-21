"""US-listed equity history. No brokerage or order endpoint is used here.

Bars are anchored at the regular session open. A short final session bar is
explicit, never extended into the next session. Missing source bars stay missing.
"""
from __future__ import annotations

import math
import os
import re
import time
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from .data import INTERVAL_MS

DAY = 86400000
NY = ZoneInfo("America/New_York")
INTERVALS = ("1m", "4m", "5m", "15m", "30m", "1h", "4h", "1d")
WATCHLIST = ("VRTX", "ALNY", "AVGO", "GOOGL", "TSM", "ETN", "NVDA", "ARGX", "CEG", "INSM",
             "VRT", "IBM", "BEAM", "CRSP", "ASML", "KEYS", "ANET", "RBRK", "VKTX", "IONQ")
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT")+WATCHLIST
YAHOO_LIMITS = {"1m":29, "4m":29, "5m":59, "15m":59, "30m":59, "1h":729, "4h":729, "1d":3650}


def ticker(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{1,5}(?:[.-][A-Z])?", value):
        raise ValueError("Use a US stock or ETF ticker, for example AAPL or SPY")
    return value


def iso(ts):
    return datetime.fromtimestamp(ts/1000, timezone.utc).isoformat()


@lru_cache(maxsize=24)
def sessions(start_date, end_date):
    import pandas_market_calendars as mcal
    schedule = mcal.get_calendar("NYSE").schedule(start_date=start_date, end_date=end_date)
    return tuple((str(day.date()), int(row.market_open.timestamp()*1000),
                  int(row.market_close.timestamp()*1000)) for day, row in schedule.iterrows())


def schedule_between(start, end):
    a = datetime.fromtimestamp(start/1000, NY).date()-timedelta(days=1)
    b = datetime.fromtimestamp(end/1000, NY).date()+timedelta(days=10)
    return sessions(str(a), str(b))


def market_status(now=None):
    now = int(time.time()*1000) if now is None else now
    schedule = schedule_between(now, now)
    active = next((s for s in schedule if s[1] <= now < s[2]), None)
    following = next((s for s in schedule if s[1] > now), None)
    return {"open":bool(active), "timezone":"America/New_York", "session":"regular",
            "session_date":active[0] if active else None, "close_ts":active[2] if active else None,
            "next_open_ts":following[1] if following else None}


def slots(interval, start, end):
    """Expected observed-bar identifiers, including the next scheduled open."""
    step = INTERVAL_MS[interval]
    result = []
    for day, opening, closing in schedule_between(start, end):
        stamps = [opening] if interval == "1d" else range(opening, closing, step)
        for ts in stamps:
            result.append({"ts":ts, "end_ts":closing if interval == "1d" else min(ts+step, closing),
                           "session":day, "session_open_ts":opening, "session_close_ts":closing})
    for a, b in zip(result, result[1:]):
        a["next_ts"] = b["ts"]
    return {r["ts"]:r for r in result if start <= r["ts"] and r["end_ts"] <= end}


def valid_prices(row):
    values = [row.get(k) for k in ("open", "high", "low", "close", "volume")]
    return (all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
            and min(values[:4]) > 0 and values[4] >= 0
            and row["low"] <= min(row["open"], row["close"])
            and row["high"] >= max(row["open"], row["close"]))


def normalize(raw, source_interval, target_interval, start, end):
    if source_interval not in INTERVALS or target_interval not in INTERVALS:
        raise ValueError("Unsupported stock timeframe")
    if INTERVAL_MS[target_interval] % INTERVAL_MS[source_interval]:
        raise ValueError("Stock aggregation must use compatible source bars")
    expected = slots(source_interval, start, end)
    by_day = {s[0]:s[1] for s in schedule_between(start, end)}
    observed, invalid, excluded = {}, 0, 0
    for source in raw:
        ts = source["ts"]
        if source_interval == "1d":
            # Vendors label a daily observation at midnight or the session open.
            day = datetime.fromtimestamp(ts/1000, NY).date().isoformat()
            ts = by_day.get(day, ts)
        if ts not in expected:
            excluded += 1
            continue
        if not valid_prices(source):
            invalid += 1
            continue
        if ts in observed:
            raise ValueError("Duplicate stock candle timestamp")
        prices = {k:float(source[k]) for k in ("open", "high", "low", "close", "volume")}
        observed[ts] = {**prices, **expected[ts], "quote_volume":prices["volume"]*prices["close"],
                        "trades":int(source.get("trades", 0)), "asset_class":"equity",
                        "split_factor":float(source.get("split_factor",1.))}
    targets = slots(target_interval, start, end)
    groups = {}
    target_step = INTERVAL_MS[target_interval]
    for row in observed.values():
        ts = (row["session_open_ts"] if target_interval == "1d" else
              row["session_open_ts"]+(row["ts"]-row["session_open_ts"])//target_step*target_step)
        groups.setdefault(ts, []).append(row)
    rows = []
    source_step = INTERVAL_MS[source_interval]
    for ts, metadata in sorted(targets.items()):
        group = sorted(groups.get(ts, []), key=lambda r:r["ts"])
        required = ([ts] if source_interval == "1d" else list(range(ts, metadata["end_ts"], source_step)))
        if [r["ts"] for r in group] != required or group[-1]["end_ts"] != metadata["end_ts"]:
            continue
        rows.append({**metadata, "open":group[0]["open"], "close":group[-1]["close"],
                     "high":max(r["high"] for r in group), "low":min(r["low"] for r in group),
                     "volume":sum(r["volume"] for r in group),
                     "quote_volume":sum(r["quote_volume"] for r in group),
                     "trades":sum(r["trades"] for r in group), "asset_class":"equity",
                     "split_factor":group[0]["split_factor"]})
    return rows, {"expected_candles":len(targets), "observed_candles":len(rows),
        "missing_candles":len(targets)-len(rows), "coverage_pct":100*len(rows)/len(targets) if targets else 0,
        "invalid_source_candles":invalid, "outside_window_or_session":excluded,
        "source_interval":source_interval, "interval":target_interval,
        "first_ts":rows[0]["ts"] if rows else None, "last_close_ts":rows[-1]["end_ts"] if rows else None,
        "short_session_bars":sum(r["end_ts"]-r["ts"] < target_step for r in rows) if target_interval != "1d" else 0,
        "calendar":"NYSE regular sessions, America/New_York; holidays and early closes included",
        "synthetic_candles":False}


class EquityData:
    def __init__(self, session=None):
        import requests
        self.http = session or requests.Session()
        self.key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID", "")
        self.secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY", "")

    def catalog(self):
        return {"symbols":list(SYMBOLS), "intervals":list(INTERVALS), "custom_us_tickers":True,
            "providers":{"yahoo":{"available":True, "max_days":YAHOO_LIMITS,
                "note":"Public Yahoo historical data; delayed, rate limited, and not an execution feed."},
                "alpaca":{"available":bool(self.key and self.secret),
                    "max_days":{iv:(3650 if iv == "1d" else 700 if iv in ("1h", "4h") else 180) for iv in INTERVALS},
                    "note":"Server data credentials required. SIP or IEX is chosen explicitly; feeds are never mixed."}},
            "default_provider":"yahoo", "default_interval":"1h", "default_days":365}

    def history(self, symbol, interval, days, cutoff=None, provider="yahoo", feed="sip", cancelled=None):
        ticker(symbol)
        if interval not in INTERVALS or provider not in self.catalog()["providers"]:
            raise ValueError("Choose a supported stock timeframe and data provider")
        limit = self.catalog()["providers"][provider]["max_days"][interval]
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= limit:
            raise ValueError(f"{provider} {interval} history is limited to {limit} calendar days per request")
        if feed not in ("sip", "iex"):
            raise ValueError("Choose SIP or IEX")
        # Both paths deliberately lag 20 minutes. Neither is a live quote feed.
        cutoff = min(cutoff or int(time.time()*1000), int(time.time()*1000)-20*60000)
        start = cutoff-days*DAY
        if cancelled and cancelled():
            raise InterruptedError("Stock download cancelled")
        if provider == "yahoo":
            base = {"4m":"1m", "4h":"1h"}.get(interval, interval)
            raw, extra = (self._yahoo_chunks(symbol,start,cutoff,cancelled) if base == "1m"
                          else self._yahoo(symbol, base, start, cutoff))
        else:
            if not self.key or not self.secret:
                raise ValueError("Configure ALPACA_API_KEY and ALPACA_SECRET_KEY on the server")
            base = {"4m":"1m", "1h":"30m", "4h":"30m"}.get(interval, interval)
            raw, extra = self._alpaca(symbol, base, start, cutoff, feed, cancelled)
            native, _ = self._alpaca(symbol, base, start, cutoff, feed, cancelled, adjustment="raw")
            native_by_ts = {r["ts"]:r for r in native}
            for row in raw:
                original = native_by_ts.get(row["ts"])
                if not valid_prices(row) or not original or not valid_prices(original):
                    row["close"] = None  # Missing raw counterpart cannot establish share sizing.
                    continue
                factor = original["close"]/row["close"]
                if any(not math.isclose(original[k]/row[k],factor,rel_tol=1e-5) for k in ("open","high","low")):
                    raise ValueError("Raw and split-adjusted Alpaca bars disagree; retry with a consistent snapshot")
                row["split_factor"] = factor
        rows, quality = normalize(raw, base, interval, start, cutoff)
        if not rows:
            raise ValueError("The provider returned no complete regular-session candles for this window")
        if len(rows) > 50000:
            raise ValueError("Shorten this request to at most 50,000 stock candles")
        from importlib.metadata import version
        return {"rows":rows, "quality":quality, "market_data":{
            "calendar_package_version":version("pandas_market_calendars"),
            "provider":provider, "feed":feed if provider == "alpaca" else "Yahoo consolidated historical chart",
            "symbol":symbol, "currency":"USD", "asset_class":"equity", "interval":interval,
            "requested_start_ts":start, "cutoff_ts":cutoff, "recorded_at":int(time.time()),
            "minimum_delay_minutes":20, "live_quotes":False, "dividends_included":False,
            "adjustment":"split-adjusted OHLC; cash dividends excluded", **extra}}

    def _yahoo_chunks(self, symbol, start, end, cancelled):
        # The minute endpoint limits the duration of each request separately
        # from its rolling retention. Keep requests shorter than seven days.
        rows, extra, events = {}, {}, {}
        cursor = start
        while cursor < end:
            if cancelled and cancelled():
                raise InterruptedError("Stock minute download cancelled")
            boundary = min(end,cursor+6*DAY)
            batch, metadata = self._yahoo(symbol,"1m",cursor,boundary)
            for row in batch:
                if cursor <= row["ts"] < boundary:
                    rows[row["ts"]] = row
            for kind, group in metadata.get("corporate_actions",{}).items():
                events.setdefault(kind,{}).update(group)
            extra = metadata
            cursor = boundary
        result = sorted(rows.values(),key=lambda r:r["ts"])
        # All chunks use today's split-adjusted prices. Earlier chunks must also
        # carry splits whose event dates were returned by a later chunk.
        for row in result:
            factor = 1.
            for event in events.get("splits",{}).values():
                if row["ts"] < int(event["date"])*1000:
                    ratio = float(event["numerator"])/float(event["denominator"])
                    if not math.isfinite(ratio) or ratio <= 0:
                        raise ValueError("Invalid stock split record")
                    factor *= ratio
            row["split_factor"] = factor
        return result, dict(extra,corporate_actions=events,minute_request_days=6)

    def _yahoo(self, symbol, interval, start, end):
        response = self.http.get("https://query1.finance.yahoo.com/v8/finance/chart/"+symbol.replace(".","-"),
            params={"period1":start//1000, "period2":end//1000, "interval":interval,
                    "includePrePost":"false", "events":"div,splits"},
            headers={"User-Agent":"Mozilla/5.0"}, timeout=25)
        if response.status_code != 200:
            raise RuntimeError(f"Yahoo data unavailable (HTTP {response.status_code}); retry later or select configured Alpaca data")
        chart = response.json().get("chart", {})
        if chart.get("error") or not chart.get("result"):
            raise ValueError("Yahoo returned no historical data for this ticker and period")
        data = chart["result"][0]
        meta = data["meta"]
        if (meta.get("currency") != "USD" or meta.get("exchangeTimezoneName") != "America/New_York"
                or meta.get("instrumentType") not in ("EQUITY", "ETF")):
            raise ValueError("This practice workspace supports US-listed USD stocks and ETFs only")
        quote = data["indicators"]["quote"][0]
        rows = [{"ts":int(ts)*1000, **{k:quote[k][i] for k in ("open", "high", "low", "close", "volume")}}
                for i, ts in enumerate(data.get("timestamp", []))]
        splits = list(data.get("events",{}).get("splits",{}).values())
        for row in rows:
            factor = 1.
            for event in splits:
                if row["ts"] < int(event["date"])*1000:
                    ratio = float(event["numerator"])/float(event["denominator"])
                    if not math.isfinite(ratio) or ratio <= 0:
                        raise ValueError("Invalid stock split record")
                    factor *= ratio
            row["split_factor"] = factor
        return rows, {"exchange":meta.get("exchangeName"), "instrument_type":meta.get("instrumentType"),
                      "corporate_actions":data.get("events", {}), "provider_guarantee":False}

    def _alpaca(self, symbol, interval, start, end, feed, cancelled, adjustment="split"):
        params = {"symbols":symbol, "timeframe":"1Day" if interval == "1d" else str(INTERVAL_MS[interval]//60000)+"Min",
                  "start":iso(start), "end":iso(end), "limit":10000, "adjustment":adjustment,
                  "feed":feed, "sort":"asc"}
        headers = {"APCA-API-KEY-ID":self.key, "APCA-API-SECRET-KEY":self.secret}
        rows, tokens = [], set()
        for _ in range(45):
            if cancelled and cancelled():
                raise InterruptedError("Stock download cancelled")
            response = self.http.get("https://data.alpaca.markets/v2/stocks/bars", params=params,
                                     headers=headers, timeout=25)
            if response.status_code != 200:
                raise RuntimeError(f"Alpaca data unavailable (HTTP {response.status_code}); check data entitlement and credentials")
            data = response.json()
            for b in data.get("bars", {}).get(symbol, []):
                rows.append({"ts":int(datetime.fromisoformat(b["t"].replace("Z", "+00:00")).timestamp()*1000),
                    **{k:b[v] for k,v in {"open":"o", "high":"h", "low":"l", "close":"c", "volume":"v"}.items()},
                    "trades":b.get("n", 0)})
            token = data.get("next_page_token")
            if not token:
                return rows, {"instrument_type":"US equity", "provider_guarantee":False}
            if token in tokens:
                raise RuntimeError("Alpaca repeated a pagination token; no partial download was accepted")
            tokens.add(token)
            params["page_token"] = token
        raise ValueError("Stock source download exceeded 450,000 source bars; shorten the requested period")
