# News folder

Headlines can help a day-trade bot **skip** a long when the tape is clearly
bad. They cannot reliably tell the bot to buy. This folder stores and scores
news for the strategy lab. It does not place orders.

## Rules

- An article is visible on a bar only if `published_ts` is at or before that
  bar's close.
- Massive ticker insights (`positive` / `negative` / `neutral`) are used when
  present. Otherwise a short keyword list runs on the title and description.
- No news on that bar means `news.ready = False`. Strategies must skip or ignore,
  not guess.
- Good/bad scores are a **filter**, not a standalone strategy. The earlier crypto
  event features had zero historical coverage; do not repeat that by trading a
  sentiment number that did not exist at the time.

## Files

- `news/massive_news.py` — download `/v2/reference/news` for one ticker
- `news/score.py` — vendor insight or keyword polarity
- `news/attach.py` — stamp `features["news"]` onto decision bars

## Run with the lab

```sh
export MASSIVE_API_KEY=your_key
python run_strategy_lab.py --strategy orb_15m --symbol AAPL --asset equity --provider massive --decision 5m --days 120 --news --out reports/aapl-orb-news.json
```

`orb_15m` will refuse a long if the last 24 hours of visible news score below
`-0.35` (cluster of negative headlines). Missing news does not block the trade.

## Honesty

Vendor sentiment is a model, not ground truth. Keywords miss sarcasm and
"beats but guides down." Earnings *reactions* often happen before the article
is timestamped. Use news as context next to price, then keep the later-window
promotion gate.
