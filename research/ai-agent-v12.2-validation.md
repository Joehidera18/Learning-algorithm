# V12.2 AI agent verification — 2026-09-27

Base: `0afac426d4136116b7b0476f18119547114a385b` in
`Joehidera18/Learning-algorithm`. Target remains the existing Render service.

## Completed checks

| Check | Result |
| --- | --- |
| Complete Python test suite | 554 passed, including 24 new agent tests |
| Agent browser workflow | 13 passed |
| Existing stock dashboard browser workflow | 9 passed |
| Existing stock research browser workflow | 14 passed |
| Existing stock backtesting browser workflow | 10 passed |
| Python compilation, JavaScript syntax, whitespace checks | Passed |
| Desktop and 390px phone screenshots | Inspected; no horizontal overflow |

Backend coverage includes authentication, missing credentials, bounded requests,
Responses function-call continuation, reasoning-state replay, secret isolation,
inline citation offsets, rejected arbitrary tools and crypto test requests,
proposal validation, per-message backtest permission, duplicate job prevention,
two-job cap, cancellation, late replies, process leases, restart recovery,
idempotent submission, durable daily counts, conversation isolation, notebook
evidence classification, provider failures and authenticated export.

Browser checks use a real temporary WSGI app with simulated AI responses. They
exercise the app token, stock/crypto presets, inert HTML from model responses,
source links, report downloads, proposal handoff, actual queued job records,
notebook persistence, old-test links outside the recent status window, stopping
work, lost-response recovery without duplicate billing requests, missing-key
setup and deletion without changing test results or request counts.

The existing stock research browser harness had two stale expectations from
before the stock migration: the old token storage key and a removed crypto
dashboard label. Those assertions now match the already-existing stock behavior;
the production token handler was not changed.

## Limits of this verification

No OpenAI API key was available in the build workspace. No live OpenAI request,
paid web research or live model-quality evaluation was performed. Research and
backtest values in the new browser fixtures are synthetic and clearly labeled.
The test suite establishes software behavior, not investment performance.

Deployment still requires the existing Render service's server-side key, model
access and billing, followed by the small live checks in [AI_AGENT.md](../AI_AGENT.md).
Stock provider entitlements, live news availability and completeness of market
history depend on the deployed accounts and requested windows. The agent does
not place funded orders or automatically install new strategies.
