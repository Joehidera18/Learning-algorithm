"""Map a headline to negative / mixed / positive. This is not a forecast.

Prefer the vendor's per-ticker insight when Massive supplies one. Otherwise use
a small explicit word list. Ambiguous text stays mixed. Never invent a time.
"""
POSITIVE = (
    "beats", "beat estimates", "raises guidance", "upgrade", "upgraded",
    "record revenue", "buyback", "approved", "wins contract", "surge",
    "higher than expected", "profit jumps",
)
NEGATIVE = (
    "misses", "miss estimates", "cuts guidance", "downgrade", "downgraded",
    "probe", "investigation", "lawsuit", "recall", "bankruptcy", "layoffs",
    "fraud", "restatement", "warning", "plunge", "lower than expected",
)

VENDOR = {"positive": 1.0, "negative": -1.0, "neutral": 0.0, "mixed": 0.0}


def vendor_score(insights, ticker):
    if not isinstance(insights, list):
        return None
    ticker = (ticker or "").upper()
    hits = []
    for item in insights:
        if not isinstance(item, dict):
            continue
        name = str(item.get("ticker") or "").upper()
        if ticker and name and name != ticker:
            continue
        label = str(item.get("sentiment") or "").lower()
        if label in VENDOR:
            hits.append(VENDOR[label])
    if not hits:
        return None
    return sum(hits) / len(hits)


def lexicon_score(text):
    blob = " ".join(part for part in text if part).lower()
    if not blob:
        return 0.0
    up = sum(1 for word in POSITIVE if word in blob)
    down = sum(1 for word in NEGATIVE if word in blob)
    if up == down:
        return 0.0
    return (up - down) / (up + down)


def article_score(article, ticker):
    vendor = vendor_score(article.get("insights"), ticker)
    if vendor is not None:
        return vendor, "massive_insight"
    text = (article.get("title"), article.get("description"), article.get("summary"))
    return lexicon_score(text), "keyword_list"
