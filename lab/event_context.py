"""Point-in-time event inputs. Publication, observation and occurrence are distinct.

Nothing collected today is backdated into yesterday's decision. A calendar entry
describes a schedule, never the unreleased result. No headline sentiment or claim
of causal attribution is inferred here.
"""
import bisect
import hashlib
import json
import math
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

VERSION = 1
HOUR = 3600000
DAY = 24*HOUR
BASE_CATEGORIES = ("macro", "regulation", "crypto", "exchange")
CATEGORIES = BASE_CATEGORIES + ("world", "project", "sentiment")
INPUT_NAMES = ("event_coverage", "event_macro_24h", "event_regulation_24h",
               "event_crypto_24h", "event_exchange_24h", "event_upcoming_24h", "event_upcoming_7d",
               "event_world_24h", "event_project_30d") + tuple("event_"+c+"_coverage" for c in CATEGORIES) + (
               "sentiment_available", "sentiment_value", "sentiment_change_available", "sentiment_change")


def news_window(category):
    return 30*DAY if category == 'project' else 2*DAY if category == 'sentiment' else DAY


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def timestamp(value):
    if type(value) is not int or not 0 <= value <= 32503680000000:
        raise ValueError("Event timestamps must be integer UTC milliseconds")
    return value


def source_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("Invalid event source link")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or
            any(ord(c)<33 or c in '<>"' for c in value)):
        raise ValueError("Event source links must use HTTPS")
    return value


def canonical_url(value):
    """Remove known tracking fields, preserving parameters identifying articles."""
    parsed = urlsplit(source_url(value))
    query = [(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in
             ('at_medium','at_campaign','fbclid','gclid','mc_cid','mc_eid')]
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(sorted(query)),''))


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("version") != VERSION:
        raise ValueError("Unsupported event archive version")
    sources = snapshot.get("sources")
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 50 or
            any(not isinstance(s,str) or not s or len(s)>80 for s in sources) or len(set(sources)) != len(sources)):
        raise ValueError("Invalid event archive sources")
    info = snapshot.get("source_info", {})
    if not isinstance(info,dict) or not set(info).issubset(sources):
        raise ValueError("Invalid event source definitions")
    for definition in info.values():
        if not isinstance(definition,dict) or definition.get('category') not in CATEGORIES:
            raise ValueError("Invalid source category")
        assets = definition.get('assets')
        if (not isinstance(assets,list) or not assets or len(assets)>100 or
                any(not isinstance(a,str) or not a or len(a)>30 for a in assets)):
            raise ValueError("Invalid source asset scope")
    events, polls = snapshot.get("events"), snapshot.get("polls")
    if not isinstance(events,list) or not isinstance(polls,list) or len(events)+len(polls)>500000:
        raise ValueError("Event archive is too large or incomplete")
    seen = set()
    for e in events:
        if not isinstance(e,dict):
            raise ValueError("Invalid event record")
        for k in ("id","revision","title"):
            if not isinstance(e.get(k),str) or not e[k] or len(e[k])>500:
                raise ValueError("Invalid event identity or title")
        if e.get("source") not in sources or e.get("category") not in CATEGORIES:
            raise ValueError("Invalid event source or category")
        if e.get("status") not in ("announcement","scheduled","cancelled","withdrawn"):
            raise ValueError("Invalid event status")
        if e.get("precision") not in ("time","day"):
            raise ValueError("Invalid event time precision")
        for k in ("published_ts","observed_ts","available_ts","event_ts"):
            timestamp(e.get(k))
        if e["available_ts"] != max(e["published_ts"], e["observed_ts"]):
            raise ValueError("Event availability must include first observation of this revision")
        if e["category"] == "sentiment" and (e["source"] != "alternative_fng"
                or e["status"] != "announcement" or type(e.get("sentiment_value")) is not int
                or not 0 <= e["sentiment_value"] <= 100 or e["published_ts"] > e["observed_ts"]):
            raise ValueError("Invalid dated sentiment observation")
        assets = e.get("assets")
        if (not isinstance(assets,list) or not assets or len(assets)>100 or
                any(not isinstance(a,str) or not a or len(a)>30 for a in assets)):
            raise ValueError("Invalid affected assets")
        source_url(e.get("url"))
        key = (e["source"], e["id"], e["available_ts"])
        if key in seen:
            raise ValueError("Ambiguous event revisions at the same timestamp")
        seen.add(key)
    seen_polls = set()
    for p in polls:
        if not isinstance(p,dict) or p.get("source") not in sources or type(p.get("ok")) is not bool:
            raise ValueError("Invalid event collection record")
        timestamp(p.get("ts"))
        if type(p.get("ttl_ms")) is not int or not HOUR//4 <= p["ttl_ms"] <= 7*DAY:
            raise ValueError("Invalid event freshness interval")
        key = (p['source'],p['ts'])
        if key in seen_polls:
            raise ValueError("Ambiguous source polls at the same timestamp")
        seen_polls.add(key)
    return snapshot


