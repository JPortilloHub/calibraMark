"""Evaluation framework for CalibraMark."""

from .backtesting import Backtester
from .calibration_metrics import (
    calculate_brier_score,
    calculate_ece,
    generate_calibration_curve,
)
from .edge_decay_monitor import EdgeDecayMonitor
from .paper_trading_monitor import PaperTradingMonitor
from .statistical_tests import (
    calculate_sharpe_ratio,
    bootstrap_confidence_interval,
    calculate_max_drawdown,
)

__all__ = [
    "Backtester",
    "calculate_brier_score",
    "calculate_ece",
    "generate_calibration_curve",
    "EdgeDecayMonitor",
    "PaperTradingMonitor",
    "calculate_sharpe_ratio",
    "bootstrap_confidence_interval",
    "calculate_max_drawdown",
]
