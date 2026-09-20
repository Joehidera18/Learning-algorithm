"""Download a separate, documented research bundle without starting a trader."""
import argparse
import json
import sys
from datetime import datetime,timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.massive_data import MassiveHistory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol',required=True)
    parser.add_argument('--interval',choices=('15m','1h','1d'),default='1h')
    parser.add_argument('--start',required=True,help='Inclusive UTC YYYY-MM-DD')
    parser.add_argument('--end',required=True,help='Exclusive UTC YYYY-MM-DD; today or earlier')
    parser.add_argument('--out',required=True,help='New ZIP filename outside the Coinbase history cache')
    args=parser.parse_args()
    def stamp(value):return int(datetime.strptime(value,'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()*1000)
    target=Path(args.out)
    if target.suffix.lower()!='.zip':parser.error('--out must be a ZIP file')
    if target.exists():parser.error('Output already exists; choose a new filename')
    try:
        content,manifest=MassiveHistory().download(args.symbol,args.interval,stamp(args.start),stamp(args.end))
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:handle.write(content)
    except (ValueError,OSError) as exc:
        parser.exit(1,str(exc)+'\n')
    print(json.dumps({'file':str(target),'rows':manifest['rows'],'coverage_pct':manifest['coverage_pct'],
        'provider':manifest['provider'],'scope':manifest['scope']},indent=2))


if __name__=='__main__':main()
