"""Download a coin's available Binance spot history and derive complete UTC bars.

One job per coin; SQLite and streaming CSV writers bound memory independently
of listing age. Different venues and quote currencies are never spliced.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.download_hbar_alternatives import CurlCache, SourceError, parse_binance, BINANCE_FIELDS
from lab.study_plan import DEFAULT_PRACTICE_SYMBOLS

MINUTE=60000
FRAMES={'1m':1,'4m':4,'5m':5,'15m':15,'30m':30,'1h':60,'4h':240}
FIELDS=BINANCE_FIELDS


def api(cache,pair,start,end,label,limit=1000):
    url='https://data-api.binance.vision/api/v3/klines?'+urlencode(dict(symbol=pair,interval='1m',startTime=start,endTime=end-1,limit=limit))
    content,meta=cache.get(url,label+'.json')
    payload=json.loads(content)
    if not isinstance(payload,list):raise SourceError('No successful kline list: '+str(payload)[:160])
    rows=[parse_binance(row) for row in payload]
    if any(not start<=row['ts']<end for row in rows):raise ValueError('Out-of-window API candle')
    return rows,meta


def insert(con,rows):
    for row in rows:
        values=tuple(row[k] for k in FIELDS)
        existing=con.execute('SELECT * FROM candles WHERE ts=?',(row['ts'],)).fetchone()
        if existing is not None and existing!=values:raise ValueError('Conflicting source observations')
        if existing is None:con.execute('INSERT INTO candles VALUES ('+','.join('?' for _ in FIELDS)+')',values)
    con.commit()


def missing(con,start,end):
    result=[];cursor=start
    for (stamp,) in con.execute('SELECT ts FROM candles WHERE ts>=? AND ts<? ORDER BY ts',(start,end)):
        if stamp>cursor:result.append({'start_ts':cursor,'end_ts':stamp,'minutes':(stamp-cursor)//MINUTE})
        cursor=stamp+MINUTE
    if cursor<end:result.append({'start_ts':cursor,'end_ts':end,'minutes':(end-cursor)//MINUTE})
    return result


def aggregate_stream(rows,minutes,start,end):
    """A bar exists only when every unique source minute is present and closed."""
    step=minutes*MINUTE
    current=None;chunk=[];previous=None
    for row in rows:
        stamp=row['ts']
        if previous is not None and stamp<=previous:raise ValueError('Duplicate or unordered source minute')
        previous=stamp
        bucket=stamp//step*step
        if bucket!=current:
            current=bucket;chunk=[]
        chunk.append(row)
        if stamp+MINUTE!=bucket+step:continue
        if bucket<start or bucket+step>end or len(chunk)!=minutes:continue
        if any(r['ts']!=bucket+i*MINUTE for i,r in enumerate(chunk)):continue
        result=dict(ts=bucket,open=chunk[0]['open'],high=max(r['high'] for r in chunk),
                    low=min(r['low'] for r in chunk),close=chunk[-1]['close'])
        result.update({k:sum(r[k] for r in chunk) for k in FIELDS[5:]})
        yield result


def export(con,out,pair,start,end):
    reports=[]
    for interval,minutes in FRAMES.items():
        step=minutes*MINUTE;left=(start+step-1)//step*step;right=end//step*step
        expected=max(0,(right-left)//step);count=zero=0;cursor=left;gaps=[]
        path=out/f'binance_{pair}_{interval}.csv.gz'
        source=(dict(zip(FIELDS,row)) for row in con.execute('SELECT * FROM candles ORDER BY ts'))
        with gzip.open(path,'wt',newline='',compresslevel=5) as handle:
            writer=csv.DictWriter(handle,fieldnames=FIELDS);writer.writeheader()
            for row in aggregate_stream(source,minutes,start,end):
                if row['ts']>cursor:gaps.append({'start_ts':cursor,'end_ts':row['ts'],'candles':(row['ts']-cursor)//step})
                cursor=row['ts']+step;writer.writerow(row);count+=1;zero+=row['volume']==0
        if cursor<right:gaps.append({'start_ts':cursor,'end_ts':right,'candles':(right-cursor)//step})
        reports.append(dict(interval=interval,rows=count,zero_volume_rows=zero,expected_candles=expected,
                            missing_candles=expected-count,start_ts=left,end_ts_exclusive=right,
                            coverage_pct=100*count/expected if expected else None,missing_ranges=gaps,
                            file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print(f'{pair} {interval}: {count:,}/{expected:,} candles; {expected-count:,} absent',flush=True)
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coin',required=True,choices=[s.split('-')[0] for s in DEFAULT_PRACTICE_SYMBOLS])
    parser.add_argument('--end-ms',required=True,type=int)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--repair-limit',type=int,default=2000)
    args=parser.parse_args();end=args.end_ms
    if end%MINUTE or end>int(time.time()*1000)//MINUTE*MINUTE:parser.error('Use a closed UTC minute cutoff')
    pair=args.coin+'USDT';out=args.out;out.mkdir(parents=True,exist_ok=True)
    work=out.parent/(out.name+'-work');cache=CurlCache(work/'requests')
    earliest,meta=api(cache,pair,0,end,'first-listing',1)
    if len(earliest)!=1:raise SourceError('Cannot identify first available candle')
    start=earliest[0]['ts']
    if start<1483228800000:raise ValueError('Unexpected listing timestamp')
    con=sqlite3.connect(work/'minutes.sqlite')
    columns=','.join(k+(' INTEGER PRIMARY KEY' if k=='ts' else ' INTEGER' if k=='trades' else ' REAL') for k in FIELDS)
    con.execute('CREATE TABLE IF NOT EXISTS candles ('+columns+')')
    sources=[meta];failures=[]
    day=datetime.fromtimestamp(start/1000,timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    cutoff=datetime.fromtimestamp(end/1000,timezone.utc)
    month=cutoff.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    tasks=[]
    while day<month:
        tasks.append(('monthly',day.strftime('%Y-%m')))
        day=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
    today=cutoff.replace(hour=0,minute=0,second=0,microsecond=0)
    while day<today:
        tasks.append(('daily',day.strftime('%Y-%m-%d')));day+=timedelta(days=1)
    for index,(kind,label) in enumerate(tasks):
        name=f'{pair}-1m-{label}.zip'
        url=f'https://data.binance.vision/data/spot/{kind}/klines/{pair}/1m/{name}'
        try:
            data,meta=cache.get(url,name)
            checksum,_=cache.get(url+'.CHECKSUM',name+'.CHECKSUM')
            if checksum.decode().split()[0]!=hashlib.sha256(data).hexdigest():raise ValueError('Published archive checksum mismatch')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.namelist()!=[name[:-4]+'.csv']:raise ValueError('Unexpected archive contents')
                with archive.open(archive.namelist()[0]) as member:
                    rows=[parse_binance(row,microseconds=label>='2025-01') for row in csv.reader(io.TextIOWrapper(member))]
            insert(con,[r for r in rows if start<=r['ts']<end])
            sources.append(dict(meta,published_checksum_verified=True))
        except (SourceError,ValueError,zipfile.BadZipFile) as exc:
            failures.append(dict(url=url,error=str(exc)))
        if (index+1)%12==0:print(f'{pair}: {index+1}/{len(tasks)} archives checked',flush=True)
    for a in range(int(today.timestamp()*1000),end,999*MINUTE):
        b=min(a+999*MINUTE,end)
        try:
            rows,meta=api(cache,pair,a,b,f'tail-{a}-{b}');insert(con,rows);sources.append(meta)
        except (SourceError,ValueError) as exc:failures.append(dict(start_ts=a,end_ts=b,error=str(exc)))
    before=missing(con,start,end);requests=recovered=0
    for gap in before:
        for a in range(gap['start_ts'],gap['end_ts'],999*MINUTE):
            if requests>=args.repair_limit:break
            b=min(a+999*MINUTE,gap['end_ts']);requests+=1
            try:
                rows,meta=api(cache,pair,a,b,f'repair-{a}-{b}');insert(con,rows)
                recovered+=len(rows);sources.append(meta)
            except (SourceError,ValueError) as exc:failures.append(dict(start_ts=a,end_ts=b,error=str(exc)))
        if requests>=args.repair_limit:break
    after=missing(con,start,end)
    frames=export(con,out,pair,start,end)
    report=dict(coin=args.coin,venue='Binance',market_type='spot',pair=pair,quote_currency='USDT',
                requested_scope='All available minute history from the first public API candle to the fixed cutoff',
                first_available_ts=start,end_ts_exclusive=end,timeframes=frames,sources=sources,source_failures=failures,
                missing_minutes_before_repair=sum(g['minutes'] for g in before),repair_requests=requests,
                recovered_minutes=recovered,missing_minutes_after_repair=sum(g['minutes'] for g in after),
                remaining_minute_gaps=after,repair_budget_exhausted=requests>=args.repair_limit,
                synthetic_candles_added=0,coinbase_history_modified=False,
                generated_at=datetime.now(timezone.utc).isoformat())
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'README.txt').write_text('Binance spot '+pair+'; quote currency USDT. Separate research dataset, not Coinbase USD history.\n'
        'CSV files are gzip-compressed. ts is UTC Unix milliseconds. All frames use complete observed one-minute buckets.\n'
        'Zero-volume buckets come from the provider. Unknown gaps remain absent; no prices are interpolated.\n'
        'See manifest.json for source URLs, verified archive hashes, gaps, repair outcomes, and per-frame checksums.\n'
        'The first and last incomplete higher-timeframe buckets are excluded. No profitability claim.\n')
    con.close()
    print(json.dumps({k:v for k,v in report.items() if k not in ('timeframes','sources','remaining_minute_gaps')},indent=2),flush=True)


if __name__=='__main__':main()
