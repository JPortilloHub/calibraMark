"""Fetch historical resolved markets from Polymarket for backtesting.

This script fetches resolved markets from Polymarket and stores them
in data/historical_markets/ for use in backtesting.
"""

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import requests
from config import get_settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PolymarketHistoricalFetcher:
    """Fetch historical resolved markets from Polymarket."""

    # Polymarket Gamma API endpoints
    GAMMA_API_BASE = "https://gamma-api.polymarket.com"

    def __init__(self):
        """Initialize fetcher."""
        self.settings = get_settings()
        self.output_dir = self.settings.data_dir / "historical_markets"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_markets(
        self,
        start_date: str,
        end_date: str,
        min_liquidity: float = 10000.0,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch markets from Polymarket.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            min_liquidity: Minimum liquidity filter
            limit: Maximum number of markets to fetch

        Returns:
            List of market dicts
        """
        logger.info(f"Fetching markets from {start_date} to {end_date}")

        url = f"{self.GAMMA_API_BASE}/markets"

        params = {
            "_limit": limit,
            "_offset": 0,
            "closed": "true",  # Only resolved markets
            "archived": "false",
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            markets = response.json()

            logger.info(f"Fetched {len(markets)} markets from API")

            # Filter by date and liquidity
            filtered_markets = []
            for market in markets:
                # Check if market has required fields
                if not all(key in market for key in ["id", "question", "closed", "outcomes"]):
                    continue

                # Check if market is actually resolved
                if not market.get("closed"):
                    continue

                # Check liquidity (if available)
                liquidity = market.get("liquidity", 0)
                if liquidity < min_liquidity:
                    continue

                # Check date range
                closed_time = market.get("closedTime") or market.get("endDate")
                if closed_time:
                    try:
                        market_date = datetime.fromisoformat(closed_time.replace("Z", "+00:00"))
                        start = datetime.fromisoformat(start_date)
                        end = datetime.fromisoformat(end_date)

                        if not (start <= market_date <= end):
                            continue
                    except (ValueError, AttributeError):
                        continue

                filtered_markets.append(market)

            logger.info(
                f"Filtered to {len(filtered_markets)} markets "
                f"(liquidity >= ${min_liquidity:,.0f})"
            )

            return filtered_markets

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching markets: {e}")
            return []

    def transform_market_for_backtesting(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Polymarket market data to backtesting format.

        Args:
            market: Raw market data from API

        Returns:
            Transformed market dict suitable for backtesting
        """
        # Extract outcome (1 if YES won, 0 if NO won)
        outcome = None
        outcomes = market.get("outcomes", [])

        if len(outcomes) >= 2:
            # Typically outcomes[0] is YES, outcomes[1] is NO
            yes_outcome = outcomes[0]
            outcome = 1 if yes_outcome.get("winning") else 0

        # Get current/final price
        current_price = 0.5  # Default to 50%
        if outcomes and len(outcomes) > 0:
            current_price = float(outcomes[0].get("price", 0.5))

        return {
            "market_id": market.get("id"),
            "question": market.get("question"),
            "description": market.get("description", ""),
            "outcome": outcome,
            "outcomes": outcomes,
            "current_price": current_price,
            "resolution_date": market.get("closedTime") or market.get("endDate"),
            "liquidity": market.get("liquidity", 0),
            "volume": market.get("volume", 0),
            "created_at": market.get("createdAt"),
            "end_date": market.get("endDate"),
            "tags": market.get("tags", []),
            "market_type": market.get("marketType", "binary"),
        }

    def save_markets(self, markets: List[Dict[str, Any]], filename: str) -> None:
        """
        Save markets to JSON file.

        Args:
            markets: List of market dicts
            filename: Output filename
        """
        output_path = self.output_dir / filename

        # Transform markets for backtesting
        transformed_markets = [self.transform_market_for_backtesting(m) for m in markets]

        # Filter out markets without outcomes
        valid_markets = [m for m in transformed_markets if m["outcome"] is not None]

        logger.info(f"Saving {len(valid_markets)} markets with valid outcomes")

        with open(output_path, "w") as f:
            json.dump(valid_markets, f, indent=2)

        logger.info(f"Saved markets to {output_path}")

        # Print summary
        self._print_summary(valid_markets)

    def _print_summary(self, markets: List[Dict[str, Any]]) -> None:
        """Print summary of fetched markets."""
        if len(markets) == 0:
            return

        yes_outcomes = sum(1 for m in markets if m["outcome"] == 1)
        no_outcomes = sum(1 for m in markets if m["outcome"] == 0)

        avg_liquidity = sum(m.get("liquidity", 0) for m in markets) / len(markets)
        avg_volume = sum(m.get("volume", 0) for m in markets) / len(markets)

        print("\n" + "=" * 80)
        print("HISTORICAL DATA SUMMARY")
        print("=" * 80)
        print(f"Total Markets:      {len(markets)}")
        print(f"YES Outcomes:       {yes_outcomes} ({yes_outcomes/len(markets)*100:.1f}%)")
        print(f"NO Outcomes:        {no_outcomes} ({no_outcomes/len(markets)*100:.1f}%)")
        print(f"Avg Liquidity:      ${avg_liquidity:,.2f}")
        print(f"Avg Volume:         ${avg_volume:,.2f}")
        print("=" * 80 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch historical resolved markets from Polymarket"
    )
    parser.add_argument(
        "--start-date",
        default=(datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d"),
        help="Start date (YYYY-MM-DD), default: 180 days ago",
    )
    parser.add_argument(
        "--end-date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD), default: today",
    )
    parser.add_argument(
        "--min-liquidity",
        type=float,
        default=10000.0,
        help="Minimum market liquidity (default: 10000)",
    )
    parser.add_argument(
        "--limit", type=int, default=1000, help="Maximum markets to fetch (default: 1000)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output filename (default: resolved_STARTDATE_to_ENDDATE.json)",
    )

    args = parser.parse_args()

    # Generate default output filename
    if args.output is None:
        args.output = f"resolved_{args.start_date}_to_{args.end_date}.json"

    # Fetch and save
    fetcher = PolymarketHistoricalFetcher()
    markets = fetcher.fetch_markets(
        start_date=args.start_date,
        end_date=args.end_date,
        min_liquidity=args.min_liquidity,
        limit=args.limit,
    )

    if len(markets) > 0:
        fetcher.save_markets(markets, args.output)
    else:
        logger.warning("No markets fetched. Check your filters and API access.")


if __name__ == "__main__":
    main()
