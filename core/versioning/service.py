"""
QuantOS — Strategy Versioning Service
───────────────────────────────────────
US-09: Detects parameter changes, asks Claude to write a commit message,
and pushes the versioned snapshot to GitHub.

GitHub integration uses the REST API directly (no git binary needed on
the cloud server) — authenticated with a PAT stored in env vars.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import anthropic
import httpx

from core.versioning.models import (
    BacktestDelta, StrategyVersion, StrategyRegistry,
)

logger = logging.getLogger(__name__)

_claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


class StrategyVersioningService:
    """
    Manages strategy versioning — detects changes, authors commit
    messages via Claude, and pushes snapshots to GitHub.
    """

    def __init__(
        self,
        registry: Optional[StrategyRegistry] = None,
        github_token: Optional[str] = None,
        github_repo: str = "SeaOfTiberias/quantos",
        branch: str = "main",
    ):
        self.registry = registry or StrategyRegistry()
        self._github_token = github_token or os.getenv("GITHUB_PAT", "")
        self._github_repo = github_repo
        self._branch = branch

    async def update_strategy(
        self,
        strategy_name: str,
        new_params: dict[str, Any],
        rationale: str = "",
        backtest_delta: Optional[BacktestDelta] = None,
        author: str = "system",
        push_to_github: bool = True,
    ) -> StrategyVersion:
        """
        Record a strategy parameter change. If params differ from current,
        creates a new version with Claude-authored commit message and
        optionally pushes to GitHub.

        Args:
            strategy_name: e.g. "darvas_breakout"
            new_params: the full new parameter dict
            rationale: why the change was made (human note)
            backtest_delta: performance comparison before/after (optional)
            author: who triggered the change
            push_to_github: whether to push the version file to GitHub

        Returns:
            StrategyVersion — the recorded version (commit_sha populated if pushed)
        """
        current = self.registry.get_current(strategy_name)
        changed = _diff_params(current or {}, new_params)

        if not changed and current is not None:
            logger.info("No parameter changes detected for %s — skipping version", strategy_name)
            history = self.registry.get_history(strategy_name)
            if history:
                return history[-1]

        version_str = _next_version(self.registry.get_history(strategy_name))
        commit_message = await _generate_commit_message(
            strategy_name, changed, new_params, current or {}, backtest_delta, rationale,
        )

        version = StrategyVersion(
            strategy_name=strategy_name,
            version=version_str,
            parameters=new_params,
            changed_params=changed,
            author=author,
            commit_message=commit_message,
            rationale=rationale,
            backtest_delta=backtest_delta,
            timestamp=datetime.now(timezone.utc),
        )

        self.registry.add_version(version)
        logger.info("Strategy version recorded: %s v%s — %s",
                    strategy_name, version_str, commit_message[:60])

        if push_to_github and self._github_token:
            sha = await self._push_to_github(version)
            version.commit_sha = sha

        return version

    # ── GitHub integration ────────────────────────────────────────────────────

    async def _push_to_github(self, version: StrategyVersion) -> Optional[str]:
        """Push versioned JSON to GitHub via REST API."""
        path = (
            f"strategies/{version.strategy_name}/versions/"
            f"{version.version}-{version.timestamp.strftime('%Y%m%d%H%M%S')}.json"
        )
        content = json.dumps(version.to_dict(), indent=2)
        import base64
        content_b64 = base64.b64encode(content.encode()).decode()

        # Check if file exists (needed for SHA to update existing file)
        existing_sha = await self._get_file_sha(path)

        payload: dict = {
            "message": version.commit_message,
            "content": content_b64,
            "branch": self._branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.put(
                    f"https://api.github.com/repos/{self._github_repo}/contents/{path}",
                    headers={
                        "Authorization": f"Bearer {self._github_token}",
                        "Accept": "application/vnd.github+json",
                    },
                    json=payload,
                )

            if resp.status_code in (200, 201):
                commit_sha = resp.json().get("commit", {}).get("sha", "")[:12]
                logger.info("Pushed strategy version to GitHub: %s (sha=%s)", path, commit_sha)
                return commit_sha
            else:
                logger.error("GitHub push failed: %d — %s", resp.status_code, resp.text[:200])
                return None
        except Exception as e:
            logger.error("GitHub push error: %s", e)
            return None

    async def _get_file_sha(self, path: str) -> Optional[str]:
        """Get existing file SHA (needed for updates via GitHub API)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{self._github_repo}/contents/{path}",
                    headers={
                        "Authorization": f"Bearer {self._github_token}",
                        "Accept": "application/vnd.github+json",
                    },
                    params={"ref": self._branch},
                )
            if resp.status_code == 200:
                return resp.json().get("sha")
        except Exception:
            pass
        return None

    # ── Query methods ─────────────────────────────────────────────────────────

    def get_history(self, strategy_name: str) -> list[StrategyVersion]:
        return self.registry.get_history(strategy_name)

    def get_current_params(self, strategy_name: str) -> Optional[dict]:
        return self.registry.get_current(strategy_name)

    def weekly_changelog(self) -> str:
        """Generate a weekly summary of all strategy changes."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        lines = ["📋 *QuantOS Weekly Strategy Changelog*", "━━━━━━━━━━━━━━"]
        found = False
        for name, versions in self.registry.versions.items():
            recent = [v for v in versions if v.timestamp >= cutoff]
            if recent:
                found = True
                lines.append(f"\n*{name}* — {len(recent)} change(s):")
                for v in recent[-3:]:  # show last 3
                    symbol = "✅" if not v.backtest_delta or v.backtest_delta.is_improvement else "⚠️"
                    lines.append(f"  {symbol} v{v.version}: {v.commit_message[:60]}")
        if not found:
            lines.append("No strategy changes this week.")
        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _diff_params(old: dict, new: dict) -> list[str]:
    """Return list of parameter names that changed."""
    changed = []
    all_keys = set(old) | set(new)
    for k in all_keys:
        if old.get(k) != new.get(k):
            changed.append(k)
    return sorted(changed)


def _next_version(history: list[StrategyVersion]) -> str:
    """Increment minor version. Start at 1.0.0."""
    if not history:
        return "1.0.0"
    last = history[-1].version
    try:
        major, minor, patch = map(int, last.split("."))
        return f"{major}.{minor + 1}.0"
    except Exception:
        return "1.0.0"


async def _generate_commit_message(
    strategy_name: str,
    changed_params: list[str],
    new_params: dict,
    old_params: dict,
    delta: Optional[BacktestDelta],
    rationale: str,
) -> str:
    """Ask Claude to write a concise, informative commit message."""
    changes_str = "\n".join(
        f"  {p}: {old_params.get(p, 'N/A')} → {new_params.get(p, 'N/A')}"
        for p in changed_params
    )

    delta_str = ""
    if delta:
        delta_str = f"\nBacktest delta: Sharpe {delta.sharpe_change:+.3f}" \
                    if delta.sharpe_change is not None else ""

    prompt = f"""Write a concise Git commit message for this strategy parameter change.

Strategy: {strategy_name}
Changed parameters:
{changes_str}
Rationale: {rationale or 'Not specified'}
{delta_str}

Rules:
- First line: imperative mood, max 72 chars, no period
- Optionally 1-2 bullet lines with key impact
- Focus on WHAT changed and WHY (not HOW)
- No markdown, no code blocks

Return ONLY the commit message text, nothing else."""

    try:
        response = await _claude.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("Claude commit message generation failed: %s", e)
        return f"chore({strategy_name}): update {', '.join(changed_params[:3])}"
