"""Tests for configuration module."""

import os
import pytest
from pydantic import ValidationError


def test_settings_loads():
    """Settings should load from environment variables."""
    from config.settings import Settings

    settings = Settings(
        anthropic_api_key="test-key-123",
        paper_trading_mode=True,
    )
    assert settings.anthropic_api_key == "test-key-123"
    assert settings.paper_trading_mode is True
    assert settings.kelly_fraction == 0.25
    assert settings.max_position_size_usd == 1000.0


def test_settings_validates_kelly_fraction():
    """Kelly fraction > 0.5 should be rejected."""
    with pytest.raises(ValidationError):
        from config.settings import Settings
        Settings(anthropic_api_key="test", kelly_fraction=0.6)


def test_settings_validates_log_level():
    """Invalid log levels should be rejected."""
    with pytest.raises(ValidationError):
        from config.settings import Settings
        Settings(anthropic_api_key="test", log_level="INVALID")


def test_risk_limits():
    """RiskLimits should validate and check positions."""
    from config.risk_limits import RiskLimits

    limits = RiskLimits(
        max_position_size_usd=1000.0,
        max_daily_loss_usd=200.0,
        max_drawdown_percent=20.0,
        kelly_fraction=0.25,
        min_edge_threshold=0.05,
    )

    # Valid position
    valid, reason = limits.validate_position_size(500, 10000)
    assert valid is True

    # Position too large (absolute)
    valid, reason = limits.validate_position_size(1500, 20000)
    assert valid is False
    assert "exceeds max" in reason

    # Position too large (fraction of bankroll)
    valid, reason = limits.validate_position_size(600, 5000)
    assert valid is False
    assert "exceeds" in reason


def test_risk_limits_edge_validation():
    """Edge below threshold should be rejected."""
    from config.risk_limits import RiskLimits

    limits = RiskLimits(
        max_position_size_usd=1000.0,
        max_daily_loss_usd=200.0,
        max_drawdown_percent=20.0,
        kelly_fraction=0.25,
        min_edge_threshold=0.05,
    )

    valid, _ = limits.validate_edge(0.10)
    assert valid is True

    valid, _ = limits.validate_edge(0.03)
    assert valid is False


def test_risk_limits_drawdown():
    """Drawdown check should flag excessive drawdown."""
    from config.risk_limits import RiskLimits

    limits = RiskLimits(
        max_position_size_usd=1000.0,
        max_daily_loss_usd=200.0,
        max_drawdown_percent=20.0,
        kelly_fraction=0.25,
        min_edge_threshold=0.05,
    )

    # Within limit
    valid, _ = limits.check_drawdown(9000, 10000)
    assert valid is True

    # Exceeded
    valid, _ = limits.check_drawdown(7500, 10000)
    assert valid is False
