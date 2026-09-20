"""Bounded, read-only adapters for public news and official event calendars."""
import calendar
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .event_context import DAY, HOUR, digest, canonical_url

SOURCES = {
    "fed_monetary":{"name":"Federal Reserve monetary policy", "kind":"rss", "category":"macro",
        "url":"https://www.federalreserve.gov/feeds/press_monetary.xml", "ttl_ms":HOUR},
    "fed_regulation":{"name":"Federal Reserve regulation", "kind":"rss", "category":"regulation",
        "url":"https://www.federalreserve.gov/feeds/press_bcreg.xml", "ttl_ms":HOUR},
    "sec":{"name":"SEC announcements", "kind":"rss", "category":"regulation",
        "url":"https://www.sec.gov/news/pressreleases.rss", "ttl_ms":HOUR},
    "bls_calendar":{"name":"BLS economic release calendar", "kind":"ics", "category":"macro",
        "url":"https://www.bls.gov/schedule/news_release/bls.ics", "ttl_ms":DAY},
    "fomc_calendar":{"name":"Federal Reserve meeting calendar", "kind":"fomc", "category":"macro",
        "url":"https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "ttl_ms":DAY},
    "coinbase_status":{"name":"Coinbase operational incidents", "kind":"rss", "category":"exchange",
        "url":"https://status.coinbase.com/history.atom", "ttl_ms":HOUR},
    "coindesk":{"name":"CoinDesk headlines (reporting)", "kind":"rss", "category":"crypto",
        "url":"https://www.coindesk.com/arc/outboundfeeds/rss", "ttl_ms":HOUR},
    "bbc_world":{"name":"BBC world news (reporting)", "kind":"rss", "category":"world",
        "url":"https://feeds.bbci.co.uk/news/world/rss.xml", "ttl_ms":HOUR, "assets":["*"]},
    "ethereum_blog":{"name":"Ethereum Foundation announcements", "kind":"rss", "category":"project",
        "url":"https://blog.ethereum.org/en/feed.xml", "ttl_ms":DAY, "assets":["ETH-USD"]},
}
# Client release announcements are not assertions of mainnet activation.
for source, name, repo, asset in (
    ('bitcoin_releases','Bitcoin Core','bitcoin/bitcoin','BTC-USD'),
    ('avalanche_releases','AvalancheGo','ava-labs/avalanchego','AVAX-USD'),
    ('polkadot_releases','Polkadot SDK','paritytech/polkadot-sdk','DOT-USD'),
    ('xrpl_releases','XRPL rippled','XRPLF/rippled','XRP-USD'),
    ('solana_releases','Solana Agave','anza-xyz/agave','SOL-USD')):
    SOURCES[source] = {'name':name+' client releases', 'kind':'rss', 'category':'project',
                      'url':'https://github.com/'+repo+'/releases.atom', 'ttl_ms':DAY, 'assets':[asset]}
for source, definition in SOURCES.items():
    definition['origin'] = ('reporting' if source in ('bbc_world','coindesk') else
                            'project_publication' if definition['category']=='project' else 'official_publication')
    definition['poll_seconds'] = 300 if source in ('bbc_world','coindesk','coinbase_status') else 900


def source_info():
    return {s:{'category':d['category'], 'assets':list(d.get('assets',['*'])), 'origin':d['origin']}
            for s,d in SOURCES.items()}
# Whole names and unambiguous tickers only. Unknown assets remain broad context;
# this deliberately does not treat ordinary words such as "near" or "link" as tickers.
ALIASES = {"BTC-USD":("bitcoin","btc"), "ETH-USD":("ethereum","ether","eth"),
    "XRP-USD":("xrp","ripple"), "SOL-USD":("solana",), "DOT-USD":("polkadot",),
    "LTC-USD":("litecoin","ltc"), "AVAX-USD":("avalanche","avax"),
    "ADA-USD":("cardano",), "DOGE-USD":("dogecoin","doge"),
    "LINK-USD":("chainlink",), "HBAR-USD":("hedera","hbar"), "XLM-USD":("stellar","xlm")}


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()[:400]


def date_ms(value):
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        raise ValueError("Publication time has no timezone")
    return int(dt.timestamp()*1000)


def record(source, identity, title, url, published, observed, event_ts=None,
           status="announcement", precision="time", assets=None):
    title = clean(title)
    if not title or not identity:
        raise ValueError("Event identity/title missing")
    if assets is None:
        assets = SOURCES[source].get('assets') or [symbol for symbol,names in ALIASES.items()
                  if any(re.search(r"\b"+re.escape(name)+r"\b",title,re.I) for name in names)]
        # Macro and regulatory announcements can affect the whole trading universe.
        if SOURCES[source]["category"] in ("macro","regulation") or not assets:
            assets = ["*"]
    data = {"id":digest([source,identity]), "source":source, "title":title,
        "url":canonical_url(url), "published_ts":published, "event_ts":published if event_ts is None else event_ts,
        "origin":SOURCES[source]['origin'],
        "category":SOURCES[source]["category"], "status":status, "precision":precision, "assets":sorted(assets)}
    # Do not include retrieval time in the revision: an unchanged poll is not new news.
    data["revision"] = digest(data)
    return dict(data,observed_ts=observed,available_ts=max(published,observed))


def rss(source, raw, observed):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Feed entities are unsupported")
    root = ET.fromstring(raw)
    if root.tag.split("}")[-1] not in ("rss","feed","RDF"):
        raise ValueError("Expected RSS or Atom, not a web/error page")
    entries = [e for e in root.iter() if e.tag.split("}")[-1] in ("item","entry")]
    result = []
    for entry in entries:
        values = {e.tag.split("}")[-1]:(e.text or "").strip() for e in entry}
        link = values.get("link")
        if not link:
            link = next((e.attrib.get("href") for e in entry if e.tag.split("}")[-1]=="link"
                         and e.attrib.get("rel","alternate")=="alternate"),None)
        published = date_ms(values.get("updated") or values.get("pubDate") or
                            values.get("published") or values.get("date") or "")
        result.append(record(source,values.get("guid") or values.get("id") or canonical_url(link),
            values.get("title"),link,published,observed))
    return result


def ics(source, raw, observed):
    text = raw.decode("utf-8-sig")
    if "BEGIN:VCALENDAR" not in text or "END:VCALENDAR" not in text:
        raise ValueError("Expected a complete calendar")
    text = re.sub(r"\r?\n[ \t]", "", text)
    result = []
    for block in re.findall(r"BEGIN:VEVENT\s*(.*?)END:VEVENT",text,re.S):
        fields, params = {}, {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key,value = line.split(":",1)
            name = key.split(";")[0]
            fields[name],params[name] = value.strip(),key
        if "RRULE" in fields or "RECURRENCE-ID" in fields:
            raise ValueError("Recurring calendar events need explicit occurrences")
        start = fields["DTSTART"]
        zone = re.search(r"TZID=([^;:]+)",params["DTSTART"])
        tz = (zone.group(1).strip('"') if zone else "")
        tz = {"US-Eastern":"America/New_York", "US/Eastern":"America/New_York"}.get(tz,tz)
        precision = "day" if len(start)==8 else "time"
        if start.endswith("Z"):
            dt = datetime.strptime(start,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        elif precision == "day":
            # BLS dates and floating day entries are Eastern; no invented release hour.
            dt = datetime.strptime(start,"%Y%m%d").replace(tzinfo=ZoneInfo(tz or "America/New_York"))
        elif tz:
            dt = datetime.strptime(start,"%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo(tz))
        else:
            raise ValueError("Scheduled release has no timezone")
        event_ts = int(dt.timestamp()*1000)
        # BLS supplies no publication timestamp on many entries. Observation is the
        # first provable availability. A stable zero placeholder is never backdated.
        result.append(record(source,fields["UID"],fields["SUMMARY"].replace("\\,",","),
            SOURCES[source]["url"],0,observed,event_ts,
            "cancelled" if fields.get("STATUS")=="CANCELLED" else "scheduled",precision,["*"]))
    return result


class CalendarHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.field=None; self.depth=0

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="div" and "fomc-meeting__month" in attrs.get("class",""):
            self.field="month"; self.parts.append(("month",""))
        elif tag=="div" and "fomc-meeting__date" in attrs.get("class",""):
            self.field="date"; self.parts.append(("date",""))
        elif tag=="h4":
            self.field="year"; self.parts.append(("year",""))

    def handle_endtag(self,tag):
        if tag in ("div","h4"):
            self.field=None

    def handle_data(self,data):
        if self.field:
            key,value=self.parts[-1]; self.parts[-1]=(key,value+data)


def fomc(source, raw, observed):
    parser=CalendarHTML(); parser.feed(raw.decode("utf-8-sig"))
    result=[]; year=month=None
    for kind,value in parser.parts:
        if kind=="year":
            match=re.search(r"(20\d{2}) FOMC Meetings",value)
            year=int(match.group(1)) if match else None
        elif kind=="month":
            month=value.strip()
        elif year and month and kind=="date":
            # First day of the announced meeting, including cross-month meetings.
            first=month.split("/")[0].strip()
            names={m:i for i,m in enumerate(calendar.month_name) if m}
            names.update({m:i for i,m in enumerate(calendar.month_abbr) if m})
            if first not in names or not re.match(r"^\s*\d{1,2}",value):
                raise ValueError("Unrecognized FOMC date format")
            day=int(re.match(r"^\s*(\d{1,2})",value).group(1))
            dt=datetime(year,names[first],day,tzinfo=ZoneInfo("America/New_York"))
            title=f"FOMC meeting begins: {month} {clean(value)} {year} (date only)"
            result.append(record(source,f"{year}-{month}",title,SOURCES[source]["url"],0,observed,
                int(dt.timestamp()*1000),"scheduled","day",["*"]))
    if not result:
        raise ValueError("FOMC calendar format changed; no meetings parsed")
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Feed redirected; review its configured URL")


def fetch(source):
    url=SOURCES[source]["url"]  # Only fixed, reviewed feed URLs are fetched.
    request=urllib.request.Request(url,headers={"User-Agent":"CryptO-Research/1.0"})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=12) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:
        raise ValueError("Event source exceeds size limit")
    return raw


def parse(source, raw, observed):
    return {"rss":rss,"ics":ics,"fomc":fomc}[SOURCES[source]["kind"]](source,raw,observed)
