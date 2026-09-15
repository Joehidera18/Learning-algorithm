"""One fixed research exit rule, driven only by completed position candles."""
from .trade_review import net_at_price

FIXED_EXIT = "fixed"
BREAK_EVEN_EXIT = "fee_covered_break_even"
EXIT_POLICIES = {FIXED_EXIT, BREAK_EVEN_EXIT}


def break_even_price(trade):
    sign = 1 if trade.get("direction", "LONG") == "LONG" else -1
    fee, slip = trade["fee_rate"], trade["slippage_rate"]
    return trade["entry"]*(sign+fee)/(sign-fee)/(1-sign*slip)


def protect_after_close(trade, candle, step):
    """Called after this bar's exits. The raised stop applies to the NEXT bar."""
    if (trade["decision_params"].get("exit_policy", FIXED_EXIT) != BREAK_EVEN_EXIT
            or trade.get("break_even_active_ts") is not None):
        return False
    if net_at_price(trade, candle["close"])/trade["risk_dollars"] < 1:
        return False
    price = break_even_price(trade)
    trade["stop"] = (max(trade["stop"], price) if trade["direction"] == "LONG"
                     else min(trade["stop"], price))
    trade["break_even_active_ts"] = candle["ts"]+step
    return True
