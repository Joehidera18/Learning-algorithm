# Stock Lab AI Research Agent

Open **AI Research Agent** at `/agent` on the existing Stock Lab website.
It can investigate stocks, ETFs and crypto, search current sources, read the
app's saved evidence and connect a research question to supported stock tests.
The agent is an optional addition to the existing app.

## Enable on the existing Render service

1. Merge this change into the branch used by `Joehidera18/Learning-algorithm`.
2. In the **existing** `learning-algorithm-wah5.onrender.com` service, add
   `OPENAI_API_KEY` under Environment. Use a key from your OpenAI API project
   with billing and model access. Do not paste it into chat, the website or git.
3. Keep `APP_ACCESS_TOKEN`, the persistent disk and existing data paths. The
   agent requires both an app token and an API key; it won't accept paid work
   or reveal conversation history on an unprotected instance.
4. Optionally set `OPENAI_MODEL` (default `gpt-6-astra`) and
   `AGENT_DAILY_RUN_LIMIT` (default 25 requests per UTC day, valid 1–100).
   Use a Responses API model that supports strict function calls and web search.
5. Save environment changes and deploy the latest commit. Automatic deployment
   remains off. Confirm `/api/health` reports `app_version: 12.2`.
6. Open `/agent`, connect using the **app token**, and try “Read our workspace
   and explain which saved results are available” with web search off. Then
   try a small sourced company research question with web search on. Inspect
   citations and the API project's usage before running larger requests.

API usage is separate from a ChatGPT subscription. The app has request and token
limits, not a dollar budget. Configure appropriate account/project usage controls
in OpenAI as well. Provider errors do not reveal raw responses or secrets.

## Research workflows

- **Emerging science:** public companies in quantum computing, gene editing,
  medicine and AI. Compare cash runway, dilution, competition, valuation, dated
  catalysts and the strongest opposing case. Trial targets are not clinical
  achievements, and a breakthrough is not a guarantee of shareholder returns.
- **Crypto opportunities:** adoption and token value capture, circulating versus
  fully diluted valuation, unlocks, liquidity, security and concentration.
  The stock execution engine remains stock-only.
- **Read my results:** inspect recent stock learning, paper summaries and named
  strategy reports. The saved watchlist retains its original research date.
- **Test a strategy:** inspect the supported catalog, run an authorized test,
  review later-period and higher-cost evidence, and save a lesson. Novel ideas
  can be researched and specified, but must be implemented and separately
  verified before this app can backtest them.

Presets only fill the form. **Start research** begins work. Enable **Allow up to
2 stock backtests** to permit that message to queue tests. Otherwise the agent
can propose tests, and **Review backtest** opens the existing form with validated
settings. Proposals recheck provider availability when opened. The user reviews
the form before running it. Agent-created tests use the app's existing costs,
sizing constraints, provider limits and minimum 20-minute candle cutoff delay.

The agent can wait briefly for a test. Long stock jobs may finish after the
research conversation; their links remain available on **Backtest stocks**.
Ask a follow-up to review and record their results. A stopped agent does not
cancel previously queued stock tests; those have their own cancel controls.

## How the agent learns

The strategy notebook stores a test's request, report version, later and
higher-cost evidence, an AI interpretation and a next hypothesis. The server
computes the evidence label from the saved report:

| Label | Meaning |
| --- | --- |
| Obsolete report | Rerun with the current backtester before relying on it |
| Incomplete | One comparison cannot establish complete account performance |
| Insufficient trades | Fewer than 20 trades in either later comparison |
| Did not pass | Failed the historical screen or its required positive metrics |
| Passed historical checks | Current complete report passes later and higher-cost checks |

All labels describe historical evidence. None approves live trading. The agent
reads this notebook in later research; this is persistent research memory, not
automatic retraining of the language model. Repeatedly choosing strategies on
the same later data can overfit. Collect new untouched data and forward paper
evidence before treating a lesson as established.

## Runtime, usage and privacy

- One background agent run at a time per persistent data directory. HTTP starts
  return quickly; requests and tool waits run in a daemon worker. Stock tests
  retain the existing shared computation slot. No new paid Render resource.
- Standard: up to 5 model responses and approximately 4 minutes. Deep research:
  up to 10 responses and approximately 15 minutes. An in-flight API request can
  extend the elapsed limit until its bounded network timeout expires.
- Up to 12 app tool calls, 2 queued tests and 2 proposals per message. At most 3
  built-in web calls per model response. Responses allow up to 4,000 output
  tokens including reasoning; a final tool-free response is requested after
  16,000 observed output tokens. Context is also bounded. These limits are not
  a promise of exhaustive research or guaranteed completion.
- No automatic paid retries. Client-generated request IDs make a lost-response
  retry idempotent. Daily request counts survive restarts and chat deletion.
  Failed or stopped runs still count because provider usage may have occurred.
- A process lease prevents competing agent workers from replaying work. After
  restart, interrupted research becomes an error; it is not silently resumed.
  Stock job IDs are saved immediately after queuing. Inspect Backtest stocks
  after an interruption before starting another test.
- Conversations use a shared-owner app token, not separate user accounts. Anyone
  with that token can read the same agent history and use the shared allowance.
- The server sends prompts, bounded recent conversation context and requested
  app evidence to OpenAI. Current research can invoke OpenAI web search. Never
  enter credentials or sensitive personal information into a research prompt.
- `store: false` is used for model responses. Provider retention policies still
  apply. The app retains conversation records for 90 days, pruning at startup or
  before new work. The UI lists the latest 30 conversations and displays up to
  60 messages per conversation; model context uses up to 6 recent completed
  exchanges with a 20,000-character history bound.
- The notebook lists the latest 30 lessons. Lessons persist until removed and
  are independent of conversation deletion. Both lessons and conversations have
  delete controls. Deleting a lesson does not delete its underlying backtest.
- Storage: `RESEARCH_DATA_DIR/stock-agent/conversations.sqlite3` on the existing
  disk. Include this directory in normal backups. No provider keys, raw reasoning
  or full provider responses are saved in that database.
- Model content is rendered as text. Only HTTP(S) source links are clickable.
  App tools cannot execute code, browse arbitrary server URLs, read secrets,
  install strategies, modify broker settings or submit real orders.

## Implementation and verification

`lab/stock_agent.py` provides the bounded Responses API loop and persistence;
`static/stock-agent.js` provides the authenticated UI. `StockService` owns the
agent's lifecycle. `StrategyLabJobs.validate_request` is shared by proposals and
real tests so the two paths cannot silently diverge.

Run the Python suite with `python -m unittest discover -s tests -q`. Run the
agent browser checks with `node tests/check_stock_agent_browser.js` after
installing Playwright and Chromium. The browser harness uses a temporary local
server, simulated provider replies and synthetic historical results. It never
spends API credits or places orders. A missing-key panel is the real production
behavior until credentials are supplied; it is not a demo chatbot.

The implementation follows the official [function calling guide](https://developers.openai.com/api/docs/guides/function-calling),
[web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
and [reasoning state guidance](https://developers.openai.com/api/docs/guides/reasoning).
Replay output items for tool continuations; expose actual citation annotations
as clickable inline sources. Live API compatibility, model access and research
quality must be checked with the deployment's own key. Local fixtures alone
cannot establish those properties or investment performance.
