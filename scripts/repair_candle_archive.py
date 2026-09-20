"""Repair known archive gaps while preserving every previously verified candle."""
import argparse,csv,gzip,hashlib,io,json,sys,zipfile
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_coin_candle_library import api,aggregate_stream,FRAMES,FIELDS,MINUTE
from scripts.download_hbar_alternatives import CurlCache,SourceError


def decode(line):
    values=line.strip().split(',')
    return {k:int(v) if k in ('ts','trades') else float(v) for k,v in zip(FIELDS,values)}


def affected_bars(old_minutes,recovered,minutes,start,end):
    step=minutes*MINUTE
    buckets={t//step*step for t in recovered}
    selected={r['ts']:r for r in old_minutes if r['ts']//step*step in buckets}
    for t,row in recovered.items():
        if t in selected and selected[t]!=row:raise ValueError('Conflicting recovered observation')
        selected[t]=row
    return {r['ts']:r for r in aggregate_stream((selected[t] for t in sorted(selected)),minutes,start,end)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    cache=CurlCache(args.out/'repair-requests');recovered={};sources=[];errors=[]
    with zipfile.ZipFile(args.archive) as z:
        manifest=json.loads(z.read('manifest.json'))
        start,end=manifest['first_available_ts'],manifest['end_ts_exclusive']
        for gap in manifest['remaining_minute_gaps']:
            for a in range(gap['start_ts'],gap['end_ts'],999*MINUTE):
                b=min(gap['end_ts'],a+999*MINUTE)
                try:
                    rows,meta=api(cache,manifest['pair'],a,b,f'retry-{a}-{b}')
                    recovered.update({r['ts']:r for r in rows});sources.append(meta)
                except (SourceError,ValueError) as exc:errors.append(dict(start_ts=a,end_ts=b,error=str(exc)))
        # Read only the original minute rows needed by changed larger buckets.
        buckets={t//(240*MINUTE) for t in recovered};neighbors=[]
        minute=next(f for f in manifest['timeframes'] if f['interval']=='1m')
        raw=z.read(minute['file']);assert hashlib.sha256(raw).hexdigest()==minute['sha256']
        with gzip.open(io.BytesIO(raw),'rt') as handle:
            next(handle)
            for line in handle:
                if int(line.split(',',1)[0])//(240*MINUTE) in buckets:neighbors.append(decode(line))
        reports=[]
        for old in manifest['timeframes']:
            interval=old['interval'];minutes=FRAMES[interval];step=minutes*MINUTE
            additions=affected_bars(neighbors,recovered,minutes,start,end)
            keys=iter(sorted(additions));pending=next(keys,None)
            path=args.out/old['file'];raw=z.read(old['file']);assert hashlib.sha256(raw).hexdigest()==old['sha256']
            count=zero=0;cursor=old['start_ts'];gaps=[]
            with gzip.open(io.BytesIO(raw),'rt') as source,gzip.open(path,'wt',newline='',compresslevel=5) as dest:
                header=next(source);dest.write(header)
                def emit(line):
                    nonlocal count,zero,cursor
                    fields=line.rstrip().split(',');stamp=int(fields[0])
                    if stamp<cursor:raise ValueError('Duplicate or unordered output')
                    if stamp>cursor:gaps.append(dict(start_ts=cursor,end_ts=stamp,candles=(stamp-cursor)//step))
                    cursor=stamp+step;count+=1;zero+=float(fields[5])==0;dest.write(line)
                def new_line(stamp):return ','.join(str(additions[stamp][k]) for k in FIELDS)+'\n'
                for line in source:
                    stamp=int(line.split(',',1)[0])
                    while pending is not None and pending<stamp:
                        emit(new_line(pending));pending=next(keys,None)
                    if pending==stamp:
                        # Recomputed complete bars must agree; original representation is retained.
                        if decode(line)!=additions[stamp]:raise ValueError('Existing candle would change')
                        pending=next(keys,None)
                    emit(line)
                while pending is not None:
                    emit(new_line(pending));pending=next(keys,None)
            if cursor<old['end_ts_exclusive']:gaps.append(dict(start_ts=cursor,end_ts=old['end_ts_exclusive'],candles=(old['end_ts_exclusive']-cursor)//step))
            report=dict(old,rows=count,zero_volume_rows=zero,missing_candles=old['expected_candles']-count,
                        coverage_pct=100*count/old['expected_candles'],missing_ranges=gaps,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            assert count>=old['rows'];reports.append(report)
        manifest['supplemental_repair']={'input_archive_sha256':hashlib.sha256(args.archive.read_bytes()).hexdigest(),
            'recovered_minutes':reports[0]['rows']-minute['rows'],'requests':len(sources)+len(errors),'errors':errors,
            'rule':'Malformed observations rejected individually; all original valid candles preserved.'}
        manifest['sources']+=sources;manifest['timeframes']=reports
        manifest['missing_minutes_after_repair']=reports[0]['missing_candles']
        manifest['remaining_minute_gaps']=[dict(start_ts=g['start_ts'],end_ts=g['end_ts'],minutes=g['candles']) for g in reports[0]['missing_ranges']]
        manifest['generated_at']=datetime.now(timezone.utc).isoformat()
        (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (args.out/'README.txt').write_bytes(z.read('README.txt'))
    final=args.out.parent/(manifest['coin']+'-complete-candle-data.zip')
    with zipfile.ZipFile(final,'w',zipfile.ZIP_STORED) as z:
        for name in ['README.txt','manifest.json']+[r['file'] for r in reports]:z.write(args.out/name,name)
    print(json.dumps({'coin':manifest['coin'],'recovered':manifest['supplemental_repair']['recovered_minutes'],
                      'remaining_missing':manifest['missing_minutes_after_repair'],'output':str(final)}),flush=True)

if __name__=='__main__':main()
