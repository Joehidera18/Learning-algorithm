"""Display totals from completed trade ledgers; never used for trading decisions."""
from decimal import Decimal, InvalidOperation
import math
import json


def execution_audit(trade, costs):
    """Recompute a single complete fill pair, independently of stored P&L.

    Fill prices already contain slippage/spread. Subtract explicit fees once.
    Older rows without frozen costs are unknown, never assumed to be free.
    """
    if not costs:
        return {"status":"unavailable", "reason":"Frozen entry costs are missing"}
    try:
        def number(value):
            if isinstance(value, bool):
                raise ValueError("Boolean amount")
            value = Decimal(str(value))
            if not value.is_finite():
                raise ValueError("Non-finite amount")
            return value
        entry, exit_price, qty, fee, stored, risk = map(number,
            (trade["entry"], trade["exit"], trade["qty"], costs["fee_rate"], trade["pnl"], trade["risk_usd"]))
        if min(entry, exit_price, qty, risk) <= 0 or not 0 <= fee <= 1:
            raise ValueError("Invalid fill or fee")
        if trade["direction"] not in ("LONG", "SHORT"):
            raise ValueError("Unknown direction")
        sign = 1 if trade["direction"] == "LONG" else -1
        gross = (exit_price-entry)*qty*sign
        fees = (entry+exit_price)*qty*fee
        expected = gross-fees
        difference = stored-expected
        r_difference = number(trade["result_r"])-expected/risk
        ok = abs(difference) <= Decimal("0.0000001") and abs(r_difference) <= Decimal("0.0000001")
        result = {"status":"reconciled" if ok else "mismatch", "gross_pnl":float(gross),
            "fees_paid":float(fees), "expected_net_pnl":float(expected),
            "net_difference":float(difference), "r_difference":float(r_difference)}
        if not all(math.isfinite(v) for v in result.values() if isinstance(v,float)):
            raise ValueError("Amounts outside supported range")
        return result
    except (KeyError, TypeError, ValueError, InvalidOperation, ArithmeticError):
        return {"status":"unavailable", "reason":"Incomplete or invalid fill evidence"}


def ordered_paper_rows(rows):
    """Use the commit sequence when closes share the same timestamp."""
    decisions = {}
    for row in rows:
        try:
            decision = json.loads(row.get("decision_json") or "{}")
            if not isinstance(decision,dict):decision={}
        except (ValueError, TypeError, AttributeError):
            decision = {}
        decisions[row["id"]] = decision
    # Quotes share second-resolution journal timestamps. The explicit commit
    # sequence prevents a later-opened, earlier-closed trade from being reordered.
    ordered = sorted(rows,key=lambda r:("account_sequence" in decisions[r["id"]],
        decisions[r["id"]].get("account_sequence",r["closed_at"]),r["id"]))
    return ordered,decisions


def paper_account_audit(rows, portfolio):
    """Reconcile the entire closed journal, including its running balance."""
    checked, unknown, problems = 0, 0, []
    expected_balance = float(portfolio["starting_balance"])
    rows,decisions=ordered_paper_rows(rows)
    for row in rows:
        decision=decisions[row["id"]]
        costs=decision.get("execution_costs")
        audit = execution_audit(row, costs)
        checked += audit["status"] != "unavailable"
        unknown += audit["status"] == "unavailable"
        if audit["status"] == "mismatch":
            problems.append({"trade_id":row["id"], "check":"fill_profit", **audit})
        expected_balance += row["pnl"]
        if "account_sequence" in decision and not math.isclose(expected_balance, row["balance_after"], rel_tol=0, abs_tol=1e-7):
            problems.append({"trade_id":row["id"], "check":"running_balance"})
    totals = closed_trade_totals(r["pnl"] for r in rows)
    if (not math.isclose(expected_balance,portfolio["balance"],rel_tol=0,abs_tol=1e-7)
            or not math.isclose(totals["net_pnl"],portfolio["realized_pnl"],rel_tol=0,abs_tol=1e-7)):
        problems.append({"check":"account_balance"})
    return {"status":"mismatch" if problems else "partial" if unknown else "reconciled",
        "checked_trades":checked, "unknown_trades":unknown, "problem_count":len(problems),
        "problems":problems[:20], "expected_balance":expected_balance,
        "scope":"Fills already include spread and slippage. Fees are deducted once. "
                "Legacy rows without frozen costs cannot pass the fill check. No balances are rewritten."}


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
