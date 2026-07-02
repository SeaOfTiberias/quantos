"""
QuantOS — Strategy Versioning Models
──────────────────────────────────────
US-09: Data structures for tracking strategy parameter changes over time.

Every time a strategy's parameters change, we:
  1. Snapshot the new parameters
  2. Compute a backtest delta (if available)
  3. Ask Claude to write a commit message explaining the change
  4. Push to GitHub as a versioned JSON file

This gives a full audit trail: what changed, when, why, and what
the performance impact was — just like Git for code, but for trading strategies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class BacktestDelta:
    """
    Performance delta between old and new strategy parameters.
    All fields are optional — may not be available for every change.
    """
    sharpe_before:   Optional[float] = None
    sharpe_after:    Optional[float] = None
    win_rate_before: Optional[float] = None
    win_rate_after:  Optional[float] = None
    max_dd_before:   Optional[float] = None    # max drawdown %
    max_dd_after:    Optional[float] = None
    total_trades_before: Optional[int] = None
    total_trades_after:  Optional[int] = None

    @property
    def sharpe_change(self) -> Optional[float]:
        if self.sharpe_before is not None and self.sharpe_after is not None:
            return round(self.sharpe_after - self.sharpe_before, 3)
        return None

    @property
    def win_rate_change(self) -> Optional[float]:
        if self.win_rate_before is not None and self.win_rate_after is not None:
            return round(self.win_rate_after - self.win_rate_before, 4)
        return None

    @property
    def is_improvement(self) -> Optional[bool]:
        """True if Sharpe improved, None if no data."""
        if self.sharpe_change is None:
            return None
        return self.sharpe_change > 0

    def to_dict(self) -> dict:
        return {
            "sharpe":    {"before": self.sharpe_before, "after": self.sharpe_after,
                          "delta": self.sharpe_change},
            "win_rate":  {"before": self.win_rate_before, "after": self.win_rate_after,
                          "delta": self.win_rate_change},
            "max_dd":    {"before": self.max_dd_before, "after": self.max_dd_after},
            "trades":    {"before": self.total_trades_before, "after": self.total_trades_after},
        }


@dataclass
class StrategyVersion:
    """
    A versioned snapshot of a strategy's parameters.
    Stored as JSON in the GitHub repo under strategies/{strategy_name}/versions/.
    """
    strategy_name:   str
    version:         str                    # semver-style: "1.0.0", "1.1.0"
    parameters:      dict[str, Any]
    changed_params:  list[str]             # which params changed vs previous
    author:          str                   # "system" | "greg" | "claude"
    commit_message:  str                   # Claude-authored summary
    rationale:       str                   # why the change was made
    backtest_delta:  Optional[BacktestDelta] = None
    timestamp:       datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    commit_sha:      Optional[str] = None  # populated after push

    def to_dict(self) -> dict:
        return {
            "strategy_name":  self.strategy_name,
            "version":        self.version,
            "parameters":     self.parameters,
            "changed_params": self.changed_params,
            "author":         self.author,
            "commit_message": self.commit_message,
            "rationale":      self.rationale,
            "backtest_delta": self.backtest_delta.to_dict() if self.backtest_delta else None,
            "timestamp":      self.timestamp.isoformat(),
            "commit_sha":     self.commit_sha,
        }


@dataclass
class StrategyRegistry:
    """In-memory registry of all known strategies and their current parameters."""
    strategies: dict[str, dict] = field(default_factory=dict)  # name → current params
    versions:   dict[str, list[StrategyVersion]] = field(default_factory=dict)  # name → history

    def register(self, name: str, params: dict) -> None:
        self.strategies[name] = params
        if name not in self.versions:
            self.versions[name] = []

    def get_current(self, name: str) -> Optional[dict]:
        return self.strategies.get(name)

    def get_history(self, name: str) -> list[StrategyVersion]:
        return self.versions.get(name, [])

    def add_version(self, version: StrategyVersion) -> None:
        name = version.strategy_name
        if name not in self.versions:
            self.versions[name] = []
        self.versions[name].append(version)
        self.strategies[name] = version.parameters