class EventIndex:
    """Advance only at changes, avoiding a news scan for every market candle."""
    def __init__(self, snapshot, symbol="*"):
        self.snapshot = validate_snapshot(snapshot)
        self.symbol = symbol
        self.events = sorted(snapshot["events"], key=lambda e:(e["available_ts"],e["source"],e["id"]))
        self.available = [e['available_ts'] for e in self.events]
        self.polls = sorted(snapshot["polls"], key=lambda p:(p["ts"],p["source"]))
        changes = {0}
        for e in self.events:
            changes.update((e["available_ts"], e["published_ts"]+news_window(e['category'])))
            if e["status"] == "scheduled":
                changes.update((max(0,e["event_ts"]-7*DAY), max(0,e["event_ts"]-DAY), e["event_ts"]+1))
        for p in self.polls:
            changes.update((p["ts"],p["ts"]+p["ttl_ms"]))
        self.changes = sorted(changes)
        self.reset()

    def observed_between(self, start, end, limit=20):
        """After-entry revisions for review only, never retrospective features."""
        timestamp(start); timestamp(end)
        if end < start or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid event observation window')
        begin, finish = bisect.bisect_right(self.available,start), bisect.bisect_right(self.available,end)
        records = [e for e in self.events[begin:finish]
                   if self.symbol == '*' or '*' in e['assets'] or self.symbol in e['assets']]
        return {'versions_observed':len(records), 'truncated':len(records)>limit,
                'items':records[-limit:], 'start_exclusive_ts':start, 'end_inclusive_ts':end}

    def reset(self):
        self.ei = self.pi = 0
        self.latest, self.health = {}, {}
        self.last_ts, self.next_change, self.cached = -1, -1, None

    def at(self, ts):
        timestamp(ts)
        if ts < self.last_ts:
            self.reset()
        self.last_ts = ts
        if self.cached is not None and ts < self.next_change:
            return self.cached
        while self.ei < len(self.events) and self.events[self.ei]["available_ts"] <= ts:
            e = self.events[self.ei]
            self.latest[(e["source"],e["id"])] = e
            self.ei += 1
        while self.pi < len(self.polls) and self.polls[self.pi]["ts"] <= ts:
            p = self.polls[self.pi]
            self.health[p["source"]] = p
            self.pi += 1
        healthy = sorted(s for s,p in self.health.items() if p["ok"] and ts < p["ts"]+p["ttl_ms"])
        recent, upcoming = [], []
        for e in self.latest.values():
            if e["status"] in ("cancelled","withdrawn") or (self.symbol != "*" and "*" not in e["assets"] and self.symbol not in e["assets"]):
                continue
            if e["status"] == "scheduled" and 0 <= e["event_ts"]-ts <= 7*DAY:
                upcoming.append(e)
            elif e["status"] == "announcement" and ts-news_window(e['category']) < e["published_ts"] <= ts:
                recent.append(e)
        # Revisions and repeated copies of the same URL count once, not as sentiment votes.
        recent = list({(e["source"],e["id"]) if e["category"] == "sentiment" else canonical_url(e["url"]):e
                       for e in sorted(recent,key=lambda e:e["available_ts"])}.values())
        upcoming.sort(key=lambda e:(e["event_ts"],e["id"]))
        recent.sort(key=lambda e:e["published_ts"], reverse=True)
        sentiment_rows = [e for e in recent if e["category"] == "sentiment" and e["source"] in healthy]
        sentiment = {"available":False, "value":None, "change_1d":None,
            "scope":"Alternative.me's Bitcoin-focused market index; not a coin-specific signal or a buy/sell rule."}
        if sentiment_rows:
            current = sentiment_rows[0]
            previous = next((e for e in sentiment_rows[1:]
                             if e["published_ts"] == current["published_ts"]-DAY), None)
            sentiment.update(available=True, value=current["sentiment_value"],
                change_1d=current["sentiment_value"]-previous["sentiment_value"] if previous else None,
                published_ts=current["published_ts"], observed_ts=current["observed_ts"],
                available_ts=current["available_ts"], source=current["source"], url=current["url"])
        definitions = self.snapshot.get('source_info',{})
        category_coverage = {}
        for category in CATEGORIES:
            relevant = [s for s,d in definitions.items() if d['category']==category and
                        (self.symbol=='*' or '*' in d['assets'] or self.symbol in d['assets'])]
            category_coverage[category] = (sum(s in healthy for s in relevant)/len(relevant)
                                           if relevant else None)
        self.cached = {"coverage":len(healthy)/len(self.snapshot["sources"]), "healthy_sources":healthy,
            "sentiment":sentiment,
            "category_coverage":category_coverage,
            "recent_counts":{c:sum(e["category"]==c for e in recent) for c in CATEGORIES},
            "upcoming_24h":sum(e["event_ts"]-ts <= DAY for e in upcoming), "upcoming_7d":len(upcoming),
            "recent":[e for e in recent if e['category'] not in ('project','sentiment')][:12],
            "projects":[e for e in recent if e['category']=='project'][:8],
            "upcoming":upcoming[:12]}
        pos = bisect.bisect_right(self.changes,ts)
        self.next_change = self.changes[pos] if pos < len(self.changes) else math.inf
        return self.cached


