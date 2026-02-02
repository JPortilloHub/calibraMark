"""Paper trading performance monitor and graduation criteria checker."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from config import get_settings
from utils import DataStorage
from .calibration_metrics import calculate_brier_score
from .statistical_tests import test_positive_expectation, calculate_sharpe_ratio


logger = logging.getLogger("calibramark.paper_trading")


class PaperTradingMonitor:
    """
    Monitor paper trading performance and check graduation criteria.

    Graduation criteria (must meet ALL for 30 consecutive days):
    1. Brier Score < 0.15
    2. Positive P&L with p < 0.05
    3. Max Drawdown < 20%
    4. Win Rate > 52%
    """

    GRADUATION_CRITERIA = {
        "min_days": 30,
        "max_brier_score": 0.15,
        "min_win_rate": 0.52,
        "max_drawdown_pct": 20.0,
        "pvalue_threshold": 0.05,
    }

    def __init__(self, storage: Optional[DataStorage] = None):
        """
        Initialize paper trading monitor.

        Args:
            storage: Optional DataStorage instance
        """
        settings = get_settings()
        self.storage = storage or DataStorage()
        self.starting_bankroll = settings.paper_trading_starting_bankroll
        self.logger = logging.getLogger("calibramark.paper_trading_monitor")

    def get_current_bankroll(self) -> float:
        """Calculate current bankroll from all trades."""
        trades = self.storage.get_all_trades()

        bankroll = self.starting_bankroll
        for trade in trades:
            if trade.get("pnl"):
                bankroll += trade["pnl"]

        return bankroll

    def get_peak_bankroll(self) -> float:
        """Calculate peak bankroll (maximum reached)."""
        trades = self.storage.get_all_trades()

        bankroll = self.starting_bankroll
        peak = bankroll

        for trade in trades:
            if trade.get("pnl"):
                bankroll += trade["pnl"]
                peak = max(peak, bankroll)

        return peak

    def calculate_current_drawdown(self) -> float:
        """Calculate current drawdown percentage."""
        current = self.get_current_bankroll()
        peak = self.get_peak_bankroll()

        if peak == 0:
            return 0.0

        drawdown_pct = ((peak - current) / peak) * 100
        return drawdown_pct

    def get_daily_pnl(self, date: Optional[str] = None) -> float:
        """
        Get P&L for a specific date.

        Args:
            date: Date in ISO format (YYYY-MM-DD), defaults to today

        Returns:
            Total P&L for that day
        """
        if date is None:
            date = datetime.now().date().isoformat()

        trades = self.storage.get_all_trades()

        daily_pnl = 0.0
        for trade in trades:
            trade_date = trade.get("timestamp", "")[:10]  # Extract YYYY-MM-DD
            if trade_date == date and trade.get("pnl"):
                daily_pnl += trade["pnl"]

        return daily_pnl

    def get_performance_metrics(self, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate performance metrics over specified period.

        Args:
            days: Number of days to look back (None = all time)

        Returns:
            Dict with performance metrics
        """
        trades = self.storage.get_all_trades()

        # Filter by date if specified
        if days is not None:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            trades = [t for t in trades if t.get("timestamp", "") >= cutoff_date]

        if len(trades) == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "brier_score": 0.0,
                "sharpe_ratio": 0.0,
                "is_profitable": False,
                "p_value": 1.0,
            }

        # Extract data
        pnl_values = [t.get("pnl", 0.0) for t in trades if t.get("pnl") is not None]
        predictions = [
            t.get("agent_probability")
            for t in trades
            if t.get("agent_probability") is not None and t.get("outcome") is not None
        ]
        outcomes = [
            t.get("outcome")
            for t in trades
            if t.get("agent_probability") is not None and t.get("outcome") is not None
        ]

        # Calculate metrics
        total_trades = len(trades)
        winning_trades = sum(1 for pnl in pnl_values if pnl > 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        total_pnl = sum(pnl_values)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

        # Brier score
        if len(predictions) > 0 and len(predictions) == len(outcomes):
            brier_score = calculate_brier_score(predictions, outcomes)
        else:
            brier_score = 0.0

        # Sharpe ratio
        if len(pnl_values) > 0:
            returns = [pnl / self.starting_bankroll for pnl in pnl_values]
            sharpe_ratio = calculate_sharpe_ratio(returns)
        else:
            sharpe_ratio = 0.0

        # Statistical significance
        if len(pnl_values) > 0:
            is_profitable, t_stat, p_value = test_positive_expectation(pnl_values)
        else:
            is_profitable = False
            p_value = 1.0

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "brier_score": brier_score,
            "sharpe_ratio": sharpe_ratio,
            "is_profitable": is_profitable,
            "p_value": p_value,
            "days_covered": days,
        }

    def check_graduation_criteria(self) -> Dict[str, Any]:
        """
        Check if system meets all graduation criteria.

        Returns:
            Dict with criteria status and overall readiness
        """
        # Get 30-day metrics
        metrics = self.get_performance_metrics(days=self.GRADUATION_CRITERIA["min_days"])

        # Get drawdown
        current_drawdown = self.calculate_current_drawdown()

        # Check each criterion
        criteria_met = {
            "min_trades": metrics["total_trades"] >= 10,  # Need at least 10 trades
            "brier_score": (
                metrics["brier_score"] < self.GRADUATION_CRITERIA["max_brier_score"]
                if metrics["brier_score"] > 0
                else False
            ),
            "positive_pnl": (
                metrics["is_profitable"]
                and metrics["p_value"] < self.GRADUATION_CRITERIA["pvalue_threshold"]
            ),
            "win_rate": metrics["win_rate"] > self.GRADUATION_CRITERIA["min_win_rate"],
            "drawdown": current_drawdown < self.GRADUATION_CRITERIA["max_drawdown_pct"],
        }

        all_met = all(criteria_met.values())

        return {
            "ready_for_real_trading": all_met,
            "criteria": {
                "min_trades": {
                    "required": 10,
                    "actual": metrics["total_trades"],
                    "met": criteria_met["min_trades"],
                },
                "brier_score": {
                    "required": f"< {self.GRADUATION_CRITERIA['max_brier_score']}",
                    "actual": metrics["brier_score"],
                    "met": criteria_met["brier_score"],
                },
                "positive_pnl": {
                    "required": f"p < {self.GRADUATION_CRITERIA['pvalue_threshold']}",
                    "actual": metrics["p_value"],
                    "met": criteria_met["positive_pnl"],
                },
                "win_rate": {
                    "required": f"> {self.GRADUATION_CRITERIA['min_win_rate']:.1%}",
                    "actual": metrics["win_rate"],
                    "met": criteria_met["win_rate"],
                },
                "drawdown": {
                    "required": f"< {self.GRADUATION_CRITERIA['max_drawdown_pct']}%",
                    "actual": f"{current_drawdown:.2f}%",
                    "met": criteria_met["drawdown"],
                },
            },
            "days_active": metrics.get("days_covered", 0),
            "metrics": metrics,
        }

    def generate_status_report(self) -> str:
        """Generate formatted status report."""
        metrics = self.get_performance_metrics(days=30)
        graduation = self.check_graduation_criteria()
        current_bankroll = self.get_current_bankroll()
        daily_pnl = self.get_daily_pnl()

        report = f"""
=== CalibraMark Paper Trading Status ===
Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}

💰 Performance (30 days)
- Current Bankroll: ${current_bankroll:,.2f}
- Total P&L: ${metrics['total_pnl']:,.2f}
- Today's P&L: ${daily_pnl:,.2f}
- Max Drawdown: {self.calculate_current_drawdown():.2f}%

📊 Trading Metrics
- Total Trades: {metrics['total_trades']}
- Win Rate: {metrics['win_rate']:.1%}
- Avg P&L per Trade: ${metrics['avg_pnl']:.2f}
- Sharpe Ratio: {metrics['sharpe_ratio']:.2f}

🎯 Calibration
- Brier Score: {metrics['brier_score']:.4f}
- Statistical Significance: p={metrics['p_value']:.4f}

✅ Graduation Criteria (30-day)
"""

        for criterion, data in graduation["criteria"].items():
            status = "✓" if data["met"] else "✗"
            report += f"  {status} {criterion}: {data['required']} (actual: {data['actual']})\n"

        if graduation["ready_for_real_trading"]:
            report += "\n🎉 READY FOR REAL TRADING! All graduation criteria met.\n"
        else:
            report += "\n⏳ Not ready for real trading. Continue paper trading.\n"

        report += "=" * 50

        return report
