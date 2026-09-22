from lab.strategy_lab import attach_closed_context
from strategies.orb_15m import OpeningRange15m


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


def _session_bar(i, high, low, close, volume=100):
    open_ts = 0
    step = 300_000
    ts = i * step
    return {"ts": ts, "end_ts": ts + step, "open": close, "high": high, "low": low,
            "close": close, "volume": volume, "session": "2026-01-02",
            "session_open_ts": open_ts, "session_close_ts": 6 * 3600_000},
        {"_close": close, "_atr": 1}


def test_orb_waits_for_complete_range_then_first_break_only():
    rows, feats = [], []
    for i in range(3):
        row, feat = _session_bar(i, 10, 9, 9.5, 50)
        rows.append(row); feats.append(feat)
    row, feat = _session_bar(3, 11, 10, 11, 50)
    rows.append(row); feats.append(feat)
    row, feat = _session_bar(4, 12, 11, 12, 50)
    rows.append(row); feats.append(feat)
    OpeningRange15m().prepare(rows, feats, "5m")
    assert feats[2]["orb"]["ready"] is False
    assert feats[3]["orb"]["ready"] is True
    assert feats[3]["orb"]["first_break"] is True
    assert feats[4]["orb"]["first_break"] is False
    score, reason = OpeningRange15m().signal(feats[3], OpeningRange15m.params)
    assert score is None and reason == "relative_volume_not_ready"
