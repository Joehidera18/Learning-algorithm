"""Display totals from completed trade ledgers; never used for trading decisions."""
from decimal import Decimal, InvalidOperation
import math


def closed_trade_totals(pnls):
    values = []
    for value in pnls:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("A completed trade is missing its net result") from None
        if not amount.is_finite():
            raise ValueError("A completed trade has an invalid net result")
        values.append(amount)
    won = sum((v for v in values if v > 0), Decimal(0))
    lost = -sum((v for v in values if v < 0), Decimal(0))
    wins, losses = sum(v > 0 for v in values), sum(v < 0 for v in values)
    amounts = [float(won), float(lost), float(won-lost)]
    if not all(math.isfinite(v) for v in amounts):
        raise ValueError("Trade totals are outside the supported range")
    return {"status":"available", "closed_trades":len(values),
        "winning_trades":wins, "losing_trades":losses,
        "break_even_trades":len(values)-wins-losses,
        "money_won":amounts[0], "money_lost":amounts[1], "net_pnl":amounts[2],
        "win_rate":100*wins/len(values) if values else None}


def historical_trade_totals(report):
    """Summarize only the complete selected final test, including marked END exits.

    Never infer a win/loss split from a rounded win rate or a sampled review.
    """
    missing = {"status":"unavailable", "message":"Complete saved test trades are unavailable. Run historical practice again."}
    holdout = report.get("holdout") or {}
    if report.get("error") or holdout.get("complete") is False or holdout.get("net_pnl") is None:
        return {"status":"unavailable", "message":"This market has no complete final test to total."}
    trades = report.get("holdout_trades")
    count = holdout.get("trades")
    if trades is None and count == 0:
        trades = []
    if (not isinstance(count,int) or isinstance(count,bool) or count < 0
            or not isinstance(trades,list) or len(trades) != count):
        return missing
    try:
        result = closed_trade_totals(t.get("pnl") for t in trades)
        if not math.isclose(result["net_pnl"], float(holdout["net_pnl"]), rel_tol=1e-8, abs_tol=1e-7):
            return missing
    except (ValueError, TypeError, AttributeError):
        return missing
    result["window_end_exits"] = sum(t.get("reason") == "END" for t in trades)
    return result
