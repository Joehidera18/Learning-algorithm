"""Artificial fixtures test causality and execution, never trading performance."""
import copy
import math
import tempfile
import time
import unittest
from pathlib import Path

from lab.adaptive import AdaptivePolicy, action_key, feature_vector
from lab.coinbase_broker import BrokerError, entry_plan
from lab.continuous import ContinuousLearner, DEFAULTS, resample
from lab.daily_context import DAY_MS, daily_context
from lab.engine import build_feature_cache
from lab.execution import simulate
from lab.strategies import profit_candidates, simple_signal
from lab.trade_quality import signal_cost_check
from tests.test_adaptive import F
from tests.test_coinbase import PRODUCT, SNAPSHOT
from tests.test_execution import candles

HOUR = 3600000
SWING = [p for p in profit_candidates() if p.get("atr_timeframe") == "daily"]


def hourly(days=55):
    rows = candles(days*24, step=HOUR)
    for i,r in enumerate(rows):
        value = 100+i*.01+math.sin(i/6)*.3
        r.update(open=value-.02, close=value, high=value+.3, low=value-.3)
    return rows


def swing_features(**changes):
    return dict(F, daily={"ready":True,"atr":10.,"momentum7":.05,
        "ma_distance_atr":1.,"atr_pct":.1,"trend_up":True,"trend_down":False},
        rsi_previous=35., support_reclaim=True, prior_compression=True,
        **changes)


