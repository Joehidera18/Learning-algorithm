"""Replay development entry and exit events to retain honest entry forecasts.

Entry predictions never use that trade's label, other open trades' labels, or
the model eventually fitted at closure. Results are learned once, after exit.
"""
import math

from .prediction_audit import PredictionAudit, entry_snapshot


class ChronologicalTrainer:
    def __init__(self, policy, candidates, examples, cancelled=None):
        self.policy, self.candidates, self.examples = policy, candidates, examples
        self.cancelled = cancelled or (lambda:False)
        self.events, self.pending = [], {}
        self.cursor, self.last_clock = 0, -1
        self.predictions = PredictionAudit()
        for number, example in enumerate(examples):
            available, index, vector, reward, outcome, entry_ts = example
            if (not math.isfinite(entry_ts) or not math.isfinite(available)
                    or not 0 <= entry_ts < available):
                raise ValueError("Development forecast must precede its resolved outcome")
            # All known closures at a clock precede decisions at that clock.
            self.events.extend(((entry_ts,1,index,number),(available,0,index,number)))
        self.events.sort()

    def advance(self, cut_ts):
        if cut_ts < self.last_clock:
            raise ValueError("Development learning clock cannot move backwards")
        self.last_clock = cut_ts
        while self.cursor < len(self.events) and self.events[self.cursor][0] <= cut_ts:
            if self.cursor % 500 == 0 and self.cancelled():
                raise InterruptedError("Learning cancelled")
            stamp, entry, index, number = self.events[self.cursor]
            available, _, vector, reward, outcome, entry_ts = self.examples[number]
            params = self.candidates[index]
            if entry:
                self.pending[number] = entry_snapshot(self.policy.forecast(params,vector),stamp)
            else:
                forecast = self.pending.pop(number)
                detail = dict(outcome,entry_forecast=forecast)
                self.policy.observe(params,vector,reward,available,outcome=detail)
                self.predictions.observe({"reason":outcome.get("reason","UNKNOWN"),
                    "strategy_family":params["family"],"entry_forecast":forecast},reward)
            self.cursor += 1
        return self.policy.export()
