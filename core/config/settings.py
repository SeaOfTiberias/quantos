"""
QuantOS — Secrets & Config Management
───────────────────────────────────────
US-16: Centralised, validated configuration loader.

All secrets and config values flow through here — never scattered
across os.getenv() calls throughout the codebase. Validates required
keys at startup, provides typed accessors, and documents every variable.

Design principles:
  - No secrets in code or Git (enforced by .gitignore + this module)
  - Fail fast at startup if required config is missing
  - Typed access (not raw strings everywhere)
  - Rotation-friendly — keys swapped in Railway Variables UI, no redeploy needed
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION  = "production"
    TEST        = "test"


# ─── Config dataclass ────────────────────────────────────────────────────────

@dataclass
class QuantOSConfig:
    """
    Fully-typed, validated configuration for QuantOS.
    Built once at startup via QuantOSConfig.from_env().
    """

    # ── Environment ───────────────────────────────────────────────────────────
    environment:          Environment

    # ── Claude API ────────────────────────────────────────────────────────────
    anthropic_api_key:    str
    claude_model:         str = "claude-sonnet-4-6"

    # ── Webhook ───────────────────────────────────────────────────────────────
    webhook_secret:       str = ""           # empty = no validation (dev only)
    cloud_api_secret:     str = ""

    # ── WhatsApp / CallMeBot ──────────────────────────────────────────────────
    callmebot_phone:      str = ""
    callmebot_api_key:    str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url:         str = ""           # empty = in-memory fallback

    # ── Signal pipeline ───────────────────────────────────────────────────────
    min_confluence_score: float = 70.0
    regime_cache_ttl:     int   = 900        # 15 minutes
    default_capital:      float = 500_000.0  # INR

    # ── Risk limits ───────────────────────────────────────────────────────────
    max_risk_per_trade:   float = 0.02       # 2%
    max_open_positions:   int   = 5
    max_daily_loss_pct:   float = 0.05       # 5% daily circuit breaker

    # ── Screener ──────────────────────────────────────────────────────────────
    screener_min_volume:  int = 500_000
    screener_top_n:       int = 10

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level:            str = "INFO"

    @classmethod
    def from_env(cls) -> "QuantOSConfig":
        """
        Build config from environment variables.
        Validates required keys — raises ConfigError if missing in production.
        """
        env = Environment(os.getenv("ENVIRONMENT", "development").lower())

        # Required in all environments
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

        # Validate required keys for production
        if env == Environment.PRODUCTION:
            missing = []
            if not anthropic_key:
                missing.append("ANTHROPIC_API_KEY")
            if not os.getenv("WEBHOOK_SECRET"):
                missing.append("WEBHOOK_SECRET")
            if not os.getenv("CALLMEBOT_PHONE"):
                missing.append("CALLMEBOT_PHONE")
            if not os.getenv("CALLMEBOT_API_KEY"):
                missing.append("CALLMEBOT_API_KEY")
            if missing:
                raise ConfigError(
                    f"Missing required environment variables for production: "
                    f"{', '.join(missing)}\n"
                    f"See deploy/railway_env.md for setup instructions."
                )

        config = cls(
            environment=env,
            anthropic_api_key=anthropic_key,
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            cloud_api_secret=os.getenv("CLOUD_API_SECRET", ""),
            callmebot_phone=os.getenv("CALLMEBOT_PHONE", ""),
            callmebot_api_key=os.getenv("CALLMEBOT_API_KEY", ""),
            database_url=os.getenv("DATABASE_URL", ""),
            min_confluence_score=float(os.getenv("MIN_CONFLUENCE_SCORE", "70")),
            regime_cache_ttl=int(os.getenv("REGIME_CACHE_TTL", "900")),
            default_capital=float(os.getenv("DEFAULT_CAPITAL", "500000")),
            max_risk_per_trade=float(os.getenv("MAX_RISK_PER_TRADE", "0.02")),
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "5")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05")),
            screener_min_volume=int(os.getenv("SCREENER_MIN_VOLUME", "500000")),
            screener_top_n=int(os.getenv("SCREENER_TOP_N", "10")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

        config._log_startup_summary()
        return config

    # ── Convenience properties ─────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.callmebot_phone and self.callmebot_api_key)

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def claude_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    def _log_startup_summary(self) -> None:
        logger.info(
            "QuantOS config loaded: env=%s | claude=%s | whatsapp=%s | db=%s",
            self.environment.value,
            "✅" if self.claude_configured else "❌ MISSING",
            "✅" if self.whatsapp_configured else "❌ not configured",
            "✅ postgres" if self.database_configured else "⚠️  in-memory",
        )
        if not self.webhook_secret and self.is_production:
            logger.warning("WEBHOOK_SECRET not set — webhook validation disabled!")


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


# ── Module-level singleton ─────────────────────────────────────────────────────
# Loaded once at app startup. Tests override via env vars or direct instantiation.

_config: Optional[QuantOSConfig] = None


def get_config() -> QuantOSConfig:
    """Get the loaded config singleton. Call load_config() first at startup."""
    global _config
    if _config is None:
        _config = QuantOSConfig.from_env()
    return _config


def load_config() -> QuantOSConfig:
    """Explicitly load / reload config from environment. Called at app startup."""
    global _config
    _config = QuantOSConfig.from_env()
    return _config


def reset_config() -> None:
    """Reset singleton — used in tests to isolate environment state."""
    global _config
    _config = None
