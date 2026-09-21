"""Retrieve separately labeled public HBAR spot histories. Never splice venues."""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import subprocess
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

MINUTE = 60000
DAY = 86400000
CORE = ['ts', 'open', 'high', 'low', 'close', 'volume']
BINANCE_FIELDS = CORE + ['quote_volume', 'trades', 'taker_buy_base_volume', 'taker_buy_quote_volume']


def iso(stamp):
    return datetime.fromtimestamp(stamp/1000, timezone.utc).isoformat()


class SourceError(RuntimeError):
    pass


class CurlCache:
    def __init__(self, root):
        self.root = Path(root)

    def get(self, url, name, byte_range=None):
        path = self.root/name
        meta = path.with_name(path.name+'.metadata.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and meta.exists():
            saved = json.loads(meta.read_text())
            if saved['url'] != url or saved['range'] != byte_range:
                raise SourceError('Checkpoint belongs to another request')
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != saved['sha256']:
                raise SourceError('Checkpoint checksum mismatch')
            return content, saved
        temporary = path.with_name(path.name+'.partial')
        headers = path.with_name(path.name+'.headers')
        for attempt in range(2):
            command = ['curl', '--location', '--silent', '--show-error', '--max-time', '25',
                       '--max-filesize', '50000000', '--output', str(temporary),
                       '--dump-header', str(headers), '--write-out', '%{http_code}']
            if byte_range is not None:
                command += ['--range', byte_range]
            result = subprocess.run(command+[url], capture_output=True, text=True)
            status = int(result.stdout[-3:]) if result.stdout[-3:].isdigit() else 0
            if result.returncode == 0 and status == (206 if byte_range is not None else 200):
                content = temporary.read_bytes()
                header_text = headers.read_text(errors='replace')
                ranges = re.findall(r'(?im)^content-range:\s*(.*?)\s*$', header_text)
                saved = dict(url=url, range=byte_range, http_status=status,
                             content_range=ranges[-1] if ranges else None,
                             retrieved_at=datetime.now(timezone.utc).isoformat(),
                             bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
                temporary.replace(path)
                meta.write_text(json.dumps(saved, indent=2)+'\n')
                headers.unlink(missing_ok=True)
                return content, saved
            if status in (400, 401, 403, 404, 451) or (byte_range is not None and status == 200):
                break
            if attempt == 0:
                time.sleep(1)
        temporary.unlink(missing_ok=True)
        headers.unlink(missing_ok=True)
        raise SourceError(f'HTTP {status}; curl {result.returncode}: {result.stderr[:180]}')


def validate(row):
    if not isinstance(row['ts'], int) or row['ts'] % MINUTE:
        raise ValueError('Unaligned minute timestamp')
    if any(not math.isfinite(row[k]) for k in CORE[1:]):
        raise ValueError('Nonfinite OHLCV')
    if min(row[k] for k in ('open','high','low','close')) <= 0 or row['volume'] < 0:
        raise ValueError('Invalid price or volume')
    if row['low'] > min(row['open'],row['close']) or row['high'] < max(row['open'],row['close']):
        raise ValueError('Invalid OHLC bounds')
    for key in ('quote_volume','trades','taker_buy_base_volume','taker_buy_quote_volume'):
        if key in row and (not math.isfinite(row[key]) or row[key] < 0):
            raise ValueError('Invalid extra field')
    if row.get('taker_buy_base_volume',0) > row['volume']+1e-8:
        raise ValueError('Taker volume exceeds total volume')
    if row.get('taker_buy_quote_volume',0) > row.get('quote_volume',0)+1e-8:
        raise ValueError('Taker quote volume exceeds total volume')
    return row


def parse_binance(raw, microseconds=False):
    if len(raw) != 12:
        raise ValueError('Unexpected Binance row shape')
    stamp, close_stamp = int(raw[0]), int(raw[6])
    divisor = 1000 if microseconds else 1
    if stamp % divisor or close_stamp-stamp != MINUTE*divisor-1:
        raise ValueError('Unexpected Binance timestamp unit or interval')
    row = dict(zip(BINANCE_FIELDS, [stamp//divisor, *map(float,raw[1:6]),
                                  float(raw[7]), int(raw[8]), float(raw[9]), float(raw[10])]))
    return validate(row)


def parse_kucoin(raw):
    # KuCoin's order is time, open, close, high, low, base volume, turnover.
    if len(raw) != 7:
        raise ValueError('Unexpected KuCoin row shape')
    stamp, opening, close, high, low, volume, quote_volume = raw
    return validate(dict(zip(CORE+['quote_volume'],
                             [int(stamp)*1000,*map(float,(opening,high,low,close,volume,quote_volume))])))


def parse_kraken(raw):
    if len(raw) != 7:
        raise ValueError('Unexpected Kraken row shape')
    return validate(dict(zip(CORE+['trades'], [int(raw[0])*1000,*map(float,raw[1:6]),int(raw[6])])) )


def add_rows(found, rows, start, end):
    for row in rows:
        if start <= row['ts'] < end:
            if row['ts'] in found and found[row['ts']] != row:
                raise ValueError('Conflicting duplicate candle')
            found[row['ts']] = row


def gaps(stamps, start, end):
    result, left = [], None
    for stamp in range(start,end,MINUTE):
        if stamp not in stamps and left is None:
            left = stamp
        elif stamp in stamps and left is not None:
            result.append(dict(start_ts=left,end_ts=stamp,missing=(stamp-left)//MINUTE))
            left = None
    if left is not None:
        result.append(dict(start_ts=left,end_ts=end,missing=(end-left)//MINUTE))
    return result


def write_dataset(out, venue, pair, found, fields, start, end, sources, failures, **extra):
    rows = [found[t] for t in sorted(found)]
    path = out/f'{venue}_{pair}_1m.csv'
    with path.open('w',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)
    expected = (end-start)//MINUTE
    report = dict(venue=venue,pair=pair,market_type='spot',interval='1m',start_ts=start,end_ts=end,
                  expected_minutes=expected,rows=len(rows),missing_minutes=expected-len(rows),
                  coverage_pct=100*len(rows)/expected,zero_volume_rows=sum(r['volume']==0 for r in rows),
                  first_ts=rows[0]['ts'] if rows else None,last_ts=rows[-1]['ts'] if rows else None,
                  csv=path.name,csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  missing_ranges=gaps(set(found),start,end),sources=sources,failures=failures,
                  synthetic_candles_added=0,coinbase_history_modified=False,**extra)
    (out/f'{venue}_{pair}_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('missing_ranges','sources')},indent=2),flush=True)
    return report


def binance(out,start,end):
    cache = CurlCache(out/'raw/binance')
    found,sources,failures = {},[],[]
    current = datetime.fromtimestamp(start/1000,timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    cutoff = datetime.fromtimestamp(end/1000,timezone.utc)
    published_month = datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    tasks = []
    while current < cutoff and current < published_month:
        label = current.strftime('%Y-%m')
        tasks.append(('monthly',label))
        current = (current.replace(day=28)+timedelta(days=4)).replace(day=1)
    day = max(current,datetime.fromtimestamp(start//DAY*DAY/1000,timezone.utc))
    today = datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    while day < cutoff and day < today:
        tasks.append(('daily',day.strftime('%Y-%m-%d')))
        day += timedelta(days=1)
    for kind,label in tasks:
        name = f'HBARUSDT-1m-{label}.zip'
        url = f'https://data.binance.vision/data/spot/{kind}/klines/HBARUSDT/1m/{name}'
        try:
            content,meta = cache.get(url,name)
            checksum,_ = cache.get(url+'.CHECKSUM',name+'.CHECKSUM')
            expected = checksum.decode().split()[0]
            if not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(content).hexdigest()!=expected:
                raise ValueError('Binance published archive checksum mismatch')
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members=archive.namelist()
                if members != [name[:-4]+'.csv']:
                    raise ValueError('Unexpected archive member')
                with archive.open(members[0]) as handle:
                    parsed=[parse_binance(row,microseconds=label>='2025-01') for row in csv.reader(io.TextIOWrapper(handle))]
            add_rows(found,parsed,start,end)
            sources.append(dict(url=url,archive_sha256=expected,published_checksum_verified=True,rows_in_archive=len(parsed)))
            print(f'binance archive {label}: {len(found):,} requested minutes collected',flush=True)
        except (SourceError,ValueError,zipfile.BadZipFile) as exc:
            failures.append(dict(url=url,error=str(exc)))
    # Complete the unpublished final UTC day from the same venue's public API.
    tail=max(start,int(day.timestamp()*1000))
    for a in range(tail,end,999*MINUTE):
        b=min(a+999*MINUTE,end)
        url='https://data-api.binance.vision/api/v3/klines?'+urlencode(dict(symbol='HBARUSDT',interval='1m',startTime=a,endTime=b-1,limit=1000))
        try:
            content,meta=cache.get(url,f'api_{a}_{b}.json')
            raw=json.loads(content)
            if not isinstance(raw,list):raise ValueError('API returned no kline list')
            add_rows(found,[parse_binance(row) for row in raw],a,b)
            sources.append(dict(url=url,response_sha256=meta['sha256'],rows_returned=len(raw)))
        except (SourceError,ValueError) as exc:
            failures.append(dict(url=url,error=str(exc)))
    return write_dataset(out,'binance','HBAR-USDT',found,BINANCE_FIELDS,start,end,sources,failures,
                         quote_currency='USDT',taker_volume_available=True)


def kucoin(out,start,end):
    cache=CurlCache(out/'raw/kucoin')
    found,sources,failures={ },[],[]
    plan=[(a,min(a+1499*MINUTE,end)) for a in range(start,end,1499*MINUTE)]
    for index,(a,b) in enumerate(plan):
        url='https://api.kucoin.com/api/v1/market/candles?'+urlencode(dict(symbol='HBAR-USDT',type='1min',startAt=a//1000,endAt=b//1000-1))
        try:
            content,meta=cache.get(url,f'{a}_{b}.json')
            payload=json.loads(content)
            if payload.get('code')!='200000' or not isinstance(payload.get('data'),list):
                raise ValueError('KuCoin returned no successful candle list')
            parsed=[parse_kucoin(row) for row in payload['data']]
            if any(not a <= r['ts'] < b for r in parsed):
                raise ValueError('KuCoin returned a candle outside its requested window')
            add_rows(found,parsed,a,b)
            sources.append(dict(url=url,response_sha256=meta['sha256'],rows_returned=len(parsed),start_ts=a,end_ts=b))
        except (SourceError,ValueError) as exc:
            failures.append(dict(url=url,start_ts=a,end_ts=b,error=str(exc)))
            if index==0:break
        if (index+1)%20==0:print(f'kucoin {index+1}/{len(plan)} windows; {len(found):,} candles',flush=True)
        time.sleep(.35)
    return write_dataset(out,'kucoin','HBAR-USDT',found,CORE+['quote_volume'],start,end,sources,failures,
                         quote_currency='USDT',request_windows_planned=len(plan),request_windows_completed=len(sources))


class RangeZip:
    """Read supported HTTP byte ranges; refuse a server returning the whole file."""
    def __init__(self,cache,url,prefix):
        self.cache,self.url,self.prefix,self.position=cache,url,prefix,0
        data,meta=cache.get(url,prefix+'/size.bin','0-0')
        match=re.fullmatch(r'bytes 0-0/(\d+)',meta.get('content_range') or '')
        if not match or len(data)!=1:raise SourceError('Invalid HTTP range response')
        self.size=int(match.group(1))

    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if self.position<0:raise ValueError('Negative seek')
        return self.position

    def tell(self):return self.position
    def seekable(self):return True

    def read(self,size=-1):
        end=self.size if size<0 else min(self.position+size,self.size)
        if end<=self.position:return b''
        if end-self.position>50_000_000:raise SourceError('Requested member exceeds bounded download size')
        left=self.position
        data,meta=self.cache.get(self.url,f'{self.prefix}/{left}_{end}.bin',f'{left}-{end-1}')
        if meta['content_range']!=f'bytes {left}-{end-1}/{self.size}' or len(data)!=end-left:
            raise SourceError('Server did not return the exact byte range')
        self.position=end
        return data


def kraken(out,start,end):
    cache=CurlCache(out/'raw/kraken')
    datasets={'HBARUSD':{},'HBARUSDT':{}}
    sources={pair:[] for pair in datasets};failures=[]
    for quarter in ('2026Q1','2026Q2'):
        url=f'https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_{quarter}.zip'
        try:
            remote=RangeZip(cache,url,quarter)
            with zipfile.ZipFile(remote) as archive:
                names=archive.namelist()
                (out/'raw/kraken'/f'{quarter}-members.json').write_text(json.dumps(names,indent=2)+'\n')
                for pair in datasets:
                    candidates=[n for n in names if Path(n).name==pair+'_1.csv']
                    if len(candidates)!=1:
                        failures.append(dict(url=url,pair=pair,error='No unique 1-minute member for this pair'))
                        continue
                    member=candidates[0]
                    content=archive.read(member) # zipfile verifies the member CRC.
                    parsed=[parse_kraken(row) for row in csv.reader(io.StringIO(content.decode())) if row]
                    add_rows(datasets[pair],parsed,start,end)
                    sources[pair].append(dict(url=url,member=member,member_crc32=f'{archive.getinfo(member).CRC:08x}',
                                             member_sha256=hashlib.sha256(content).hexdigest(),rows_in_member=len(parsed),
                                             member_crc_verified=True,full_archive_sha256_verified=False))
                    print(f'kraken {quarter} {pair}: {len(datasets[pair]):,} requested minutes collected',flush=True)
        except (SourceError,ValueError,zipfile.BadZipFile) as exc:
            failures.append(dict(url=url,error=str(exc)))
    return [write_dataset(out,'kraken','HBAR-'+pair[4:],datasets[pair],CORE+['trades'],start,end,sources[pair],
                          [f for f in failures if 'pair' not in f or f['pair']==pair],
                          quote_currency=pair[4:],archive_available_through_exclusive='2026-07-01T00:00:00Z') for pair in datasets]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',nargs='+',choices=['binance','kucoin','kraken'],required=True)
    parser.add_argument('--start-ms',type=int,default=1774345140000)
    parser.add_argument('--end-ms',type=int,default=1789897140000)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if not 0 < args.start_ms < args.end_ms <= int(time.time()*1000)//MINUTE*MINUTE:
        parser.error('Use completed historical minutes')
    if args.start_ms%MINUTE or args.end_ms%MINUTE or args.end_ms-args.start_ms>366*DAY:
        parser.error('Use aligned minutes within one year')
    args.out.mkdir(parents=True,exist_ok=True)
    reports=[]
    for source in args.sources:
        result=globals()[source](args.out,args.start_ms,args.end_ms)
        reports.extend(result if isinstance(result,list) else [result])
    (args.out/'download-summary.json').write_text(json.dumps(reports,indent=2)+'\n')
    return 0 if any(r['rows'] for r in reports) else 2


if __name__=='__main__':raise SystemExit(main())
