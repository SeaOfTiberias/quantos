# Prompts (S5-8)

Every Claude prompt QuantOS sends lives here as a `.md` file, not inline in
Python. Editing the analyst's instructions is a diff to a text file, and **git
history is the prompt changelog** — `git log -p prompts/pre_trade_user.md` shows
exactly how the live scoring prompt evolved and why.

## Convention

- One file per prompt, named `<module>_<role>.md`:
  - `*_system.md` — the Claude `system` prompt (static).
  - `*_user.md` — the per-request user message; a `str.format` template.
- Templates use named `{placeholder}` holes. Callers pass every hole as a
  keyword arg via `core.prompts.render(...)`. A missing/misspelled placeholder
  raises at render time — it can't silently ship a broken prompt.
- **Literal braces must be doubled** `{{ }}` (str.format rule) — see the JSON
  schema blocks in `*_recommender_user.md`, `backtest_analyst_user.md`,
  `screener_ranker_user.md`.

## Loading

`core/prompts/loader.py`:

```python
from core import prompts

prompts.load("pre_trade_system")                       # cached str
prompts.render("pre_trade_user", symbol="TCS", ...)    # filled template
prompts.preload("pre_trade_system", "pre_trade_user")  # fail-fast at startup
```

Prompts are cached process-for-life (a prompt edit ships as a redeploy). The
cloud API `preload()`s the hot-path `pre_trade_*` prompts on startup so a
missing file fails at deploy, not on the first live signal.

## Current prompts

| File | Used by |
|---|---|
| `pre_trade_system.md`, `pre_trade_user.md` | `cloud/analyst/pre_trade.py` (live webhook path) |
| `options_recommender_system.md`, `options_recommender_user.md` | `core/options/recommender.py` |
| `morning_brief_user.md` | `core/morning/brief.py` |
| `alpha_attribution_user.md` | `core/options/alpha_attribution.py` |
| `backtest_analyst_system.md`, `backtest_analyst_user.md` | `core/backtest/analyst.py` |
| `screener_ranker_system.md`, `screener_ranker_user.md` | `core/screener/ranker.py` |
| `analyst_chat_system.md` | `cloud/analyst/chat.py` (cockpit chat) |
