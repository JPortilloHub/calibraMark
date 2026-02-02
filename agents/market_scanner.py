"""Market Scanner Agent - Scans Polymarket for tradeable opportunities."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from config import get_settings
from mcp_servers.polymarket_server import get_active_markets, get_market_details
from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage


class MarketScannerAgent(BaseAgent):
    """
    Scans Polymarket for markets matching our criteria, then classifies
    each market by domain using the event-classification skill.
    """

    def __init__(
        self,
        client: Optional[AnthropicClient] = None,
        storage: Optional[DataStorage] = None,
    ):
        super().__init__(name="market_scanner", client=client, storage=storage)
        self.settings = get_settings()

    def _fetch_markets(self) -> List[Dict[str, Any]]:
        """Fetch active markets from Polymarket."""
        self.logger.info("Fetching active markets from Polymarket...")
        raw = get_active_markets(
            min_liquidity=self.settings.min_market_liquidity,
            limit=100,
        )
        data = json.loads(raw)
        markets = data.get("markets", [])
        self.logger.info(f"Fetched {len(markets)} markets above ${self.settings.min_market_liquidity} liquidity")
        return markets

    def _filter_by_resolution_date(self, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter markets by resolution date window."""
        now = datetime.now()
        min_date = now + timedelta(days=self.settings.min_days_until_resolution)
        max_date = now + timedelta(days=self.settings.max_days_until_resolution)

        filtered = []
        for market in markets:
            end_date_str = market.get("end_date")
            if not end_date_str:
                continue
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                if min_date <= end_date <= max_date:
                    filtered.append(market)
            except (ValueError, TypeError):
                continue

        self.logger.info(
            f"Filtered to {len(filtered)} markets resolving within "
            f"{self.settings.min_days_until_resolution}-{self.settings.max_days_until_resolution} days"
        )
        return filtered

    def _classify_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a market using the event-classification skill."""
        context = json.dumps({
            "market_question": market.get("question", ""),
            "description": market.get("description", ""),
            "tags": market.get("tags", []),
        }, indent=2)

        try:
            response_text = self._invoke_skill(
                "event-classification",
                f"Classify this prediction market:\n\n{context}",
                max_tokens=2048,
                temperature=0.3,
            )
            classification = self._parse_json_response(response_text)
            return classification
        except Exception as e:
            self.logger.warning(f"Failed to classify market {market.get('id')}: {e}")
            return {
                "primary_category": "Other",
                "confidence": "low",
                "error": str(e),
            }

    def _snapshot_market(self, market: Dict[str, Any]) -> None:
        """Save a market snapshot to storage."""
        outcomes = market.get("outcomes", [])
        yes_price = 0.5
        no_price = 0.5
        if isinstance(outcomes, list) and len(outcomes) >= 2:
            # Outcomes may be strings or dicts
            if isinstance(outcomes[0], dict):
                yes_price = float(outcomes[0].get("price", 0.5))
                no_price = float(outcomes[1].get("price", 0.5))

        self.storage.save_market_snapshot({
            "market_id": market.get("id", ""),
            "market_question": market.get("question", ""),
            "yes_price": yes_price,
            "no_price": no_price,
            "liquidity": market.get("liquidity"),
            "volume": market.get("volume"),
            "resolution_date": market.get("end_date"),
        })

    def run(
        self,
        classify: bool = True,
        max_to_classify: int = 20,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run market scan pipeline.

        Args:
            classify: Whether to classify markets using AI
            max_to_classify: Maximum number of markets to classify (API cost control)

        Returns:
            Dict with shortlisted markets and classifications
        """
        self.logger.info("Starting market scan...")

        # Fetch and filter
        markets = self._fetch_markets()
        filtered = self._filter_by_resolution_date(markets)

        # Sort by liquidity (highest first) and take top candidates
        filtered.sort(key=lambda m: m.get("liquidity", 0), reverse=True)
        candidates = filtered[:max_to_classify]

        # Snapshot and optionally classify
        shortlist = []
        for market in candidates:
            self._snapshot_market(market)

            entry = {
                "id": market.get("id"),
                "question": market.get("question"),
                "liquidity": market.get("liquidity"),
                "volume": market.get("volume"),
                "end_date": market.get("end_date"),
                "outcomes": market.get("outcomes", []),
                "tags": market.get("tags", []),
            }

            if classify:
                classification = self._classify_market(market)
                entry["classification"] = classification

            shortlist.append(entry)

        result = {
            "timestamp": datetime.now().isoformat(),
            "total_fetched": len(markets),
            "after_date_filter": len(filtered),
            "shortlisted": len(shortlist),
            "markets": shortlist,
        }

        self.logger.info(
            f"Scan complete: {len(markets)} fetched -> {len(filtered)} filtered -> {len(shortlist)} shortlisted"
        )

        return result
