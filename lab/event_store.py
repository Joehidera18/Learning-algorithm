"""Persistent, revision-preserving event collection, outside the trading loop."""
import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

from .db import connect
from .event_context import EventIndex, VERSION, digest, validate_snapshot
from .event_feeds import SOURCES, fetch, parse, source_info


def now_ms():
    return int(time.time()*1000)


@contextmanager
def transaction(path):
    con=connect(path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            yield con
    finally:
        con.close()


class EventStore:
    def __init__(self, db_path):
        self.db_path=db_path
        with transaction(db_path) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS market_events (
                    source TEXT NOT NULL, event_id TEXT NOT NULL, available_ts INTEGER NOT NULL,
                    data_json TEXT NOT NULL, PRIMARY KEY(source,event_id,available_ts));
                CREATE TABLE IF NOT EXISTS market_event_polls (
                    source TEXT NOT NULL, ts INTEGER NOT NULL, ok INTEGER NOT NULL,
                    ttl_ms INTEGER NOT NULL, error TEXT, PRIMARY KEY(source,ts));
                CREATE TABLE IF NOT EXISTS market_event_settings (id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL);
            """)

    def enabled(self, value=None):
        with transaction(self.db_path) as con:
            if value is not None:
                con.execute("INSERT INTO market_event_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled",(int(value),))
            row=con.execute("SELECT enabled FROM market_event_settings WHERE id=1").fetchone()
        return bool(row and row[0])

    def record_poll(self, source, ts, events=None, error=None):
        if source not in SOURCES:
            raise ValueError("Unconfigured event source")
        if any(e.get("source") != source or e.get("observed_ts") != ts for e in (events or [])):
            raise ValueError("Event observations must match their collection record")
        ok=error is None
        poll={"source":source,"ts":ts,"ok":ok,"ttl_ms":SOURCES[source]["ttl_ms"]}
        validate_snapshot({"version":VERSION,"sources":list(SOURCES),"events":events or [],"polls":[poll]})
        with transaction(self.db_path) as con:
            if con.execute('SELECT 1 FROM market_event_polls WHERE source=? AND ts=?',(source,ts)).fetchone():
                raise ValueError('A source poll at this timestamp is already recorded')
            previous={}
            for row in con.execute("SELECT data_json FROM market_events WHERE source=? ORDER BY available_ts",(source,)):
                e=json.loads(row[0]); previous[e["id"]]=e
            current=list(events or [])
            if ok and SOURCES[source]["kind"] in ("ics","fomc"):
                present={e["id"] for e in current}
                # Only complete successful calendar snapshots can withdraw an absent schedule.
                for e in previous.values():
                    if e["id"] not in present and e["status"]=="scheduled" and e["event_ts"]>ts:
                        updated={**e,"status":"withdrawn","observed_ts":ts,"available_ts":max(e["published_ts"],ts)}
                        updated["revision"]=digest([e["revision"],"removed_from_calendar",ts])
                        current.append(updated)
            if ok:
                for e in current:
                    if previous.get(e["id"],{}).get("revision")==e["revision"]:
                        continue
                    con.execute("INSERT INTO market_events VALUES(?,?,?,?)",(
                        source,e["id"],e["available_ts"],json.dumps(e,sort_keys=True,allow_nan=False)))
            con.execute("INSERT INTO market_event_polls VALUES(?,?,?,?,?)",(
                source,ts,int(ok),poll["ttl_ms"],str(error)[:300] if error else None))

    def snapshot(self):
        con=connect(self.db_path)
        try:
            con.execute("BEGIN")
            events=[json.loads(r[0]) for r in con.execute("SELECT data_json FROM market_events ORDER BY available_ts,source,event_id")]
            polls=[dict(r) for r in con.execute("SELECT source,ts,ok,ttl_ms,error FROM market_event_polls ORDER BY ts,source")]
            for p in polls:p["ok"]=bool(p["ok"])
            return {"version":VERSION,"sources":list(SOURCES),"source_info":source_info(),"events":events,"polls":polls}
        finally:
            con.close()


class EventCollector:
    def __init__(self, db_path, fetcher=fetch):
        self.store=EventStore(db_path)
        self.fetcher=fetcher
        self.lock=threading.RLock()
        self.refresh_lock=threading.Lock()
        self.stop_event=threading.Event()
        self.initial_poll=threading.Event()
        self.worker=None
        self.generation=0
        self.last_error=None
        self._reload()

    def _reload(self):
        snapshot=self.store.snapshot()
        with self.lock:
            self._snapshot=snapshot
            self.indexes={}
            self.generation+=1
            if any(p['ok'] for p in snapshot['polls']):
                self.initial_poll.set()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self._snapshot)

    def prepare_for_study(self, timeout=15., cancelled=None):
        """Bounded wait in the learning worker, never in an HTTP/status handler.

        Even a failed collection is evidence about missing coverage. Return the
        archive unchanged; observations retain their real receipt timestamps.
        """
        if cancelled and cancelled():
            raise InterruptedError("Learning cancelled")
        self.start()
        deadline=time.monotonic()+max(0.,timeout)
        while not self.initial_poll.is_set():
            if cancelled and cancelled():
                raise InterruptedError("Learning cancelled")
            if self.stop_event.is_set() or not (self.worker and self.worker.is_alive()):
                break
            remaining=deadline-time.monotonic()
            if remaining <= 0:
                break
            self.initial_poll.wait(min(.1,remaining))
        if cancelled and cancelled():
            raise InterruptedError("Learning cancelled")
        return self.snapshot()

    def context(self, symbol, ts, clock="status"):
        with self.lock:
            key=(symbol,clock)
            if key not in self.indexes:
                self.indexes[key]=EventIndex(self._snapshot,symbol)
            return self.indexes[key].at(ts)

    def observed_between(self, symbol, start, end):
        with self.lock:
            key=(symbol,'review')
            if key not in self.indexes:self.indexes[key]=EventIndex(self._snapshot,symbol)
            return self.indexes[key].observed_between(start,end)

    def refresh(self, due_only=False):
        if not self.refresh_lock.acquire(blocking=False):
            return False
        try:
            with self.lock:
                latest={p['source']:p['ts'] for p in self._snapshot['polls']}
            ts=now_ms()
            due=[s for s,d in SOURCES.items() if not due_only or
                 ts-latest.get(s,0) >= d['poll_seconds']*1000]
            if not due:return False
            def collect(source):
                try:
                    raw=self.fetcher(source)
                    ts=now_ms()  # Receipt time, not the start of a slow request.
                    entries=parse(source,raw,ts)
                    if not entries:
                        raise ValueError("Empty feed; coverage cannot be confirmed")
                    self.store.record_poll(source,ts,entries)
                except Exception as exc:
                    self.store.record_poll(source,now_ms(),error=str(exc))
            # Bounded I/O concurrency; historical replay never calls this method.
            with ThreadPoolExecutor(max_workers=3) as pool:
                tasks=[pool.submit(collect,s) for s in due if not self.stop_event.is_set()]
                for task in as_completed(tasks):
                    task.result()
                    # Publish completed feeds immediately; a slow source must not
                    # hide successful observations until the entire batch ends.
                    self._reload()
            self.last_error=None
            return True
        finally:
            self.refresh_lock.release()
            # Include a completed storage-error attempt in readiness. Historical
            # learning can continue with explicitly unavailable event coverage.
            self.initial_poll.set()

    def _run(self):
        while not self.stop_event.is_set():
            try:self.refresh(due_only=True)
            except Exception as exc:
                self.last_error=str(exc)[:300]
                # A storage failure cannot terminate position management. Existing
                # poll times expire naturally and are displayed as stale.
            if self.stop_event.wait(30):break

    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                if self.stop_event.is_set():
                    raise ValueError("Event collection is stopping; wait for the current requests to finish")
                return
            self.store.enabled(True)
            self.stop_event.clear()
            self.worker=threading.Thread(target=self._run,daemon=True,name="market-events")
            self.worker.start()

    def stop(self, persist=True):
        with self.lock:
            if persist:self.store.enabled(False)
            self.stop_event.set()

    def status(self):
        ts=now_ms()
        with self.lock:
            context=self.context("*",ts)
            latest={p["source"]:p for p in self._snapshot["polls"]}
            return {"running":bool(self.worker and self.worker.is_alive() and not self.stop_event.is_set()),
                "last_error":self.last_error,
                "asof_ts":ts,"versions":len(self._snapshot["events"]),**context,
                "sources":[{"id":s,"name":v["name"],"url":v["url"],
                    "category":v['category'], "assets":v.get('assets',['*']), "origin":v['origin'],
                    "poll_seconds":v['poll_seconds'],
                    "last_poll_ts":latest.get(s,{}).get("ts"),
                    "healthy":s in context["healthy_sources"],"error":latest.get(s,{}).get("error")}
                    for s,v in SOURCES.items()],
                "scope":"Selected sources, not all world news. Reporting can contain unverified claims. "
                    "Project feeds use fixed asset tags; other asset tags are headline matches. "
                    "Client releases do not establish mainnet activation. News/incident feeds are checked about every five minutes, others every fifteen; publisher delays also apply. "
                    "Regulatory announcements may be proposals, statements or actions; they are not classified as enacted law. "
                    "Schedules can change and do not predict release outcomes."}
