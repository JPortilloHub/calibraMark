"""Calibration Agent - The critical gatekeeper for trade decisions."""

import json
import logging
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from config import get_settings, get_risk_limits
from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage


class CalibrationAgent(BaseAgent):
    """
    The gatekeeper agent that synthesizes all inputs and makes the
    final TRADE / NO_TRADE decision.

    Pipeline:
    1. Synthesize news sentiment + fundamental analysis + market data
    2. Invoke probability-calibration skill -> estimated probability
    3. Calculate expected value vs market price
    4. If EV >= threshold, invoke kelly-criterion skill -> position size
    5. Output: TRADE or NO_TRADE with full reasoning
    """

    def __init__(
        self,
        client: Optional[AnthropicClient] = None,
        storage: Optional[DataStorage] = None,
    ):
        super().__init__(name="calibration", client=client, storage=storage)
        self.settings = get_settings()
        self.risk_limits = get_risk_limits()

    def _estimate_probability(
        self,
        market_question: str,
        market_price: float,
        news_sentiment: Dict[str, Any],
        fundamentals: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke probability-calibration skill."""
        context = json.dumps({
            "market_question": market_question,
            "current_market_price": market_price,
            "market_category": classification.get("primary_category", "Other"),
            "news_sentiment": {
                "score": news_sentiment.get("sentiment_score", 0),
                "confidence": news_sentiment.get("confidence", "low"),
                "key_events": news_sentiment.get("key_events", []),
                "article_count": news_sentiment.get("article_count", 0),
            },
            "fundamentals": {
                "assessment": fundamentals.get("assessment", "neutral"),
                "confidence": fundamentals.get("confidence", "low"),
                "key_metrics": fundamentals.get("key_metrics", []),
                "probability_adjustment": fundamentals.get("probability_adjustment", {}),
            },
        }, indent=2)

        response_text = self._invoke_skill(
            "probability-calibration",
            f"Estimate the probability for this prediction market:\n\n{context}",
            max_tokens=4096,
            temperature=0.5,
        )

        return self._parse_json_response(response_text)

    def _calculate_kelly(
        self,
        agent_probability: float,
        market_price: float,
        bankroll: float,
    ) -> Dict[str, Any]:
        """Invoke kelly-criterion skill."""
        # Determine side
        if agent_probability > market_price:
            side = "YES"
            edge = agent_probability - market_price
        else:
            side = "NO"
            edge = market_price - agent_probability

        context = json.dumps({
            "agent_probability": agent_probability,
            "market_price": market_price,
            "side": side,
            "edge": edge,
            "bankroll": bankroll,
            "risk_limits": {
                "max_position_size": self.risk_limits.max_position_size_usd,
                "max_bankroll_fraction": 0.10,
                "kelly_fraction": self.risk_limits.kelly_fraction,
                "min_edge_threshold": self.risk_limits.min_edge_threshold,
            },
        }, indent=2)

        response_text = self._invoke_skill(
            "kelly-criterion",
            f"Calculate optimal position size:\n\n{context}",
            max_tokens=2048,
            temperature=0.2,
        )

        result = self._parse_json_response(response_text)
        result["side"] = side
        return result

    def run(
        self,
        market_id: str = "",
        market_question: str = "",
        market_price: float = 0.5,
        news_sentiment: Optional[Dict[str, Any]] = None,
        fundamentals: Optional[Dict[str, Any]] = None,
        classification: Optional[Dict[str, Any]] = None,
        bankroll: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run calibration pipeline: estimate probability -> calculate EV -> size position.

        Args:
            market_id: Market identifier
            market_question: The market question
            market_price: Current YES price (0-1)
            news_sentiment: Output from NewsSentimentAgent
            fundamentals: Output from FundamentalsAgent
            classification: Output from event-classification
            bankroll: Current bankroll (defaults to paper trading bankroll)

        Returns:
            Dict with TRADE or NO_TRADE decision and full reasoning
        """
        self.logger.info(f"Running calibration for market: {market_id}")

        if bankroll is None:
            bankroll = self.settings.paper_trading_starting_bankroll

        news_sentiment = news_sentiment or {}
        fundamentals = fundamentals or {}
        classification = classification or {"primary_category": "Other"}

        # Step 1: Estimate probability
        try:
            prob_estimate = self._estimate_probability(
                market_question, market_price, news_sentiment, fundamentals, classification
            )
        except Exception as e:
            self.logger.error(f"Probability estimation failed: {e}")
            result = {
                "market_id": market_id,
                "decision": "NO_TRADE",
                "reason": f"Probability estimation failed: {e}",
            }
            self._save_decision(market_id, {"decision": "NO_TRADE", "reasoning": str(e), "metadata": result})
            return result

        agent_probability = prob_estimate.get("probability", 0.5)
        confidence = prob_estimate.get("confidence_level", "low")

        # Step 2: Calculate edge
        if agent_probability > market_price:
            edge = agent_probability - market_price
            side = "YES"
        else:
            edge = market_price - agent_probability
            side = "NO"

        self.logger.info(
            f"Agent probability: {agent_probability:.2%}, Market: {market_price:.2%}, "
            f"Edge: {edge:.2%}, Side: {side}"
        )

        # Step 3: Check minimum edge
        edge_valid, edge_reason = self.risk_limits.validate_edge(edge)
        if not edge_valid:
            result = {
                "market_id": market_id,
                "decision": "NO_TRADE",
                "reason": edge_reason,
                "agent_probability": agent_probability,
                "market_price": market_price,
                "edge": edge,
                "side": side,
                "probability_estimate": prob_estimate,
            }
            self._save_decision(market_id, {"decision": "NO_TRADE", "reasoning": edge_reason, "metadata": result})
            self.logger.info(f"NO_TRADE: {edge_reason}")
            return result

        # Step 4: Calculate position size using Kelly
        try:
            kelly_result = self._calculate_kelly(agent_probability, market_price, bankroll)
        except Exception as e:
            self.logger.error(f"Kelly calculation failed: {e}")
            result = {
                "market_id": market_id,
                "decision": "NO_TRADE",
                "reason": f"Kelly calculation failed: {e}",
                "agent_probability": agent_probability,
                "edge": edge,
            }
            self._save_decision(market_id, {"decision": "NO_TRADE", "reasoning": str(e), "metadata": result})
            return result

        position_size = kelly_result.get("final_position_size", 0)
        recommendation = kelly_result.get("recommendation", "NO_TRADE")

        if recommendation == "NO_TRADE" or position_size <= 0:
            result = {
                "market_id": market_id,
                "decision": "NO_TRADE",
                "reason": "Kelly criterion recommends no trade",
                "agent_probability": agent_probability,
                "market_price": market_price,
                "edge": edge,
                "side": side,
                "kelly_result": kelly_result,
                "probability_estimate": prob_estimate,
            }
            self._save_decision(market_id, {"decision": "NO_TRADE", "reasoning": "Kelly: no trade", "metadata": result})
            self.logger.info("NO_TRADE: Kelly criterion recommends no trade")
            return result

        # Step 5: Validate position against risk limits
        pos_valid, pos_reason = self.risk_limits.validate_position_size(position_size, bankroll)
        if not pos_valid:
            # Cap position rather than reject
            position_size = min(
                self.risk_limits.max_position_size_usd,
                bankroll * 0.10,
            )
            self.logger.warning(f"Position capped: {pos_reason}")

        # TRADE decision
        result = {
            "market_id": market_id,
            "market_question": market_question,
            "decision": "TRADE",
            "side": side,
            "agent_probability": agent_probability,
            "market_price": market_price,
            "edge": edge,
            "position_size": position_size,
            "expected_value": edge * position_size,
            "confidence": confidence,
            "probability_estimate": prob_estimate,
            "kelly_result": kelly_result,
        }

        self._save_decision(market_id, {
            "decision": "TRADE",
            "reasoning": f"{side} @ {market_price:.2%}, edge={edge:.2%}, size=${position_size:.2f}",
            "metadata": result,
        })

        self.logger.info(
            f"TRADE: {side} @ {market_price:.2%}, edge={edge:.2%}, size=${position_size:.2f}"
        )

        return result
