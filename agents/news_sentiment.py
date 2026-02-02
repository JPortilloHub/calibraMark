"""News Sentiment Agent - Analyzes news sentiment for prediction markets."""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from mcp_servers.news_server import get_market_news
from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage


class NewsSentimentAgent(BaseAgent):
    """
    Fetches relevant news for a market and analyzes sentiment
    using the sentiment-analysis skill.
    """

    def __init__(
        self,
        client: Optional[AnthropicClient] = None,
        storage: Optional[DataStorage] = None,
    ):
        super().__init__(name="news_sentiment", client=client, storage=storage)

    def _fetch_news(self, market_question: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """Fetch relevant news for a market question."""
        self.logger.info(f"Fetching news for: {market_question[:80]}...")
        raw = get_market_news(
            market_question=market_question,
            max_results=15,
        )
        data = json.loads(raw)
        articles = data.get("articles", [])
        self.logger.info(f"Found {len(articles)} relevant articles")
        return articles

    def _analyze_sentiment(
        self,
        market_question: str,
        market_price: float,
        articles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyze sentiment using the sentiment-analysis skill."""
        # Format articles for the skill
        articles_summary = []
        for article in articles[:10]:  # Limit to 10 to control token usage
            articles_summary.append({
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "published": article.get("published", ""),
                "summary": article.get("summary", "")[:300],
                "credibility_tier": article.get("credibility_tier", "unknown"),
            })

        context = json.dumps({
            "market_question": market_question,
            "current_market_price": market_price,
            "articles": articles_summary,
        }, indent=2)

        response_text = self._invoke_skill(
            "sentiment-analysis",
            f"Analyze the sentiment of these news articles relative to this prediction market:\n\n{context}",
            max_tokens=3072,
            temperature=0.3,
        )

        return self._parse_json_response(response_text)

    def run(
        self,
        market_question: str,
        market_id: str = "",
        market_price: float = 0.5,
        days_back: int = 7,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run news sentiment analysis for a market.

        Args:
            market_question: The prediction market question
            market_id: Market identifier
            market_price: Current YES price (0-1)
            days_back: How many days of news to look back

        Returns:
            Dict with sentiment analysis results
        """
        self.logger.info(f"Running sentiment analysis for market: {market_id}")

        # Fetch news
        articles = self._fetch_news(market_question, days_back)

        if not articles:
            result = {
                "market_id": market_id,
                "sentiment_score": 0.0,
                "confidence": "low",
                "article_count": 0,
                "note": "No relevant news articles found",
            }
            self._save_decision(market_id, {
                "decision": "no_news",
                "reasoning": "No relevant articles found",
                "metadata": result,
            })
            return result

        # Analyze sentiment
        try:
            sentiment = self._analyze_sentiment(market_question, market_price, articles)
        except Exception as e:
            self.logger.error(f"Sentiment analysis failed: {e}")
            sentiment = {
                "sentiment_score": 0.0,
                "confidence": "low",
                "error": str(e),
            }

        result = {
            "market_id": market_id,
            "article_count": len(articles),
            **sentiment,
        }

        self._save_decision(market_id, {
            "decision": "sentiment_analyzed",
            "reasoning": sentiment.get("reasoning", ""),
            "metadata": result,
        })

        return result
