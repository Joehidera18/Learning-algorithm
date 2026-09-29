"""Small, fixed-endpoint news and quote readers. No broker/order requests."""
from __future__ import annotations

import html
import json
import math
import os
import re
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime

from .crypto_watch import DAY, STEP, SYMBOLS as CRYPTO
from .equity_data import WATCHLIST, NY, schedule_between
from .event_context import canonical_url, digest
from .event_feeds import NoRedirect, clean, date_ms

STOCKS = WATCHLIST + ("NTLA",)
ASSETS = STOCKS + CRYPTO
NAMES = dict(zip(STOCKS, (
    "Vertex Pharmaceuticals", "Alnylam", "Broadcom", "Alphabet", "TSMC", "Eaton",
    "NVIDIA", "argenx", "Constellation Energy", "Insmed", "Vertiv", "IBM",
    "Beam Therapeutics", "CRISPR Therapeutics", "ASML", "Keysight", "Arista Networks",
    "Rubrik", "Viking Therapeutics", "IonQ", "Intellia")))
NAMES.update(dict(zip(CRYPTO, ("Bitcoin", "Hedera", "Ethereum", "Solana", "XRP",
    "Stellar", "Chainlink", "Cardano", "Dogecoin", "Avalanche", "Litecoin", "Bitcoin Cash"))))
ALIASES = {s: [name] for s, name in NAMES.items()}
ALIASES["GOOGL"] += ["Google"]
ALIASES["TSM"] += ["Taiwan Semiconductor"]
ALIASES["XRP-USD"] += ["Ripple"]
ALIASES["ETH-USD"] += ["Ether"]

