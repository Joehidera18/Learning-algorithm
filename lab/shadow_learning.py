"""Accelerated historical feedback from independent, fully costed simulations.

No generated prices, future labels, exchange orders or account P&L are used.
Every candidate uses the same execution engine as the selected policy. Candidate
outcomes overlap and must never be counted as account trades or independent bets.
"""
from .execution import simulation_steps
from .outcome_memory import trade_feedback


class HistoricalFeedback:
    def __init__(self, rows, features, start, end, settings, policy, step, cancelled=None):
        self.policy, self.pending, self.runs = policy, [], []
        self.last_clock = -1
        self.count, self.by_family, self.gap_censored = 0, {}, 0
        for index, params in enumerate(policy.candidates):
            if policy.legacy_candidates_only and params.get("atr_timeframe") == "daily":
                continue
            def resolved(trade, reward, available, index=index):
                self.pending.append((available, index, trade["training_vector"], reward, trade_feedback(trade)))
            run = simulation_steps(rows, features, start, end, 500,
                settings["risk_per_trade"], policy.fee_rate, policy.slippage_rate, params,
                cancelled=cancelled, training_examples=True, bar_interval_ms=step,
                on_resolved=resolved)
            try:
                self.runs.append([next(run), run])
            except StopIteration:
                pass

    def advance(self, closed_ms):
        if closed_ms < self.last_clock:
            raise ValueError("Historical feedback clock cannot move backwards")
        self.last_clock = closed_ms
        alive = []
        for item in self.runs:
            clock, run = item
            try:
                while clock <= closed_ms:
                    clock = next(run)
                alive.append([clock, run])
            except StopIteration as finished:
                self.gap_censored += finished.value[0]["signal_funnel"].get("gap_censored_examples", 0)
        self.runs = alive
        for available, index, vector, reward, outcome in sorted(self.pending, key=lambda x:(x[0], x[1])):
            if available > closed_ms:
                raise ValueError("Future shadow outcome reached the learner")
            params = self.policy.candidates[index]
            self.policy.observe(params, vector, reward, available, outcome=outcome)
            self.count += 1
            family = self.by_family.setdefault(params["family"], {"examples":0, "sum_net_r":0.})
            family["examples"] += 1
            family["sum_net_r"] += reward
        self.pending.clear()

    def summary(self):
        return {"mode":"historical_shadow", "resolved_examples":self.count,
                "by_family":self.by_family, "last_clock_ms":self.last_clock,
                "gap_censored_examples":self.gap_censored,
                "account_feedback_also_applied":False,
                "scope":"Independent, overlapping historical simulations with full costs. "
                        "Learn only after exit bars close, including setups the account skipped. "
                        "These examples are not account trades or profits."}
