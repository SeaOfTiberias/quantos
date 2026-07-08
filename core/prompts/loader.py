"""
QuantOS — Prompt Loader (S5-8 / P2-5)
─────────────────────────────────────
Claude prompts live as plain-text files under the repo's top-level
`prompts/` directory instead of inline Python string literals, so that:

  • git history becomes the prompt changelog (who changed the analyst
    instructions, when, and why — reviewable in a diff, not buried in code),
  • prompts can be edited without touching/redeploying logic, and
  • every Claude-calling module loads its prompt the same way.

Files are `.md` (Markdown reads well and Claude handles it natively). A
prompt with runtime holes is a `str.format()` template — named `{placeholders}`
filled via `render()`. Literal braces in a template must be doubled `{{ }}`
per `str.format` rules.

Loaded prompts are cached process-for-life (they never change under a running
process — a prompt edit ships as a redeploy). Call `preload()` at startup to
fail fast if a prompt file is missing, rather than on the first live signal.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Repo-root/prompts by default (…/core/prompts/loader.py → parents[2] == root).
# Overridable via env for tests or alternate deploys.
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPTS_DIR = Path(os.getenv("QUANTOS_PROMPTS_DIR", str(_DEFAULT_DIR)))


class PromptNotFoundError(FileNotFoundError):
    """Raised when a named prompt file does not exist under PROMPTS_DIR."""


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """Return the text of `prompts/{name}.md`, trailing whitespace stripped.

    Cached for the life of the process. `name` is a bare stem, no extension
    and no path separators (e.g. "pre_trade_system").
    """
    if "/" in name or "\\" in name or name.endswith(".md"):
        raise ValueError(f"Prompt name must be a bare stem, got: {name!r}")
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def render(name: str, /, **kwargs) -> str:
    """Load prompt `name` and fill its `{placeholder}` holes via str.format.

    `name` is positional-only so a prompt may legitimately have a `{name}`
    placeholder without colliding with this parameter.
    """
    return load(name).format(**kwargs)


def preload(*names: str) -> None:
    """Force-load prompts now so a missing file fails at startup, not on the
    first live request. Pass the prompt stems a module depends on."""
    for name in names:
        load(name)


def clear_cache() -> None:
    """Drop the in-process cache — test hook (e.g. after pointing
    QUANTOS_PROMPTS_DIR at a fixture)."""
    load.cache_clear()
