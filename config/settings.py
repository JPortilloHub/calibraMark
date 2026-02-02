"""Application settings loaded from environment variables."""

import os
from datetime import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings with validation."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic API
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514", description="Claude model to use"
    )

    # Polymarket API
    polymarket_api_key: Optional[str] = Field(
        default=None, description="Polymarket API key (optional for read-only)"
    )
    polymarket_api_secret: Optional[str] = Field(default=None, description="Polymarket API secret")
    polymarket_private_key: Optional[str] = Field(
        default=None, description="Polymarket wallet private key"
    )
    polymarket_chain_id: int = Field(default=137, description="Polygon chain ID")

    # News APIs
    news_api_key: Optional[str] = Field(default=None, description="NewsAPI.org key (optional)")

    # Financial Data APIs
    fred_api_key: Optional[str] = Field(default=None, description="FRED API key (optional)")
    openbb_api_key: Optional[str] = Field(default=None, description="OpenBB API key (optional)")

    # Risk Management (loaded in risk_limits.py)
    max_position_size_usd: float = Field(default=1000.0, description="Max position size in USD")
    max_daily_loss_usd: float = Field(default=200.0, description="Max daily loss in USD")
    max_drawdown_percent: float = Field(default=20.0, description="Max drawdown percentage")
    kelly_fraction: float = Field(
        default=0.25, description="Fractional Kelly (0.25 = 25% of full Kelly)"
    )
    min_edge_threshold: float = Field(default=0.05, description="Minimum edge to trade (5%)")

    # Trading Mode
    paper_trading_mode: bool = Field(default=True, description="Enable paper trading mode")
    paper_trading_starting_bankroll: float = Field(
        default=10000.0, description="Starting bankroll for paper trading"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_dir: Path = Field(default=Path("data/logs"), description="Log directory")

    # Data Storage
    data_dir: Path = Field(default=Path("data"), description="Data directory")

    # Scheduling
    scan_time_utc: str = Field(default="10:00", description="Daily scan time (HH:MM UTC)")
    scan_enabled: bool = Field(default=True, description="Enable scheduled scans")

    # Market Scanning Filters
    min_market_liquidity: float = Field(
        default=10000.0, description="Minimum market liquidity in USD"
    )
    min_days_until_resolution: int = Field(default=1, description="Min days until market resolves")
    max_days_until_resolution: int = Field(default=90, description="Max days until market resolves")

    # Backtesting
    backtest_start_date: str = Field(default="2024-07-01", description="Backtest start date")
    backtest_end_date: str = Field(default="2025-01-31", description="Backtest end date")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v

    @field_validator("kelly_fraction")
    @classmethod
    def validate_kelly_fraction(cls, v: float) -> float:
        """Validate Kelly fraction is reasonable."""
        if not 0 < v <= 1:
            raise ValueError("kelly_fraction must be between 0 and 1")
        if v > 0.5:
            raise ValueError(
                "kelly_fraction > 0.5 is not recommended (too aggressive). Use <= 0.25 for safety."
            )
        return v

    @field_validator("max_drawdown_percent")
    @classmethod
    def validate_max_drawdown(cls, v: float) -> float:
        """Validate max drawdown percentage."""
        if not 0 < v <= 100:
            raise ValueError("max_drawdown_percent must be between 0 and 100")
        return v

    @field_validator("scan_time_utc")
    @classmethod
    def validate_scan_time(cls, v: str) -> str:
        """Validate scan time format."""
        try:
            time.fromisoformat(v)
        except ValueError:
            raise ValueError("scan_time_utc must be in HH:MM format")
        return v

    @property
    def scan_time_parsed(self) -> time:
        """Parse scan time string to time object."""
        return time.fromisoformat(self.scan_time_utc)

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        directories = [
            self.data_dir,
            self.log_dir,
            self.data_dir / "paper_trades",
            self.data_dir / "historical_markets",
            self.data_dir / "calibration_history",
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
