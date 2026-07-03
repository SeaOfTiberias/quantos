"""
US-16 Secrets & Config Management — Unit Tests
"""

import pytest
import os

from core.config.settings import (
    QuantOSConfig, ConfigError, Environment,
    get_config, load_config, reset_config,
)
from core.config.rotate import generate_secret


class TestQuantOSConfig:

    def setup_method(self):
        reset_config()

    def test_loads_from_env_defaults(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        config = QuantOSConfig.from_env()
        assert config.environment == Environment.DEVELOPMENT
        assert config.anthropic_api_key == "sk-ant-test"

    def test_default_values(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        monkeypatch.setenv("ENVIRONMENT", "development")
        config = QuantOSConfig.from_env()
        assert config.min_confluence_score == 70.0
        assert config.regime_cache_ttl == 900
        assert config.default_capital == 500_000.0
        assert config.max_risk_per_trade == 0.02
        assert config.screener_top_n == 10

    def test_numeric_env_vars_parsed(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "75")
        monkeypatch.setenv("REGIME_CACHE_TTL", "600")
        monkeypatch.setenv("DEFAULT_CAPITAL", "1000000")
        config = QuantOSConfig.from_env()
        assert config.min_confluence_score == 75.0
        assert config.regime_cache_ttl == 600
        assert config.default_capital == 1_000_000.0

    def test_production_raises_on_missing_required_keys(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("CALLMEBOT_PHONE", raising=False)
        monkeypatch.delenv("CALLMEBOT_API_KEY", raising=False)
        with pytest.raises(ConfigError) as exc:
            QuantOSConfig.from_env()
        assert "ANTHROPIC_API_KEY" in str(exc.value)

    def test_development_does_not_require_all_keys(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("CALLMEBOT_PHONE", raising=False)
        config = QuantOSConfig.from_env()
        assert config.environment == Environment.DEVELOPMENT

    def test_is_production_property(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        config = QuantOSConfig.from_env()
        assert config.is_production is False
        assert config.is_development is True

    def test_whatsapp_configured_when_both_set(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "7123456789:AAFxxxxx")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "895737628")
        config = QuantOSConfig.from_env()
        assert config.whatsapp_configured is True

    def test_whatsapp_not_configured_when_missing(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        config = QuantOSConfig.from_env()
        assert config.whatsapp_configured is False

    def test_claude_configured_with_key(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        config = QuantOSConfig.from_env()
        assert config.claude_configured is True

    def test_database_not_configured_when_url_missing(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        config = QuantOSConfig.from_env()
        assert config.database_configured is False

    def test_database_configured_when_url_set(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/quantos")
        config = QuantOSConfig.from_env()
        assert config.database_configured is True


class TestConfigSingleton:

    def setup_method(self):
        reset_config()

    def test_get_config_returns_same_instance(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_load_config_reloads(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "70")
        c1 = load_config()

        monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "80")
        c2 = load_config()

        assert c2.min_confluence_score == 80.0
        assert c2 is not c1

    def test_reset_config_clears_singleton(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        c1 = get_config()
        reset_config()
        c2 = get_config()
        assert c1 is not c2


class TestSecretGeneration:

    def test_generate_secret_length(self):
        s = generate_secret(32)
        assert len(s) == 32

    def test_generate_secret_custom_length(self):
        s = generate_secret(64)
        assert len(s) == 64

    def test_generate_secret_unique(self):
        s1 = generate_secret()
        s2 = generate_secret()
        assert s1 != s2

    def test_generate_secret_not_empty(self):
        s = generate_secret()
        assert len(s) > 0
