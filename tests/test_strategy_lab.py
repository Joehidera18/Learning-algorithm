from lab.strategy_lab import attach_closed_context


def _bar(ts, step, close):
    return {"ts": ts, "end_ts": ts + step, "open": close, "high": close, "low": close,
            "close": close, "volume": 1}


def test_context_uses_only_already_closed_bars():
    decision = [_bar(900_000 * i, 900_000, 100 + i) for i in range(8)]
    hourly = [_bar(3_600_000 * i, 3_600_000, 200 + i) for i in range(2)]
    attach_closed_context(decision, "15m", {"1h": hourly})
    first = decision[0]["mtf"]["1h"]
    assert first["ready"] is False
    later = decision[4]["mtf"]["1h"]
    assert later["ready"] is True
    assert later["end_ts"] <= decision[4]["end_ts"]
    assert later["close"] == 200


def test_missing_higher_bar_is_not_filled_forward():
    decision = [_bar(60_000 * i, 60_000, 10) for i in range(10)]
    hourly = [_bar(0, 3_600_000, 99)]
    attach_closed_context(decision, "1m", {"1h": hourly})
    assert all(row["mtf"]["1h"]["ready"] is False for row in decision)
