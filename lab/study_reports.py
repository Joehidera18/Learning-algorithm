"""Small dashboard summaries; complete research stays in the saved report."""
import copy


def compact_report(report):
    fields = ('symbol','interval','validated','research_only','error','fingerprint',
        'engine_version','policy_version','learning_report_version','created_at',
        'history_request','historical_examples','holdout_learning_updates','data_hours',
        'rejection_reasons','review_scope','next_review_at','data_quality','data_selection')
    result = {key:report[key] for key in fields if key in report}
    # Nested feedback, candidate ledgers and case studies can be much larger
    # than all the account metrics combined. Fetch those only when requested.
    for key in ('holdout','holdout_stressed'):
        result[key] = {k:v for k,v in (report.get(key) or {}).items()
            if not isinstance(v,(dict,list))}
    result['daily_goal'] = {'mean_net_per_day':(report.get('daily_goal') or {}).get('mean_net_per_day')}
    result['learning_evidence'] = {k:v for k,v in report.get('learning_evidence', {}).items()
        if k in ('eligible_examples','cost_blocked_examples','minimum_eligible_examples')}
    result['bitcoin_data'] = {k:v for k,v in report.get('bitcoin_data', {}).items()
        if k in ('symbol','source','holdout_ready_candles','holdout_candles')}
    result['evaluation'] = {key:report['evaluation'][key]
        for key in ('reuses_reviewed_history','reviewed_through_ts','basis')
        if key in (report.get('evaluation') or {})}
    result['report_summary'] = True
    result['details_available'] = not bool(report.get('error'))
    return copy.deepcopy(result)
