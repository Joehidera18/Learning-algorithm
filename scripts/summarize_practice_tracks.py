"""Summarize fixed before/after records without selecting a winning policy."""
import argparse
import json
from pathlib import Path
from compare_practice_tracks import compare_forecasts

def metrics(m):
 return {k:v for k,v in m.items() if k not in ('feedback','signal_funnel','prediction_audit')}

def summary(r):
 values={k:r[k] for k in ('engine_version','policy_version','learning_report_version','data_sha256',
   'daily_data','cost_signature','historical_examples','candidate_count','training_label_end_ts','holdout_start_ts',
   'pre_holdout_model_sha256','validated','rejection_reasons','holdout_trades')}
 values['development_prediction_audit']={k:v for k,v in r['development_prediction_audit'].items() if k not in ('calibration','by_family','by_forecast_band','scope')}
 values['prediction_audit']={name:{k:v for k,v in a.items() if k not in ('calibration','by_family','by_forecast_band','scope')} for name,a in r['prediction_audit'].items() if isinstance(a,dict)}
 for k in ('holdout','holdout_stressed','frozen_holdout'):values[k]=metrics(r[k])
 values['folds']=[{'fold':f['fold'],'test_start_ts':f['test_start_ts'],'test_end_ts':f['test_end_ts'],
   'training_labels':f['training_labels'],'metrics':metrics(f['metrics'])} for f in r['folds']]
 values['training_diagnostics']={'totals':r['training_diagnostics']['totals'],'candidates':[
   {k:({lane:{f:n for f,n in group.items() if f!='signal_funnel'} for lane,group in v.items()} if k=='by_practice_lane' else v)
    for k,v in c.items() if k!='signal_funnel'} for c in r['training_diagnostics']['candidates']]}
 values['shadow_feedback']={k:v for k,v in r['holdout_shadow_feedback'].items() if k!='prediction_audit'}
 values['model_observations']=r['model']['observations']
 values['reviewed_through_ts']=r['evaluation']['reviewed_through_ts']
 values['confirmation']=r['evaluation']['confirmation']
 for k in ('account_feedback_comparison','outcome_memory_comparison','upgrade_comparison','strategy_expansion_comparison'):
  values[k]={key:(metrics(v) if isinstance(v,dict) else v) for key,v in r[k].items()}
 for k in ('exit_policy_comparison','selection_policy_comparison'):
  values[k]={key:v for key,v in r[k].items() if key in ('rule','holdout','holdout_stressed','folds','rejection_reasons',
   'net_pnl_difference','stress_net_pnl_difference','qualified','eligible_for_trading','historical_examples','profitable_folds')}
  values[k]['folds']=[{'fold':f['fold'],'training_labels':f['training_labels'],'test_start_ts':f['test_start_ts'],'test_end_ts':f['test_end_ts'],'metrics':metrics(f['metrics'])} for f in r[k]['folds']]
 return values

def counts(forecasts):
 return {lane:{'examples':len(v:=[x for x in forecasts.values() if x['cost_lane']==lane]),
   'sum_net_r':sum(x['actual_r'] for x in v),'net_losses':sum(x['actual_r']<0 for x in v)} for lane in ('eligible','cost_blocked')}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--markets",nargs="+",default=["dot","xrp","avax"])
    args=parser.parse_args()
    records=[]
    for symbol in args.markets:
     a=json.loads((args.study_dir/f'{symbol}-baseline-verified.json').read_text())
     b=json.loads((args.study_dir/f'{symbol}-revised-verified.json').read_text())
     after_counts=counts(b['primary_practice_forecasts'])
     for lane,c in after_counts.items():
      assert c['examples']==b['result']['holdout_shadow_feedback']['by_practice_lane'][lane]['resolved_examples']
     comparison={**b['comparison'],**compare_forecasts(a['primary_practice_forecasts'],b['primary_practice_forecasts'])}
     records.append({'symbol':b['result']['symbol'],'bundle_sha256':b['bundle_sha256'],
      'reviewed_report_sha256':b['reviewed_report_sha256'],
      'before_source_code_sha256':a['source_code_sha256'],'after_source_code_sha256':b['source_code_sha256'],
      'before_runtime_seconds':a['runtime_seconds'],'after_runtime_seconds':b['runtime_seconds'],
      'before_entry_verification':a['entry_outcome_verification'],'after_entry_verification':b['entry_outcome_verification'],
      'before_practice_cost_groups':counts(a['primary_practice_forecasts']),'after_practice_cost_groups':after_counts,
      'comparison':comparison,'before':summary(a['result']),'after':summary(b['result'])})
    output={'scope':'Fixed V11.8 versus V11.9 replays of three supplied candle bundles with identical costs and reviewed boundaries. '
     'Each market is a separate $500 account. More practice examples are not independent bets or account profits. '
     'Forecast errors compare common candidate entries with identical exit clocks and rewards. All markets remain unqualified.',
     'selection_uses_comparison':False,'qualification_uses_comparison':False,'markets':records}
    path=args.out
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(path,path.stat().st_size)
    for r in records:
     print(r['symbol'], r['comparison']['common_entry_forecast_errors']['eligible'])


if __name__=="__main__": main()
