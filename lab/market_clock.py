"""Observed bar boundaries; stock metadata is supplied by the validated calendar adapter."""


def close_ts(row, step):
    return row.get("end_ts", row["ts"]+step)


def consecutive(previous, current, step):
    return current["ts"] == previous.get("next_ts", previous["ts"]+step)


def session_id(row):
    return row.get("session", row["ts"]//86400000)
