"""Resolve open paper trades by checking market outcomes on Polymarket."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from mcp_servers.polymarket_server import get_market_details
from utils.data_storage import DataStorage
from utils.kill_switch import KillSwitch
from utils.logging_config import setup_logging, get_logger


def resolve_trades():
    """Check all open trades and resolve any that have settled."""
    setup_logging()
    logger = get_logger("resolve_trades")

    storage = DataStorage()
    kill_switch = KillSwitch()

    open_trades = storage.get_open_trades()
    logger.info(f"Found {len(open_trades)} open trades to check")

    resolved_count = 0
    total_pnl = 0.0

    for trade in open_trades:
        market_id = trade["market_id"]
        trade_id = trade["id"]
        side = trade["side"]
        entry_price = trade["entry_price"]
        position_size = trade["position_size"]

        try:
            raw = get_market_details(market_id)
            market = json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to fetch market {market_id}: {e}")
            continue

        # Check if market is resolved
        resolved = market.get("resolved", False)
        if not resolved:
            logger.debug(f"Market {market_id} not yet resolved, skipping")
            continue

        # Determine outcome
        outcome_str = market.get("outcome", "")
        if not outcome_str:
            logger.warning(f"Market {market_id} resolved but no outcome found")
            continue

        # Calculate P&L
        if side == "YES":
            if outcome_str.lower() in ("yes", "1", "true"):
                exit_price = 1.0
                pnl = (exit_price - entry_price) * position_size / entry_price
                outcome = "WIN"
            else:
                exit_price = 0.0
                pnl = -position_size
                outcome = "LOSS"
        else:  # NO side
            if outcome_str.lower() in ("no", "0", "false"):
                exit_price = 0.0
                pnl = (entry_price) * position_size / (1 - entry_price)
                outcome = "WIN"
            else:
                exit_price = 1.0
                pnl = -position_size
                outcome = "LOSS"

        storage.update_trade_resolution(trade_id, exit_price, pnl, outcome)
        resolved_count += 1
        total_pnl += pnl

        logger.info(
            f"Resolved trade #{trade_id}: {side} on '{trade['market_question'][:50]}' "
            f"-> {outcome} (P&L: ${pnl:+.2f})"
        )

    # Check drawdown after resolutions
    if resolved_count > 0:
        all_trades = storage.get_all_trades()
        settings = get_settings()
        starting = settings.paper_trading_starting_bankroll
        total_realized_pnl = sum(t.get("pnl", 0) or 0 for t in all_trades if t.get("status") == "CLOSED")
        current_bankroll = starting + total_realized_pnl

        peak = max(starting, current_bankroll)  # Simplified; real peak tracking needs history
        kill_switch.check_and_activate_on_drawdown(current_bankroll, peak)

    logger.info(f"Resolution complete: {resolved_count} trades resolved, P&L: ${total_pnl:+.2f}")
    print(f"Resolved {resolved_count} trades. Total P&L: ${total_pnl:+.2f}")


if __name__ == "__main__":
    resolve_trades()
