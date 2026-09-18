"""Complementary practice tracks; neither track is an account or portfolio."""

PRACTICE_LANES = ("eligible", "cost_blocked")


def merge_counts(target, source):
    for key, value in source.items():
        if isinstance(value, dict):
            merge_counts(target.setdefault(key, {}), value)
        else:
            target[key] = target.get(key, 0) + value


def outcome_totals(trades):
    resolved = [t for t in trades if t["reason"] != "END"]
    return {"resolved_examples":len(resolved),
            "sum_net_r":sum(t["r_multiple"] for t in resolved),
            "net_losses":sum(t["r_multiple"] < 0 for t in resolved)}