def vector(context):
    if not context or not context.get("coverage"):
        return [0.]*len(INPUT_NAMES)
    # Missing source coverage is an explicit input. Counts have no directional sign.
    sentiment = context.get("sentiment", {})
    available = bool(sentiment.get("available"))
    change = sentiment.get("change_1d") if available else None
    return [context["coverage"]] + [min(1.,context["recent_counts"].get(c,0)/10) for c in BASE_CATEGORIES] + [
        min(1.,context["upcoming_24h"]/5), min(1.,context["upcoming_7d"]/10)] + [
        min(1.,context['recent_counts'].get(c,0)/10) for c in ('world','project')] + [
        context.get('category_coverage',{}).get(c) or 0. for c in CATEGORIES] + [
        float(available), (sentiment["value"]-50)/50 if available else 0.,
        float(change is not None), change/100 if change is not None else 0.]


def attach_event_context(rows, features, step, snapshot, symbol):
    if len(rows) != len(features):
        raise ValueError("Event context must match decision candles")
    index = EventIndex(snapshot,symbol)
    for row, f in zip(rows,features):
        if f:
            f["event_context"] = index.at(row["ts"]+step)
    return features


def data_summary(snapshot, features, start):
    contexts = [(f or {}).get("event_context",{}) for f in features[start:]]
    return {"source":"recorded_event_observations" if snapshot else "unavailable",
        "data_sha256":digest(snapshot) if snapshot else None,
        "versions":len(snapshot["events"]) if snapshot else 0,
        "first_observation_ts":min((p["ts"] for p in snapshot["polls"] if p["ok"]),default=None) if snapshot else None,
        "covered_candles":sum((f or {}).get("event_context",{}).get("coverage",0)>0 for f in features),
        "holdout_candles":len(contexts),
        "holdout_covered_candles":sum(c.get("coverage",0)>0 for c in contexts),
        "holdout_full_coverage_candles":sum(c.get("coverage",0)==1 for c in contexts),
        "sentiment_covered_candles":sum(bool((f or {}).get("event_context",{}).get("sentiment",{}).get("available")) for f in features),
        "sentiment_holdout_candles":sum(bool(c.get("sentiment",{}).get("available")) for c in contexts),
        "rule":"Only revisions observed by the signal close are included. Missing/stale collection is unknown. "
            "Upcoming events contain schedules, not unreleased results. Event associations do not establish why a market moved."}


def without_sentiment(snapshot):
    """Remove the source as well as its coverage input for the matched control."""
    sources = [s for s in snapshot["sources"] if s != "alternative_fng"]
    if not sources:
        return None
    return {**snapshot, "sources":sources,
        "source_info":{s:d for s,d in snapshot.get("source_info",{}).items() if s in sources},
        "events":[e for e in snapshot["events"] if e["source"] in sources],
        "polls":[p for p in snapshot["polls"] if p["source"] in sources]}


def outcome_summary(trades):
    groups = {}
    for t in trades:
        if t.get("reason") == "END":
            continue
        c = (t.get("features") or {}).get("event_context") or {}
        labels = (["coverage_unknown"] if not c.get("coverage") else
            [k for k,v in c.get("recent_counts",{}).items() if v] +
            (["upcoming_24h"] if c.get("upcoming_24h") else []) or ["no_recent_recorded_event"])
        for key in labels:
            g = groups.setdefault(key,{"trades":0,"wins":0,"net_pnl":0.})
            g["trades"] += 1; g["wins"] += int(t["pnl"]>0); g["net_pnl"] += t["pnl"]
    return {"by_entry_context":groups,
        "scope":"Descriptive, overlapping groups of completed trades. Unknown coverage is separate. "
                "No causal explanation or automatic strategy selection is inferred from these groups."}
