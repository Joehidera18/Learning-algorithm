"""Accelerated historical feedback from independent, fully costed simulations.

No generated prices, future labels, exchange orders or account P&L are used.
Every candidate uses the same execution engine as the selected policy. Candidate
outcomes overlap and must never be counted as account trades or independent bets.
"""
from .execution import simulation_steps
from .outcome_memory import trade_feedback
from .prediction_audit import PredictionAudit, entry_snapshot
from .practice import PRACTICE_LANES


class HistoricalFeedback:
    def __init__(self, rows, features, start, end, settings, policy, step, cancelled=None):
        self.policy, self.pending, self.runs = policy, [], []
        self.last_clock = -1
        self.count, self.by_family, self.gap_censored = 0, {}, 0
        self.loss_pause_overrides = 0
        self.predictions = PredictionAudit()
        self.by_practice_lane, self.seen_entries = {}, set()
        self.report_start_ts, self.by_entry_period = None, {}
        for index, params in enumerate(policy.candidates):
            if policy.legacy_candidates_only and params.get("atr_timeframe") == "daily":
                continue
            def resolved(trade, reward, available, index=index):
                self.pending.append((available, index, trade["training_vector"], reward, trade_feedback(trade),
                    {k:trade[k] for k in ("entry_forecast", "strategy_family", "reason", "practice_lane")}))
            def opened(trade, index=index):
                identity = (index, trade["entry_ts"])
                if identity in self.seen_entries:
                    raise ValueError("Duplicate candidate entry in shadow practice")
                self.seen_entries.add(identity)
                trade["entry_forecast"] = entry_snapshot(
                    policy.forecast(trade["decision_params"], trade["training_vector"]),
                    trade["signal_ts"]+step)
            for lane in PRACTICE_LANES:
                run = simulation_steps(rows, features, start, end, 500,
                    settings["risk_per_trade"], policy.fee_rate, policy.slippage_rate, params,
                    cancelled=cancelled, training_examples=True, bar_interval_ms=step,
                    on_resolved=resolved, on_entry=opened, practice_cost_mode=lane,
                    on_training_event=self._training_event, stream_only=True)
                try:
                    self.runs.append([next(run), run])
                except StopIteration:
                    pass

    def advance(self, closed_ms):
        if closed_ms < self.last_clock:
            raise ValueError("Historical feedback clock cannot move backwards")
        self.last_clock = closed_ms
        # Apply every candle's resolved labels before opening the next candle's
        # examples. Bulk advancement and incremental calls must make the same
        # forecasts; running one candidate to the end first would freeze them.
        while self.runs:
            clock = min(item[0] for item in self.runs)
            if clock > closed_ms:
                break
            alive = []
            for scheduled, run in self.runs:
                if scheduled > clock:
                    alive.append([scheduled, run])
                    continue
                try:
                    alive.append([next(run), run])
                except StopIteration:
                    pass
            self.runs = alive
            for available, index, vector, reward, outcome, audit in sorted(
                    self.pending, key=lambda x:(x[0], x[1], x[4]["entry_forecast"]["signal_close_ts"])):
                if available > clock:
                    raise ValueError("Future shadow outcome reached the learner")
                params = self.policy.candidates[index]
                self.predictions.observe(audit, reward)
                self.policy.observe(params, vector, reward, available, outcome=outcome)
                self.count += 1
                family = self.by_family.setdefault(params["family"], {"examples":0, "sum_net_r":0.})
                family["examples"] += 1
                family["sum_net_r"] += reward
                lane = self.by_practice_lane.setdefault(audit["practice_lane"],
                    {"resolved_examples":0, "sum_net_r":0., "net_losses":0})
                lane["resolved_examples"] += 1
                lane["sum_net_r"] += reward
                lane["net_losses"] += int(reward < 0)
                if self.report_start_ts is not None:
                    period = ("carried_in" if outcome["entry_forecast"]["signal_close_ts"] < self.report_start_ts
                              else "new_entry")
                    group = self.by_entry_period.setdefault(period,
                        {"resolved_examples":0, "sum_net_r":0., "net_losses":0, "by_practice_lane":{}})
                    detail = group["by_practice_lane"].setdefault(audit["practice_lane"],
                        {"resolved_examples":0, "sum_net_r":0., "net_losses":0})
                    for bucket in (group, detail):
                        bucket["resolved_examples"] += 1
                        bucket["sum_net_r"] += reward
                        bucket["net_losses"] += int(reward < 0)
            self.pending.clear()

    def _training_event(self, name, available_ts):
        # Record diagnostics at the actual event, not when a generator ends.
        # Otherwise resetting a reporting window would recount earlier events.
        if available_ts > self.last_clock:
            raise ValueError("Future practice diagnostic reached the report")
        if name == "gap_censored_examples":
            self.gap_censored += 1
        elif name == "loss_pause_overrides":
            self.loss_pause_overrides += 1
        else:
            raise ValueError("Unknown practice diagnostic")

    def begin_reporting(self, closed_ms):
        """Start a measurement window without restarting any learning or trades.

        Outcomes available exactly at the boundary belong to the earlier prefix.
        Open positions, cooldowns, deduplication and saved entry forecasts survive.
        """
        self.advance(closed_ms)
        self.report_start_ts = closed_ms
        self.count, self.by_family, self.by_practice_lane = 0, {}, {}
        self.gap_censored = self.loss_pause_overrides = 0
        self.by_entry_period = {}
        self.predictions = PredictionAudit()

    def summary(self):
        return {"mode":"historical_shadow", "resolved_examples":self.count,
                "by_family":self.by_family, "last_clock_ms":self.last_clock,
                "by_practice_lane":self.by_practice_lane,
                "report_start_ts":self.report_start_ts,
                "by_entry_period":self.by_entry_period,
                "gap_censored_examples":self.gap_censored,
                "loss_pause_overrides":self.loss_pause_overrides,
                "prediction_audit":self.predictions.summary(),
                "account_feedback_also_applied":False,
                "scope":"Separate cost-eligible and cost-blocked practice tracks per candidate, with full costs. "
                        "Entries belong to exactly one track; open examples in one cannot occupy the other. "
                        "Learn only after exit bars close, including setups the account skipped. "
                        "Reporting boundaries preserve open practice trades and entry forecasts. "
                        "Carried-in examples entered before the reporting boundary and resolved after it; "
                        "they are learning feedback, not new account trades. "
                        "Loss streaks do not pause this independent practice. These examples are not account trades or profits."}
