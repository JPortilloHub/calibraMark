"""Risk management limits and validation."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .settings import get_settings


class RiskLimits(BaseModel):
    """Risk management limits."""

    max_position_size_usd: float = Field(..., description="Maximum position size in USD")
    max_daily_loss_usd: float = Field(..., description="Maximum daily loss in USD")
    max_drawdown_percent: float = Field(..., description="Maximum drawdown percentage")
    kelly_fraction: float = Field(..., description="Fractional Kelly multiplier")
    min_edge_threshold: float = Field(..., description="Minimum edge required to trade")

    @field_validator("max_position_size_usd", "max_daily_loss_usd")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("max_drawdown_percent")
    @classmethod
    def validate_percentage(cls, v: float) -> float:
        """Validate percentage is between 0 and 100."""
        if not 0 < v <= 100:
            raise ValueError("Percentage must be between 0 and 100")
        return v

    @field_validator("kelly_fraction")
    @classmethod
    def validate_kelly(cls, v: float) -> float:
        """Validate Kelly fraction is reasonable."""
        if not 0 < v <= 1:
            raise ValueError("Kelly fraction must be between 0 and 1")
        if v > 0.5:
            raise ValueError("Kelly fraction > 0.5 is too aggressive")
        return v

    @field_validator("min_edge_threshold")
    @classmethod
    def validate_edge_threshold(cls, v: float) -> float:
        """Validate edge threshold is reasonable."""
        if not 0 <= v < 1:
            raise ValueError("Edge threshold must be between 0 and 1")
        return v

    def validate_position_size(self, size: float, bankroll: float) -> tuple[bool, str]:
        """
        Validate a proposed position size against limits.

        Returns:
            tuple: (is_valid, reason)
        """
        # Check absolute limit
        if size > self.max_position_size_usd:
            return (
                False,
                f"Position size ${size:.2f} exceeds max ${self.max_position_size_usd:.2f}",
            )

        # Check as percentage of bankroll (max 10%)
        max_fraction_of_bankroll = 0.10
        if size > bankroll * max_fraction_of_bankroll:
            return (
                False,
                f"Position size ${size:.2f} exceeds {max_fraction_of_bankroll:.0%} of bankroll "
                f"${bankroll:.2f}",
            )

        return True, "Valid"

    def validate_edge(self, edge: float) -> tuple[bool, str]:
        """
        Validate edge meets minimum threshold.

        Returns:
            tuple: (is_valid, reason)
        """
        if edge < self.min_edge_threshold:
            return (
                False,
                f"Edge {edge:.2%} below minimum threshold {self.min_edge_threshold:.2%}",
            )
        return True, "Valid"

    def check_drawdown(self, current_bankroll: float, peak_bankroll: float) -> tuple[bool, str]:
        """
        Check if current drawdown exceeds limit.

        Returns:
            tuple: (within_limit, reason)
        """
        if peak_bankroll == 0:
            return True, "No drawdown yet"

        drawdown_pct = ((peak_bankroll - current_bankroll) / peak_bankroll) * 100

        if drawdown_pct > self.max_drawdown_percent:
            return (
                False,
                f"Drawdown {drawdown_pct:.1f}% exceeds limit {self.max_drawdown_percent:.1f}%",
            )

        return True, f"Drawdown {drawdown_pct:.1f}% within limit"


# Singleton instance
_risk_limits: Optional[RiskLimits] = None


def get_risk_limits() -> RiskLimits:
    """Get or create risk limits singleton from settings."""
    global _risk_limits
    if _risk_limits is None:
        settings = get_settings()
        _risk_limits = RiskLimits(
            max_position_size_usd=settings.max_position_size_usd,
            max_daily_loss_usd=settings.max_daily_loss_usd,
            max_drawdown_percent=settings.max_drawdown_percent,
            kelly_fraction=settings.kelly_fraction,
            min_edge_threshold=settings.min_edge_threshold,
        )
    return _risk_limits
