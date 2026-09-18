"""Inventory uploaded research without pooling duplicate reports or price rows.

Records overlap revisions explicitly. It does not merge snapshots or train a
model. Run with --input-dir /path/to/uploads --out /path/to/inventory.json.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.evaluation import dataset_digest
from lab.data import INTERVAL_MS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    reports, bundles, seen_files, timelines, revisions = [], [], {}, {}, []
    for path in sorted(args.input_dir.glob('learning-results*.json')):
        data=json.loads(path.read_text()); markets=data.get('results',[]); digest=sha(path)
        reports.append({'file':path.name,'sha256':digest,'duplicate_of':seen_files.get(digest),
            'markets_present':len(markets),'engine_versions':sorted({r['engine_version'] for r in markets}),
            'selected_trades':sum(r['holdout']['trades'] for r in markets),
            'sum_of_available_separate_account_net_pnl':sum(r['holdout'].get('net_pnl') or 0 for r in markets),
            'incomplete_accounts':sum(r['holdout'].get('complete') is False for r in markets),
            'reviewed_endpoints':{r['symbol']:r['replay']['test_end_ts'] for r in markets}})
        seen_files.setdefault(digest,path.name)
    ordered=[]
    for path in args.input_dir.glob('*learning-data*.zip'):
        with zipfile.ZipFile(path) as z:
            report=json.loads(z.read('learning-result.json'))
        ordered.append((report['replay']['test_end_ts'],path.name,path,report))
    seen_data={}
    for _,_,path,report in sorted(ordered):
        item={'file':path.name,'sha256':sha(path),'symbol':report['symbol'],'candles':{}}
        with zipfile.ZipFile(path) as z:
            for name,step in (('candles.csv',INTERVAL_MS[report['interval']]),('daily-candles.csv',86400000)):
                if name not in z.namelist(): continue
                rows=[{k:int(v) if k in ('ts','trades') else float(v) for k,v in r.items()}
                      for r in csv.DictReader(io.StringIO(z.read(name).decode()))]
                if any(b['ts']<=a['ts'] or (b['ts']-a['ts'])%step for a,b in zip(rows,rows[1:])):
                    raise ValueError(f'Unordered or off-grid rows in {path.name}: {name}')
                digest=dataset_digest(rows)
                declared=(report.get('data_sha256') if name=='candles.csv'
                          else report.get('daily_data',{}).get('data_sha256'))
                if declared is not None and declared!=digest:
                    raise ValueError(f'Price identity mismatch in {path.name}: {name}')
                timeline=timelines.setdefault((report['symbol'],name),{})
                fresh=changed=0
                for row in rows:
                    previous=timeline.get(row['ts'])
                    if previous is None: fresh+=1
                    elif previous[1]!=row:
                        changed+=1
                        revisions.append({'symbol':report['symbol'],'file':name,'ts':row['ts'],
                            'earlier_snapshot':previous[0],'later_snapshot':path.name,
                            'earlier_row':previous[1],'later_row':row})
                    timeline[row['ts']]=(path.name,row)
                identity=(report['symbol'],name,digest)
                item['candles'][name]={'rows':len(rows),'canonical_sha256':digest,
                    'declared_hash_verified':declared is not None,'same_prices_as':seen_data.get(identity),
                    'start_ts':rows[0]['ts'],'end_ts':rows[-1]['ts'],
                    'missing_intervals':sum((b['ts']-a['ts'])//step-1 for a,b in zip(rows,rows[1:])),
                    'additional_unique_timestamps':fresh,'revised_overlapping_rows':changed}
                seen_data.setdefault(identity,path.name)
        bundles.append(item)
    record={'reports':reports,'bundles':bundles,'overlap_revisions':revisions,
        'unique_timestamps':{symbol+'/'+name:len(rows) for (symbol,name),rows in timelines.items()},
        'scope':'Inventory only. Duplicate uploads and overlapping snapshots are not extra independent learning. '
                'Reports are separate historical accounts, not one portfolio. Incomplete returns are identified. '
                'No prices are synthesized, merged or downloaded by this script.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'reports':len(reports),'bundles':len(bundles),'overlap_revisions':len(revisions)}))


if __name__=='__main__': main()
