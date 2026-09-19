"""Reproduce a known reporting-boundary defect without changing qualification.

Run separately against pinned V11.9 and revised source with identical --bundle
and --boundary-report inputs. The boundary report supplies a HISTORICAL cut for
a retrospective diagnostic, never a new confirmation or trading qualification.
The normal learner reviews the whole bundle through its end in both runs.
"""
import argparse
import csv
import hashlib
import io
import json
from bisect import bisect_left
from pathlib import Path
import sys
import time
import zipfile


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def comparable_model(model):
    # The version bump must invalidate production models; comparison of the
    # mathematical state excludes only that identifier, never weights/counts.
    return {k: v for k, v in model.items() if k != 'version'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--boundary-report', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    from lab import learning_research
    from lab.adaptive import AdaptivePolicy, action_key
    from lab.continuous import DEFAULTS
    from lab.data import INTERVAL_MS
    from lab.evaluation import dataset_digest
    from lab.execution import simulate
    from lab.shadow_learning import HistoricalFeedback

    with zipfile.ZipFile(args.bundle) as archive:
        def read(name):
            return [{k: int(v) if k in ('ts', 'trades') else float(v) for k, v in row.items()}
                    for row in csv.DictReader(io.StringIO(archive.read(name).decode()))]
        rows, daily = read('candles.csv'), read('daily-candles.csv')
        embedded = json.loads(archive.read('learning-result.json'))
    assert dataset_digest(rows) == embedded['data_sha256']
    assert dataset_digest(daily) == embedded['daily_data']['data_sha256']
    settings = {**DEFAULTS, **embedded['cost_signature']}
    step = INTERVAL_MS[embedded['interval']]
    old_report = json.loads(args.boundary_report.read_text())
    boundary = next(r['replay']['test_end_ts'] for r in old_report['results']
                    if r['symbol'] == embedded['symbol'])
    split = bisect_left([r['ts'] for r in rows], boundary)
    start, end = int(len(rows)*.8), len(rows)
    assert start < split < end-1 and rows[split]['ts'] == boundary
    captured = {}

    class CaptureFeedback(HistoricalFeedback):
        def __init__(self, data, features, first, last, config, policy, interval, cancelled=None):
            if (first == start and last == end and policy.exit_policy == 'fixed'
                    and policy.recent_return_veto and policy.regime_adaptation and policy.cost_filter
                    and policy.failure_adaptation and not policy.legacy_candidates_only):
                captured.setdefault(policy.fee_rate, {'initial': policy.export(), 'policy': policy,
                    'features': features})
            super().__init__(data, features, first, last, config, policy, interval, cancelled)

    # Read-only capture of the primary seeds and completed reference streams.
    learning_research.HistoricalFeedback = CaptureFeedback
    source = hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        source.update(path.name.encode()+b'\0'+path.read_bytes())
    started = time.monotonic()
    result = learning_research.learn_history(rows, embedded['symbol'], settings,
        daily_rows=daily, reviewed_through_ts=rows[-1]['ts']+step,
        progress=lambda **state: print(state.get('message', ''), flush=True))
    assert result['evaluation']['confirmation'] is None and not result['validated']
    fee, slip = settings['fee_rate'], settings['slippage_rate']+.0005
    references = {cost: value['policy'].export() for cost, value in captured.items()}
    features, initial = captured[fee]['features'], captured[fee]['initial']
    continuous = hasattr(HistoricalFeedback, 'begin_reporting')

    def policy(seed, stress=1):
        return AdaptivePolicy(seed, settings['max_notional_fraction'],
            fee_rate=fee*stress, slippage_rate=slip*stress)

    old_prefix = None
    if not continuous:
        old_prefix = policy(initial)
        prefix = HistoricalFeedback(rows, features, start, split, settings, old_prefix, step)
        prefix.advance(boundary)
        old_prefix = old_prefix.export()

    windows = {}
    for stress in (1, 1.5):
        learner = policy(initial if continuous else old_prefix, stress)
        observed = {}
        original = learner.observe
        def observe(params, vector, reward, available_ts, outcome=None):
            if available_ts > boundary:
                forecast = outcome['entry_forecast']
                identity = action_key(params)+'|'+str(forecast['signal_close_ts'])
                assert identity not in observed
                observed[identity] = {'entry_ts': forecast['signal_close_ts'],
                    'available_ts': available_ts, 'actual_r': reward,
                    'predicted_r': forecast['estimated_net_r'], 'ready': forecast['ready'],
                    'practice_lane': outcome['practice_lane']}
            return original(params, vector, reward, available_ts, outcome=outcome)
        learner.observe = observe
        feedback = HistoricalFeedback(rows, features, start if continuous else split, end,
            settings, learner, step)
        if continuous:
            feedback.begin_reporting(boundary)
        at_start = learner.export()
        assert at_start['last_label_ts'] <= boundary
        metrics, trades = simulate(rows, features, split, end, 500, settings['risk_per_trade'],
            fee*stress, slip*stress, {'family': 'adaptive_policy', 'direction': 'LONG'},
            policy=learner, feedback=feedback, daily_loss_limit=settings['daily_loss_limit'],
            bar_interval_ms=step)
        control, _ = simulate(rows, features, split, end, 500, settings['risk_per_trade'],
            fee*stress, slip*stress, {'family': 'adaptive_policy', 'direction': 'LONG'},
            policy=policy(at_start, stress), daily_loss_limit=settings['daily_loss_limit'],
            bar_interval_ms=step)
        carried = [v for v in observed.values() if v['entry_ts'] < boundary]
        windows[str(stress)] = {'metrics': metrics, 'feedback': feedback.summary(),
            'account_feedback_control': control, 'selected_trades': len(trades),
            'entry_forecasts': observed, 'carried_in_examples': len(carried),
            'carried_in_eligible': sum(v['practice_lane'] == 'eligible' for v in carried),
            'carried_in_sum_net_r': sum(v['actual_r'] for v in carried),
            'starting_model_sha256': digest(comparable_model(at_start)),
            'ending_model_sha256': digest(comparable_model(learner.export())),
            'uninterrupted_model_sha256': digest(comparable_model(references[fee*stress])),
            'ending_model_matches_uninterrupted': learner.export() == references[fee*stress]}
        if continuous:
            assert windows[str(stress)]['ending_model_matches_uninterrupted']
        print(json.dumps({'retrospective_cost_multiplier': stress,
            'feedback': len(observed), 'carried_in': len(carried),
            'matches_uninterrupted': windows[str(stress)]['ending_model_matches_uninterrupted']}), flush=True)

    record = {'symbol': embedded['symbol'], 'engine_version': result['engine_version'],
        'source_code_sha256': source.hexdigest(),
        'bundle_sha256': hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'boundary_report_sha256': hashlib.sha256(args.boundary_report.read_bytes()).hexdigest(),
        'diagnostic_boundary': boundary, 'continuous_confirmation': continuous,
        'historical_windows': windows, 'result': result,
        'continuous_model_observations': references[fee]['observations'],
        'uploaded_model_observations': embedded['model']['observations'],
        'uploaded_model_matches_continuous': comparable_model(embedded['model']) == comparable_model(references[fee]),
        'runtime_seconds': time.monotonic()-started,
        'scope': 'Fixed retrospective diagnosis on already reviewed prices, never fresh qualification. '
            'Normal report evaluation still marks the entire bundle as reviewed. No strategy, costs, '
            'risk limits or qualification thresholds are selected from these results. '
            'The diagnostic windows reproduce the source version\'s confirmation handoff; '
            'their feedback and dollar accounts are separate quantities.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'symbol': embedded['symbol'], 'runtime_seconds': record['runtime_seconds'],
        'ordinary_net': result['holdout']['net_pnl'], 'stressed_net': result['holdout_stressed']['net_pnl']}), flush=True)


if __name__ == '__main__':
    main()
