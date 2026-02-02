"""Fundamentals Agent - Analyzes financial/economic data for prediction markets."""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from mcp_servers.fundamentals_server import (
    get_stock_data,
    get_earnings_data,
    get_economic_indicator,
)
from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage


class FundamentalsAgent(BaseAgent):
    """
    Fetches relevant financial and economic data based on market classification,
    then analyzes it using the fundamental-analysis skill.
    """

    # Map categories to relevant data-fetching strategies
    CATEGORY_DATA_MAP = {
        "Economics": {
            "indicators": ["FEDFUNDS", "CPIAUCSL", "UNRATE", "GDP"],
            "tickers": ["^GSPC", "^TNX"],
        },
        "Cryptocurrency": {
            "indicators": [],
            "tickers": ["BTC-USD", "ETH-USD"],
        },
        "Technology": {
            "indicators": [],
            "tickers": ["QQQ", "^IXIC"],
        },
    }

    def __init__(
        self,
        client: Optional[AnthropicClient] = None,
        storage: Optional[DataStorage] = None,
    ):
        super().__init__(name="fundamentals", client=client, storage=storage)

    def _fetch_data_for_category(
        self,
        category: str,
        keywords: List[str],
    ) -> Dict[str, Any]:
        """Fetch relevant data based on market category."""
        data = {"category": category, "indicators": {}, "stocks": {}}

        config = self.CATEGORY_DATA_MAP.get(category, {})

        # Fetch economic indicators
        for series_id in config.get("indicators", []):
            try:
                raw = get_economic_indicator(series_id, observation_count=6)
                data["indicators"][series_id] = json.loads(raw)
            except Exception as e:
                self.logger.warning(f"Failed to fetch indicator {series_id}: {e}")

        # Fetch stock/index data
        for ticker in config.get("tickers", []):
            try:
                raw = get_stock_data(ticker, period="1mo")
                data["stocks"][ticker] = json.loads(raw)
            except Exception as e:
                self.logger.warning(f"Failed to fetch ticker {ticker}: {e}")

        # Try to extract tickers from keywords
        for kw in keywords:
            kw_upper = kw.upper()
            if len(kw_upper) <= 5 and kw_upper.isalpha() and kw_upper not in data["stocks"]:
                try:
                    raw = get_stock_data(kw_upper, period="1mo")
                    parsed = json.loads(raw)
                    if "error" not in parsed:
                        data["stocks"][kw_upper] = parsed
                except Exception:
                    pass

        return data

    def _analyze_fundamentals(
        self,
        market_question: str,
        market_price: float,
        category: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze fundamentals using the fundamental-analysis skill."""
        # Trim data to avoid hitting token limits
        trimmed_data = {"category": category}

        # Summarize indicators
        for series_id, indicator in data.get("indicators", {}).items():
            obs = indicator.get("observations", [])[:3]
            trimmed_data[f"indicator_{series_id}"] = {
                "info": indicator.get("info", {}),
                "recent_observations": obs,
            }

        # Summarize stock data
        for ticker, stock in data.get("stocks", {}).items():
            trimmed_data[f"stock_{ticker}"] = {
                "name": stock.get("name"),
                "current_price": stock.get("current_price"),
                "pe_ratio": stock.get("pe_ratio"),
                "market_cap": stock.get("market_cap"),
                "52_week_high": stock.get("52_week_high"),
                "52_week_low": stock.get("52_week_low"),
                "revenue_growth": stock.get("revenue_growth"),
            }

        context = json.dumps({
            "market_question": market_question,
            "current_market_price": market_price,
            "data": trimmed_data,
        }, indent=2)

        response_text = self._invoke_skill(
            "fundamental-analysis",
            f"Analyze this financial data relative to the prediction market question:\n\n{context}",
            max_tokens=3072,
            temperature=0.3,
        )

        return self._parse_json_response(response_text)

    def run(
        self,
        market_question: str,
        market_id: str = "",
        market_price: float = 0.5,
        category: str = "Other",
        keywords: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run fundamental analysis for a market.

        Args:
            market_question: The prediction market question
            market_id: Market identifier
            market_price: Current YES price (0-1)
            category: Market category from event-classification
            keywords: Relevant keywords from classification

        Returns:
            Dict with fundamental analysis results
        """
        self.logger.info(f"Running fundamental analysis for market: {market_id}")

        # Fetch relevant data
        data = self._fetch_data_for_category(category, keywords or [])

        has_data = bool(data.get("indicators")) or bool(data.get("stocks"))
        if not has_data:
            result = {
                "market_id": market_id,
                "assessment": "neutral",
                "confidence": "low",
                "note": f"No relevant fundamental data available for category: {category}",
            }
            self._save_decision(market_id, {
                "decision": "no_data",
                "reasoning": "No relevant fundamental data available",
                "metadata": result,
            })
            return result

        # Analyze
        try:
            analysis = self._analyze_fundamentals(market_question, market_price, category, data)
        except Exception as e:
            self.logger.error(f"Fundamental analysis failed: {e}")
            analysis = {
                "assessment": "neutral",
                "confidence": "low",
                "error": str(e),
            }

        result = {
            "market_id": market_id,
            **analysis,
        }

        self._save_decision(market_id, {
            "decision": "fundamentals_analyzed",
            "reasoning": analysis.get("reasoning", ""),
            "metadata": result,
        })

        return result
