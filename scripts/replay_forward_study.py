"""Independently reproduce a downloaded study under its exact registered code."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.forward_study import evaluate,source_digest
from lab.event_context import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file')
    args=parser.parse_args()
    record=json.loads(Path(args.file).read_text())
    p=record['protocol'];original=dict(p);stamp=original.pop('protocol_sha256')
    if digest(original)!=stamp or digest(p['model'])!=p['model_sha256']:
        parser.error('Protocol or seed differs from its registered hash')
    if p['source_sha256']!=source_digest():parser.error('Check out the exact code recorded for this study before replaying')
    if not record['inputs'] or not record['result']:parser.error('No evaluated observations are saved yet')
    if digest(record['inputs'])!=record['result']['inputs_sha256']:parser.error('Saved inputs do not match their hash')
    result=evaluate(p,record['inputs'])
    if result!=record['result']:parser.error('Replay differs from the saved result')
    print(json.dumps({'study':record['id'],'matches_saved_result':True,
        'status':record['status'],'equity_pnl_difference':result['equity_pnl_difference'],
        'scope':result['scope']},indent=2))


if __name__=='__main__':main()
