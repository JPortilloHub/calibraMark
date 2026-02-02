"""Backtesting engine for CalibraMark.

This module provides the core backtesting functionality to validate
the trading system against historical resolved markets.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from .calibration_metrics import calculate_brier_score, analyze_calibration_by_bucket
from .statistical_tests import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    test_positive_expectation,
)


logger = logging.getLogger("calibramark.backtesting")


class BacktestResults:
    """Container for backtest results with analysis methods."""

    def __init__(self, trades: List[Dict[str, Any]], starting_bankroll: float = 10000.0):
        """
        Initialize backtest results.

        Args:
            trades: List of trade dicts with predictions and outcomes
            starting_bankroll: Starting bankroll for P&L calculation
        """
        self.trades = trades
        self.starting_bankroll = starting_bankroll
        self._calculate_metrics()

    def _calculate_metrics(self) -> None:
        """Calculate all performance metrics."""
        if len(self.trades) == 0:
            self.total_trades = 0
            self.total_pnl = 0.0
            self.win_rate = 0.0
            self.brier_score = 0.0
            self.sharpe_ratio = 0.0
            self.max_drawdown_pct = 0.0
            self.final_bankroll = self.starting_bankroll
            self.equity_curve = [self.starting_bankroll]
            return

        self.total_trades = len(self.trades)

        # Extract predictions and outcomes
        predictions = [t["agent_probability"] for t in self.trades if "agent_probability" in t]
        outcomes = [t["outcome"] for t in self.trades if "outcome" in t]

        # Calculate Brier score
        if predictions and outcomes and len(predictions) == len(outcomes):
            self.brier_score = calculate_brier_score(predictions, outcomes)
            self.calibration_analysis = analyze_calibration_by_bucket(predictions, outcomes)
        else:
            self.brier_score = 0.0
            self.calibration_analysis = []

        # Calculate P&L
        pnl_values = [t.get("pnl", 0.0) for t in self.trades]
        self.total_pnl = sum(pnl_values)

        # Calculate win rate
        winning_trades = sum(1 for pnl in pnl_values if pnl > 0)
        self.win_rate = winning_trades / self.total_trades if self.total_trades > 0 else 0.0

        # Build equity curve
        self.equity_curve = [self.starting_bankroll]
        bankroll = self.starting_bankroll
        for pnl in pnl_values:
            bankroll += pnl
            self.equity_curve.append(bankroll)

        self.final_bankroll = bankroll

        # Calculate Sharpe ratio (convert P&L to returns)
        if len(pnl_values) > 0 and self.starting_bankroll > 0:
            returns = [pnl / self.starting_bankroll for pnl in pnl_values]
            self.sharpe_ratio = calculate_sharpe_ratio(returns)
        else:
            self.sharpe_ratio = 0.0

        # Calculate max drawdown
        if len(self.equity_curve) > 1:
            self.max_drawdown_pct, self.dd_start_idx, self.dd_end_idx = calculate_max_drawdown(
                self.equity_curve
            )
        else:
            self.max_drawdown_pct = 0.0
            self.dd_start_idx = 0
            self.dd_end_idx = 0

        # Statistical significance
        if len(pnl_values) > 0:
            self.is_significant, self.t_stat, self.p_value = test_positive_expectation(pnl_values)
        else:
            self.is_significant = False
            self.t_stat = 0.0
            self.p_value = 1.0

    def summary(self) -> Dict[str, Any]:
        """Get summary of backtest results."""
        return {
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "brier_score": self.brier_score,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "final_bankroll": self.final_bankroll,
            "return_pct": (
                (self.final_bankroll - self.starting_bankroll) / self.starting_bankroll * 100
            ),
            "is_statistically_significant": self.is_significant,
            "p_value": self.p_value,
        }

    def print_summary(self) -> None:
        """Print formatted backtest summary."""
        summary = self.summary()

        print("\n" + "=" * 80)
        print("BACKTEST RESULTS SUMMARY")
        print("=" * 80)
        print(f"Total Trades:     {summary['total_trades']}")
        print(f"Win Rate:         {summary['win_rate']:.1%}")
        print(f"Total P&L:        ${summary['total_pnl']:.2f}")
        print(f"Return:           {summary['return_pct']:.2f}%")
        print(f"Final Bankroll:   ${summary['final_bankroll']:.2f}")
        print()
        print(f"Brier Score:      {summary['brier_score']:.4f} (lower is better)")
        print(f"Sharpe Ratio:     {summary['sharpe_ratio']:.2f}")
        print(f"Max Drawdown:     {summary['max_drawdown_pct']:.2f}%")
        print()
        print(f"Statistical Significance:")
        print(f"  p-value:        {summary['p_value']:.4f}")
        print(f"  Significant:    {'YES' if summary['is_statistically_significant'] else 'NO'} (at α=0.05)")
        print("=" * 80 + "\n")


class Backtester:
    """
    Backtesting engine that runs the trading system on historical data.

    IMPORTANT: Only uses data that would have been available at decision time
    to avoid look-ahead bias.
    """

    def __init__(self, historical_markets: List[Dict[str, Any]]):
        """
        Initialize backtester with historical market data.

        Args:
            historical_markets: List of resolved markets with:
                - market_id
                - question
                - resolution_date
                - outcome (0 or 1)
                - price_history (list of {timestamp, price} dicts)
        """
        self.historical_markets = historical_markets
        self.logger = logging.getLogger("calibramark.backtester")

    def run(
        self,
        agent_pipeline_func: callable,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        starting_bankroll: float = 10000.0,
    ) -> BacktestResults:
        """
        Run backtest over historical markets.

        Args:
            agent_pipeline_func: Function that takes market data and returns a trade decision
                Expected signature: func(market_data) -> {
                    "decision": "TRADE" or "NO_TRADE",
                    "side": "YES" or "NO",
                    "position_size": float,
                    "agent_probability": float,
                    "reasoning": str
                }
            start_date: Optional start date filter (ISO format)
            end_date: Optional end date filter (ISO format)
            starting_bankroll: Starting bankroll for simulation

        Returns:
            BacktestResults object
        """
        self.logger.info(f"Starting backtest on {len(self.historical_markets)} markets")

        # Filter markets by date if specified
        markets = self._filter_by_date(self.historical_markets, start_date, end_date)

        self.logger.info(f"Running backtest on {len(markets)} markets (after date filter)")

        trades = []
        bankroll = starting_bankroll

        for i, market in enumerate(markets):
            self.logger.debug(f"Processing market {i+1}/{len(markets)}: {market['question']}")

            try:
                # Run agent pipeline on this market
                decision = agent_pipeline_func(market)

                if decision["decision"] == "TRADE":
                    # Simulate trade
                    trade = self._simulate_trade(market, decision, bankroll)
                    trades.append(trade)

                    # Update bankroll
                    bankroll += trade["pnl"]

                    self.logger.debug(
                        f"Trade executed: {trade['side']} at {trade['entry_price']:.3f}, "
                        f"P&L: ${trade['pnl']:.2f}"
                    )

            except Exception as e:
                self.logger.error(f"Error processing market {market['market_id']}: {e}")
                continue

        self.logger.info(f"Backtest complete. Executed {len(trades)} trades.")

        return BacktestResults(trades, starting_bankroll)

    def _filter_by_date(
        self, markets: List[Dict[str, Any]], start_date: Optional[str], end_date: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Filter markets by resolution date."""
        if not start_date and not end_date:
            return markets

        filtered = []
        for market in markets:
            resolution_date = market.get("resolution_date")
            if not resolution_date:
                continue

            if start_date and resolution_date < start_date:
                continue
            if end_date and resolution_date > end_date:
                continue

            filtered.append(market)

        return filtered

    def _simulate_trade(
        self, market: Dict[str, Any], decision: Dict[str, Any], bankroll: float
    ) -> Dict[str, Any]:
        """
        Simulate a trade and calculate P&L.

        Args:
            market: Market data with outcome
            decision: Agent decision
            bankroll: Current bankroll

        Returns:
            Trade record with P&L
        """
        side = decision["side"]
        position_size = min(decision["position_size"], bankroll * 0.1)  # Cap at 10% of bankroll
        entry_price = market.get("current_price", 0.5)  # Use market price at decision time
        outcome = market["outcome"]  # 0 or 1

        # Calculate P&L based on outcome
        if side == "YES":
            # Betting YES means we win if outcome is 1
            if outcome == 1:
                # Win: get 1.0 per share, paid entry_price
                pnl = position_size * (1.0 - entry_price)
            else:
                # Loss: lose what we paid
                pnl = -position_size * entry_price
        else:  # side == "NO"
            # Betting NO means we win if outcome is 0
            if outcome == 0:
                # Win: get 1.0 per share, paid (1 - entry_price)
                pnl = position_size * entry_price
            else:
                # Loss: lose what we paid
                pnl = -position_size * (1 - entry_price)

        return {
            "timestamp": datetime.now().isoformat(),
            "market_id": market["market_id"],
            "market_question": market["question"],
            "side": side,
            "position_size": position_size,
            "entry_price": entry_price,
            "exit_price": 1.0 if outcome == 1 else 0.0,
            "pnl": pnl,
            "outcome": outcome,
            "agent_probability": decision.get("agent_probability"),
            "reasoning": decision.get("reasoning"),
        }
