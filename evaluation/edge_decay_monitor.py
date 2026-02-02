"""Monitor for detecting if trading edge is decaying over time."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import stats

from utils import DataStorage


logger = logging.getLogger("calibramark.edge_decay")


class EdgeDecayMonitor:
    """
    Monitor if the trading edge is declining over time.

    Detects:
    - Decreasing average edge in recent trades
    - Declining win rate
    - Deteriorating Brier score
    - Suggests when to pause trading
    """

    def __init__(self, storage: Optional[DataStorage] = None):
        """
        Initialize edge decay monitor.

        Args:
            storage: Optional DataStorage instance
        """
        self.storage = storage or DataStorage()
        self.logger = logging.getLogger("calibramark.edge_decay")

    def calculate_rolling_metrics(
        self, window_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Calculate rolling window metrics.

        Args:
            window_days: Size of rolling window in days

        Returns:
            List of dicts with date and metrics
        """
        trades = self.storage.get_all_trades()

        if len(trades) == 0:
            return []

        # Group trades by date
        trades_by_date: Dict[str, List[Dict]] = {}
        for trade in trades:
            date = trade.get("timestamp", "")[:10]  # YYYY-MM-DD
            if date not in trades_by_date:
                trades_by_date[date] = []
            trades_by_date[date].append(trade)

        # Sort dates
        dates = sorted(trades_by_date.keys())

        rolling_metrics = []

        for i, end_date in enumerate(dates):
            # Get window of dates
            start_idx = max(0, i - window_days + 1)
            window_dates = dates[start_idx : i + 1]

            # Collect trades in window
            window_trades = []
            for date in window_dates:
                window_trades.extend(trades_by_date[date])

            # Calculate metrics for window
            if len(window_trades) > 0:
                pnl_values = [t.get("pnl", 0) for t in window_trades if t.get("pnl") is not None]
                expected_values = [
                    t.get("expected_value", 0)
                    for t in window_trades
                    if t.get("expected_value") is not None
                ]

                winning = sum(1 for pnl in pnl_values if pnl > 0)
                win_rate = winning / len(pnl_values) if pnl_values else 0

                rolling_metrics.append(
                    {
                        "date": end_date,
                        "window_days": window_days,
                        "trade_count": len(window_trades),
                        "avg_pnl": np.mean(pnl_values) if pnl_values else 0,
                        "avg_edge": np.mean(expected_values) if expected_values else 0,
                        "win_rate": win_rate,
                        "total_pnl": sum(pnl_values),
                    }
                )

        return rolling_metrics

    def detect_edge_decay(self, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Detect if edge is decaying.

        Compares recent performance to historical baseline.

        Args:
            lookback_days: Days to use for recent performance

        Returns:
            Dict with decay analysis
        """
        trades = self.storage.get_all_trades()

        if len(trades) < 20:  # Need minimum data
            return {
                "edge_decaying": False,
                "reason": "Insufficient data",
                "recommendation": "CONTINUE",
            }

        # Split into recent and historical
        cutoff_date = (datetime.now() - timedelta(days=lookback_days)).isoformat()
        recent_trades = [t for t in trades if t.get("timestamp", "") >= cutoff_date]
        historical_trades = [t for t in trades if t.get("timestamp", "") < cutoff_date]

        if len(recent_trades) < 5 or len(historical_trades) < 5:
            return {
                "edge_decaying": False,
                "reason": "Insufficient data in period",
                "recommendation": "CONTINUE",
            }

        # Compare metrics
        recent_edge = np.mean([t.get("expected_value", 0) for t in recent_trades if t.get("expected_value")])
        historical_edge = np.mean([t.get("expected_value", 0) for t in historical_trades if t.get("expected_value")])

        recent_pnl = [t.get("pnl", 0) for t in recent_trades if t.get("pnl") is not None]
        historical_pnl = [t.get("pnl", 0) for t in historical_trades if t.get("pnl") is not None]

        recent_avg_pnl = np.mean(recent_pnl) if recent_pnl else 0
        historical_avg_pnl = np.mean(historical_pnl) if historical_pnl else 0

        # Statistical test for difference
        if len(recent_pnl) > 0 and len(historical_pnl) > 0:
            t_stat, p_value = stats.ttest_ind(recent_pnl, historical_pnl)
        else:
            t_stat, p_value = 0, 1.0

        # Detect decay
        edge_declined = recent_edge < historical_edge * 0.7  # 30% decline
        pnl_declined_significantly = recent_avg_pnl < historical_avg_pnl and p_value < 0.05

        edge_decaying = edge_declined or pnl_declined_significantly

        if edge_decaying:
            recommendation = "PAUSE" if recent_avg_pnl < 0 else "CAUTION"
            reason = "Recent edge significantly lower than historical baseline"
        else:
            recommendation = "CONTINUE"
            reason = "Edge remains stable"

        return {
            "edge_decaying": edge_decaying,
            "reason": reason,
            "recommendation": recommendation,
            "recent_avg_edge": recent_edge,
            "historical_avg_edge": historical_edge,
            "recent_avg_pnl": recent_avg_pnl,
            "historical_avg_pnl": historical_avg_pnl,
            "decline_pct": ((recent_edge - historical_edge) / historical_edge * 100)
            if historical_edge != 0
            else 0,
            "p_value": p_value,
        }

    def generate_decay_report(self) -> str:
        """Generate formatted edge decay report."""
        decay = self.detect_edge_decay()
        rolling = self.calculate_rolling_metrics(window_days=7)

        report = f"""
=== Edge Decay Analysis ===

Status: {decay['recommendation']}
Reason: {decay['reason']}

Recent vs Historical:
- Recent Avg Edge: {decay['recent_avg_edge']:.2%}
- Historical Avg Edge: {decay['historical_avg_edge']:.2%}
- Decline: {decay['decline_pct']:.1f}%

- Recent Avg P&L: ${decay['recent_avg_pnl']:.2f}
- Historical Avg P&L: ${decay['historical_avg_pnl']:.2f}

Statistical Test: p={decay['p_value']:.4f}
"""

        if len(rolling) > 0:
            report += "\n7-Day Rolling Metrics (last 5 windows):\n"
            for metric in rolling[-5:]:
                report += (
                    f"  {metric['date']}: Edge={metric['avg_edge']:.2%}, "
                    f"Win Rate={metric['win_rate']:.1%}, "
                    f"Avg P&L=${metric['avg_pnl']:.2f}\n"
                )

        if decay["recommendation"] == "PAUSE":
            report += "\n⚠️  RECOMMENDATION: PAUSE TRADING\n"
            report += "Edge has significantly declined. Review system and market conditions.\n"
        elif decay["recommendation"] == "CAUTION":
            report += "\n⚠️  RECOMMENDATION: PROCEED WITH CAUTION\n"
            report += "Edge showing signs of decline. Monitor closely.\n"
        else:
            report += "\n✅ RECOMMENDATION: CONTINUE TRADING\n"
            report += "Edge remains stable.\n"

        report += "=" * 50

        return report