# Source identity is fixed by code. User-supplied calendar links are never fetched.
FEEDS = {
    "hedera": {"name": "Hedera announcements", "url": "https://hedera.com/feed/",
        "origin": "primary", "symbols": ["HBAR-USD"]},
    "hedera_status": {"name": "Hedera network status", "url": "https://status.hedera.com/history.atom",
        "origin": "primary", "symbols": ["HBAR-USD"]},
    "intellia": {"name": "Intellia investor releases", "url": "https://ir.intelliatx.com/rss/news-releases.xml",
        "origin": "primary", "symbols": ["NTLA"]},
    "crispr": {"name": "CRISPR investor releases", "url": "https://ir.crisprtx.com/rss/news-releases.xml",
        "origin": "primary", "symbols": ["CRSP"]},
    "stock_news": {"name": "Yahoo Finance stock headlines", "origin": "reporting", "symbols": [],
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?" + urllib.parse.urlencode({"s": ",".join(STOCKS), "region": "US", "lang": "en-US"})},
    "crypto_news": {"name": "CoinDesk crypto headlines", "origin": "reporting", "symbols": [],
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss"},
    "fed": {"name": "Federal Reserve monetary policy", "origin": "primary", "symbols": ["*"],
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml"},
    "coinbase_status": {"name": "Coinbase operational status", "origin": "primary", "symbols": ["*"],
        "url": "https://status.coinbase.com/history.rss"},
}


def read_url(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "Stock-Lab-Market-Radar/1.0", **(headers or {})})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Response exceeds the 1 MB limit")
    return raw


def fetch_news(source):
    return read_url(FEEDS[source]["url"], {"Accept": "application/rss+xml, application/atom+xml, application/xml"})


def matched_assets(title):
    result = set()
    unambiguous = {"VRTX", "ALNY", "AVGO", "GOOGL", "NVDA", "ARGX", "INSM", "CRSP", "ASML", "ANET", "RBRK", "VKTX", "IONQ", "NTLA", "BTC", "ETH", "XRP", "XLM", "AVAX", "DOGE", "LTC", "BCH"}
    for symbol, names in ALIASES.items():
        if any(re.search(r"\b" + re.escape(name) + r"\b", title, re.I) for name in names):
            result.add(symbol)
        # Do not treat ordinary words (LINK, BEAM, KEYS, etc.) as ticker evidence.
        code = symbol.removesuffix("-USD")
        if re.search(r"(?:\$|\b(?:NASDAQ|NYSE)\s*:\s*)" + re.escape(code) + r"\b", title, re.I):
            result.add(symbol)
        if code in unambiguous and re.search(r"\b" + re.escape(code) + r"\b", title):
            result.add(symbol)
    if "HBAR" in title.upper():
        if re.search(r"\bHBAR\b", title, re.I):
            result.add("HBAR-USD")
    if "BCH-USD" in result and not re.search(r"\bBTC\b", title, re.I):
        result.discard("BTC-USD")
    return sorted(result)


def category(title, source):
    """A review topic, never a sentiment, materiality score or buy probability."""
    if source.endswith("status"):
        return "operations"
    if source == "fed":
        return "monetary policy"
    for label, pattern in (
        ("security", r"hack|exploit|breach|vulnerab|security incident"),
        ("financing / supply", r"offering|dilution|raise[sd]?\b|financing|unlock|buyback|repurchase"),
        ("clinical / regulatory", r"\bFDA\b|\bEMA\b|trial|clinical|approval|safety|PDUFA|readout"),
        ("earnings / guidance", r"earnings|financial results|guidance|outlook"),
        ("commercial / product", r"partner|agreement|contract|launch|acquir|acquisit|upgrade|release|deploy"),
    ):
        if re.search(pattern, title, re.I):
            return label
    return "general"


def parse_news(source, raw, observed):
    if len(raw) > 1_000_000 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Feed size or entity declaration rejected")
    root = ET.fromstring(raw)
    if root.tag.split("}")[-1] not in ("rss", "feed", "RDF"):
        raise ValueError("Expected RSS or Atom")
    entries = [e for e in root.iter() if e.tag.split("}")[-1] in ("item", "entry")]
    if len(entries) > 600:
        raise ValueError("Too many feed entries")
    items, rejected = [], 0
    for entry in entries:
        try:
            values = {e.tag.split("}")[-1]: (e.text or "").strip() for e in entry}
            title = clean(values.get("title"))
            # Incident pages may keep their title while adding material updates.
            # Hash the supplied feed body without storing/displaying its full text.
            body = " ".join(" ".join(e.itertext()) for e in entry
                if e.tag.split("}")[-1] in ("summary", "content", "description", "encoded"))
            body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
            url = values.get("link") or next((e.attrib.get("href") for e in entry
                if e.tag.split("}")[-1] == "link" and e.attrib.get("rel", "alternate") == "alternate"), None)
            url = canonical_url(url)
            published = date_ms(values.get("published") or values.get("pubDate") or values.get("date") or values.get("updated") or "")
            updated = date_ms(values.get("updated") or values.get("pubDate") or values.get("published") or values.get("date") or "")
            if not title or not 0 < published <= updated <= observed:
                raise ValueError("Missing, future or inconsistent timestamp")
            if observed - updated > 30 * DAY:
                continue
            if re.search(r"sponsored|price prediction|\bpresale\b|100x|next coin to explode", title, re.I):
                continue
            assets = FEEDS[source]["symbols"] or matched_assets(title)
            if not assets:
                continue
            item = {"id": digest(url), "url": url, "title": title, "source": source,
                "origin": FEEDS[source]["origin"], "assets": assets, "published_ts": published,
                "updated_ts": updated, "category": category(title, source)}
            item["content_key"] = digest([title, body])
            item["revision"] = digest([title, published, updated, item["content_key"]])
            # Same headline on another feed is a possible reprint, not confirmation.
            item["headline_key"] = digest(re.sub(r"\W+", " ", title.casefold()).strip())
            items.append(item)
        except (ValueError, TypeError, OverflowError, OSError):
            rejected += 1
    if entries and rejected == len(entries):
        raise ValueError("No entries have usable dates and source links")
    return items, rejected


def source_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "Source returned HTTP " + str(exc.code) + "; check access or try a later scan."
    if isinstance(exc, (TimeoutError, urllib.error.URLError)):
        return "Source timed out or could not be reached."
    return "Source response was unusable (" + type(exc).__name__ + ")."


class StockSnapshots:
    def __init__(self):
        self.key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
        self.secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY") or ""
        self.feed = os.getenv("RADAR_STOCK_FEED", "iex").lower()

    def info(self):
        return {"configured": bool(self.key and self.secret), "feed": self.feed,
            "coverage": "IEX only; not the whole US market" if self.feed == "iex" else "SIP; subscription required",
            "error": None if self.feed in ("iex", "sip") else "RADAR_STOCK_FEED must be iex or sip"}

    def snapshots(self):
        if not self.info()["configured"] or self.info()["error"]:
            raise ValueError("Stock data is not configured")
        query = urllib.parse.urlencode({"symbols": ",".join(STOCKS), "feed": self.feed})
        raw = read_url("https://data.alpaca.markets/v2/stocks/snapshots?" + query,
            {"Accept": "application/json", "APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret})
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Unexpected snapshot response")
        return value


def stock_observation(symbol, snapshot, observed, feed, previous=None):
    result = {"symbol": symbol, "stage": "unavailable", "observed_ts": observed,
        "quote_ts": None, "price": None, "change_pct": None, "interval_change_pct": None,
        "feed": feed, "reason": "Missing stock snapshot", "initial_observation": True}
    try:
        schedule = schedule_between(observed - 10 * DAY, observed)
        current = next((s for s in schedule if s[1] <= observed < s[2]), None)
        if not current:
            result.update(stage="market_closed", reason="Regular US session closed; price alerts pause. News continues.")
            return result
        if not isinstance(snapshot, dict):
            return result
        trade, prior = snapshot["latestTrade"], snapshot["prevDailyBar"]
        quote_ts, prior_ts = date_ms(trade["t"]), date_ms(prior["t"])
        if not current[1] <= quote_ts <= observed or observed - quote_ts > 2 * STEP:
            raise ValueError("Quote is stale, future-dated or outside the regular session")
        prior_session = next(s for s in reversed(schedule) if s[2] < current[1])
        if str(datetime.fromtimestamp(prior_ts / 1000, NY).date()) != prior_session[0]:
            raise ValueError("Previous close is not from the preceding trading session")
        price, close = trade["p"], prior["c"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in (price, close)):
            raise ValueError("Invalid price or previous close")
        change = 100 * (price / close - 1)
        if not math.isfinite(change):
            raise ValueError("Non-finite price change")
        result.update(quote_ts=quote_ts, price=price, change_pct=change, session=current[0],
            previous_close=close, previous_close_ts=prior_ts, stage="quiet",
            reason="No price-change threshold met; no volume confirmation is inferred")
        if (previous and previous.get("stage") not in ("unavailable", "market_closed") and previous.get("feed") == feed
                and previous.get("session") == current[0] and previous.get("price", 0) > 0
                and 0 < observed - previous["observed_ts"] <= 2 * STEP
                and 0 < quote_ts - previous["quote_ts"] <= 2 * STEP):
            result["initial_observation"] = False
            result["interval_change_pct"] = 100 * (price / previous["price"] - 1)
        if abs(change) >= 5:
            result.update(stage="large_move", reason="Already moved at least 5% from the unadjusted prior close; verify news and corporate actions")
        elif result["interval_change_pct"] is not None and abs(result["interval_change_pct"]) >= 2:
            result.update(stage="momentum_change", reason="Price changed at least 2% between fresh observations; direction can reverse")
    except (KeyError, TypeError, ValueError, OverflowError, StopIteration) as exc:
        result.update(stage="unavailable", reason=str(exc)[:180])
    return result