class DailyContextTests(unittest.TestCase):
    def test_current_day_is_hidden_and_future_candles_cannot_repaint(self):
        rows = hourly(30)
        cache = daily_context(rows, HOUR)
        first = 21*24-1
        self.assertTrue(all(not x for x in cache[:first]))
        self.assertEqual(cache[first]["available_ts"], rows[first]["ts"]+HOUR)
        for i in range(first+1,first+24):
            self.assertEqual(cache[i], cache[first])
        cut = 26*24+7
        self.assertEqual(daily_context(rows[:cut], HOUR), cache[:cut])
        changed = copy.deepcopy(rows)
        for r in changed[cut:]:
            r.update(high=r["high"]*100, close=r["close"]*100)
        self.assertEqual(daily_context(changed,HOUR)[:cut],cache[:cut])

    def test_a_missing_hour_resets_daily_warmup_without_filling_the_gap(self):
        rows = hourly()
        missing_index = 27*24+3
        missing = rows.pop(missing_index)["ts"]
        cache = daily_context(rows,HOUR)
        self.assertFalse(cache[missing_index])
        ready = next(i for i in range(missing_index,len(rows)) if cache[i])
        next_midnight = (missing//DAY_MS+1)*DAY_MS
        self.assertEqual(cache[ready]["available_ts"],next_midnight+21*DAY_MS)
        self.assertEqual(len(cache),len(rows))

    def test_replay_and_paper_daily_context_agree_despite_short_decision_cache(self):
        rows = hourly(43)
        asof = rows[-1]["ts"]+HOUR
        four_hour = resample(rows,4*HOUR,asof_ms=asof)
        replay = build_feature_cache(rows,"1h",simple_only=True)["features"][-1]
        self.assertEqual(replay["daily"],daily_context(four_hour,4*HOUR)[-1])
        with tempfile.TemporaryDirectory() as directory:
            agent = ContinuousLearner(Path(directory)/"test.db",Path(directory)/"data")
            market = agent._empty_market()
            market["bars"]["1h"] = rows[-300:]
            future_rows = hourly(46)
            market["bars"]["4h"] = resample(future_rows,4*HOUR,asof_ms=future_rows[-1]["ts"]+HOUR)
            agent.market["BTC-USD"] = market
            live = agent._latest_feature("BTC-USD","1h")
            self.assertEqual(live["daily"],replay["daily"])
            self.assertLessEqual(live["daily"]["available_ts"],asof)
            agent.stop()


class SwingStrategyTests(unittest.TestCase):
    def test_new_rules_require_history_and_each_has_a_distinct_trigger(self):
        for p in SWING:
            self.assertEqual(simple_signal(F,p)[1],"daily_history_not_ready")
            f = swing_features(lower_wick=.4, range_expansion=2.)
            self.assertIsNotNone(simple_signal(f,p)[0])
            down = dict(f,daily=dict(f["daily"],trend_down=True))
            self.assertEqual(simple_signal(down,p)[1],"daily_downtrend")
            family = p["family"]
            blocked = (dict(f,breakout=False) if family=="daily_trend_momentum_simple" else
                       dict(f,prior_compression=False) if family=="volatility_expansion_simple" else
                       dict(f,rsi_previous=45.))
            self.assertIsNone(simple_signal(blocked,p)[0])
        self.assertEqual(len({action_key(p) for p in profit_candidates()}),22)

    def test_daily_atr_is_used_after_costs_without_relaxing_the_gap_guard(self):
        p = SWING[0]
        f = swing_features()
        quality, error = signal_cost_check(f,p,.004,.001)
        self.assertIsNone(error)
        self.assertGreater(quality["net_rr"],1.5)
        self.assertIsNotNone(signal_cost_check(F,p,.004,.001)[1])
        rows = candles(245)
        fs = [f if i==240 else None for i in range(len(rows))]
        _,trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,p)
        trade = trades[0]
        self.assertAlmostEqual(trade["entry"]-trade["stop"],10*p["stop_atr"])
        self.assertLessEqual(trade["risk_dollars"],500*.0075)
        self.assertLess(trade["pnl"],0)  # Flat prices still pay both sides' costs.
        self.assertEqual(feature_vector(trade["features"]),feature_vector(f))
        rows[241].update(open=102.,high=103.,low=101.,close=102.)
        metrics,trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,p)
        self.assertFalse(trades)
        self.assertEqual(metrics["signal_funnel"]["entry_rejections"]["entry_gap_too_large"],1)

    def test_broker_uses_the_same_stop_and_tighter_decision_gap(self):
        p = SWING[0]
        signal = {"product_id":"BTC-USD","atr":10.,"gap_atr":2.,"close":100.,"params":p}
        quote = {"bid":"99.99","ask":"100.01","ts":int(time.time())}
        plan = entry_plan(signal,PRODUCT,quote,SNAPSHOT,500,DEFAULTS,"fixture")
        self.assertAlmostEqual(float(plan["max_entry_price"])-float(plan["stop"]),7.5,places=2)
        with self.assertRaisesRegex(BrokerError,"moved too far"):
            entry_plan(signal,PRODUCT,{"bid":"101.99","ask":"102.01"},SNAPSHOT,500,DEFAULTS,"fixture")

    def test_paper_stop_distance_and_risk_remain_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = ContinuousLearner(Path(directory)/"test.db",Path(directory)/"data")
            agent.configure({"validated_only":False})
            agent.runtime["running"] = True
            market = agent._empty_market()
            market["ticker"] = {"price":100.,"best_bid":99.99,"best_ask":100.01,
                                "ts":int(time.time()*1000)}
            agent.market["BTC-USD"] = market
            choice = {"params":SWING[0],"adjusted_score":70.,"raw_score":70.,"learned":{}}
            position = agent._open_position("BTC-USD",100.,swing_features(),{"key":"fixture"},choice,"experiment")
            self.assertIsNotNone(position)
            self.assertAlmostEqual(position["entry"]-position["stop"],7.5)
            self.assertLessEqual(position["risk_usd"],500*DEFAULTS["risk_per_trade"])
            agent.stop()

    def test_legacy_comparison_cannot_use_a_new_strategy(self):
        policy = AdaptivePolicy()
        f = swing_features()
        for i in range(80):
            policy.observe(SWING[0],feature_vector(f),1.,i)
        self.assertIsNotNone(policy.choose(f))
        baseline = AdaptivePolicy(policy.export(),legacy_candidates_only=True)
        self.assertIsNone(baseline.choose(f))
        self.assertEqual(baseline.last_diagnostics["candidates_checked"],16)
