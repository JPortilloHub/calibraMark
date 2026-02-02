"""Polymarket MCP Server - Market data and paper trade execution.

Provides tools to:
- Fetch active and resolved markets from Polymarket
- Get market details and price history
- Execute paper trades (logged to local ledger)
- Check orderbook depth
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger("calibramark.mcp.polymarket")

# Polymarket public API endpoints (no auth required)
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

server = FastMCP(
    name="polymarket",
    instructions="Polymarket prediction market data provider. Fetches markets, prices, and history.",
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _gamma_get(endpoint: str, params: Optional[dict] = None, timeout: int = 30) -> Any:
    """Make a GET request to the Gamma API."""
    url = f"{GAMMA_API}{endpoint}"
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _clob_get(endpoint: str, params: Optional[dict] = None, timeout: int = 30) -> Any:
    """Make a GET request to the CLOB API."""
    url = f"{CLOB_API}{endpoint}"
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@server.tool(description="Fetch active prediction markets from Polymarket")
def get_active_markets(
    min_liquidity: float = 10000.0,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """
    Fetch active markets from Polymarket.

    Args:
        min_liquidity: Minimum liquidity in USD (default $10k)
        limit: Maximum number of markets to return
        offset: Pagination offset
    """
    try:
        params = {
            "_limit": limit,
            "_offset": offset,
            "closed": "false",
            "archived": "false",
            "active": "true",
        }

        markets = _gamma_get("/markets", params=params)

        # Filter by liquidity
        filtered = []
        for market in markets:
            liquidity = float(market.get("liquidity", 0))
            if liquidity >= min_liquidity:
                filtered.append({
                    "id": market.get("id"),
                    "question": market.get("question"),
                    "description": market.get("description", "")[:200],
                    "liquidity": liquidity,
                    "volume": float(market.get("volume", 0)),
                    "end_date": market.get("endDate"),
                    "outcomes": market.get("outcomes", []),
                    "tags": market.get("tags", []),
                    "market_type": market.get("marketType", "binary"),
                })

        return json.dumps({
            "count": len(filtered),
            "total_fetched": len(markets),
            "min_liquidity": min_liquidity,
            "markets": filtered,
        }, indent=2)

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": str(e)})


@server.tool(description="Get detailed info for a specific Polymarket market")
def get_market_details(market_id: str) -> str:
    """
    Get detailed information for a specific market.

    Args:
        market_id: Polymarket market ID
    """
    try:
        market = _gamma_get(f"/markets/{market_id}")

        return json.dumps({
            "id": market.get("id"),
            "question": market.get("question"),
            "description": market.get("description"),
            "liquidity": float(market.get("liquidity", 0)),
            "volume": float(market.get("volume", 0)),
            "outcomes": market.get("outcomes", []),
            "end_date": market.get("endDate"),
            "closed": market.get("closed", False),
            "resolution_date": market.get("closedTime"),
            "tags": market.get("tags", []),
            "market_type": market.get("marketType", "binary"),
            "created_at": market.get("createdAt"),
        }, indent=2)

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": str(e)})


@server.tool(description="Get price history for a Polymarket market")
def get_market_history(market_id: str, days_back: int = 30) -> str:
    """
    Get price history for a market.

    Args:
        market_id: Polymarket market ID
        days_back: Number of days of history to fetch
    """
    try:
        # Use the CLOB API for price history
        params = {
            "market": market_id,
            "interval": "1d" if days_back > 7 else "1h",
            "fidelity": min(days_back, 100),
        }

        history = _clob_get("/prices-history", params=params)

        return json.dumps({
            "market_id": market_id,
            "days_back": days_back,
            "data_points": len(history) if isinstance(history, list) else 0,
            "history": history,
        }, indent=2)

    except requests.exceptions.RequestException as e:
        # Fallback: return market current price if history unavailable
        try:
            market = _gamma_get(f"/markets/{market_id}")
            outcomes = market.get("outcomes", [])
            current_price = float(outcomes[0].get("price", 0.5)) if outcomes else 0.5
            return json.dumps({
                "market_id": market_id,
                "error": f"History unavailable: {e}",
                "current_price": current_price,
                "history": [],
            }, indent=2)
        except Exception:
            return json.dumps({"error": str(e)})


@server.tool(description="Get resolved markets for backtesting")
def get_resolved_markets(
    limit: int = 100,
    offset: int = 0,
) -> str:
    """
    Fetch resolved (closed) markets for backtesting.

    Args:
        limit: Maximum number of markets to return
        offset: Pagination offset
    """
    try:
        params = {
            "_limit": limit,
            "_offset": offset,
            "closed": "true",
            "archived": "false",
        }

        markets = _gamma_get("/markets", params=params)

        resolved = []
        for market in markets:
            outcomes = market.get("outcomes", [])

            # Determine outcome
            outcome = None
            if len(outcomes) >= 2:
                if outcomes[0].get("winner"):
                    outcome = 1
                elif outcomes[1].get("winner"):
                    outcome = 0

            resolved.append({
                "id": market.get("id"),
                "question": market.get("question"),
                "outcome": outcome,
                "resolution_date": market.get("closedTime"),
                "liquidity": float(market.get("liquidity", 0)),
                "volume": float(market.get("volume", 0)),
                "outcomes": outcomes,
            })

        return json.dumps({
            "count": len(resolved),
            "markets": resolved,
        }, indent=2)

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": str(e)})


@server.tool(description="Execute a paper trade (simulated, logged to local ledger)")
def execute_paper_trade(
    market_id: str,
    market_question: str,
    side: str,
    position_size: float,
    entry_price: float,
    agent_probability: float = 0.0,
    expected_value: float = 0.0,
    reasoning: str = "",
) -> str:
    """
    Record a paper trade to the local ledger.

    Args:
        market_id: Polymarket market ID
        market_question: The market question
        side: YES or NO
        position_size: Size of position in USD
        entry_price: Current market price (0-1)
        agent_probability: Agent's estimated probability
        expected_value: Expected value of the trade
        reasoning: Reasoning for the trade
    """
    trade = {
        "timestamp": datetime.now().isoformat(),
        "market_id": market_id,
        "market_question": market_question,
        "side": side.upper(),
        "position_size": position_size,
        "entry_price": entry_price,
        "agent_probability": agent_probability,
        "expected_value": expected_value,
        "reasoning": reasoning,
        "status": "OPEN",
        "pnl": None,
        "exit_price": None,
    }

    # Save to paper trades directory
    trades_dir = Path("data/paper_trades")
    trades_dir.mkdir(parents=True, exist_ok=True)

    trades_file = trades_dir / "trades.json"

    # Load existing trades
    existing_trades = []
    if trades_file.exists():
        with open(trades_file, "r") as f:
            existing_trades = json.load(f)

    # Append new trade
    trade["id"] = len(existing_trades) + 1
    existing_trades.append(trade)

    with open(trades_file, "w") as f:
        json.dump(existing_trades, f, indent=2)

    logger.info(f"Paper trade recorded: {side} {market_question} @ {entry_price}")

    return json.dumps({
        "status": "EXECUTED",
        "trade": trade,
    }, indent=2)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@server.resource("polymarket://paper-trades")
def get_paper_trades() -> str:
    """Read all paper trades."""
    trades_file = Path("data/paper_trades/trades.json")
    if trades_file.exists():
        with open(trades_file, "r") as f:
            return f.read()
    return json.dumps([])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.run(transport="stdio")
