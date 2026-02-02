"""News MCP Server - RSS feed aggregation and news search.

Provides tools to:
- Search news by keywords across multiple RSS sources
- Get recent headlines
- Filter news by relevance to prediction markets
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import feedparser
import requests
from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger("calibramark.mcp.news")

server = FastMCP(
    name="news",
    instructions="News aggregation server. Searches RSS feeds for articles relevant to prediction markets.",
)

# ---------------------------------------------------------------------------
# RSS Feed Sources
# ---------------------------------------------------------------------------

RSS_FEEDS = {
    # Major wire services
    "reuters_world": "https://feeds.reuters.com/Reuters/worldNews",
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "reuters_politics": "https://feeds.reuters.com/Reuters/PoliticsNews",
    "reuters_tech": "https://feeds.reuters.com/reuters/technologyNews",
    "ap_top": "https://rsshub.app/apnews/topics/apf-topnews",
    # US news
    "nyt_world": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "nyt_politics": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "nyt_business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "nyt_tech": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    # Finance
    "cnbc_top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories",
    # Tech
    "techcrunch": "https://techcrunch.com/feed/",
    "ars_tech": "https://feeds.arstechnica.com/arstechnica/index",
    # Science
    "nature": "https://www.nature.com/nature.rss",
    # Crypto
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
}

# Source credibility tiers
SOURCE_CREDIBILITY = {
    "reuters": "tier_1",
    "ap": "tier_1",
    "nyt": "tier_1",
    "bbc": "tier_1",
    "cnbc": "tier_2",
    "marketwatch": "tier_2",
    "techcrunch": "tier_2",
    "ars_tech": "tier_2",
    "nature": "tier_1",
    "coindesk": "tier_2",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _parse_feed(feed_url: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """Parse an RSS feed and return articles."""
    try:
        feed = feedparser.parse(feed_url)
        articles = []

        for entry in feed.entries[:20]:  # Limit per feed
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).isoformat()
                except (TypeError, ValueError):
                    published = entry.get("published")

            articles.append({
                "title": entry.get("title", ""),
                "summary": _clean_html(entry.get("summary", "")),
                "link": entry.get("link", ""),
                "published": published,
                "source": feed.feed.get("title", "Unknown"),
            })

        return articles

    except Exception as e:
        logger.debug(f"Error parsing feed {feed_url}: {e}")
        return []


def _clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:500]  # Limit length


def _matches_keywords(article: Dict, keywords: List[str]) -> bool:
    """Check if article matches any keyword."""
    text = f"{article['title']} {article['summary']}".lower()
    return any(kw.lower() in text for kw in keywords)


def _get_credibility(source: str) -> str:
    """Get credibility tier for a source."""
    source_lower = source.lower()
    for key, tier in SOURCE_CREDIBILITY.items():
        if key in source_lower:
            return tier
    return "tier_3"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@server.tool(description="Search news articles by keywords across multiple RSS sources")
def search_news(
    keywords: str,
    days_back: int = 7,
    max_results: int = 20,
) -> str:
    """
    Search news articles by keywords.

    Args:
        keywords: Comma-separated keywords to search for
        days_back: How many days back to search
        max_results: Maximum number of results to return
    """
    keyword_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]

    if not keyword_list:
        return json.dumps({"error": "No keywords provided"})

    cutoff_date = datetime.now() - timedelta(days=days_back)
    all_articles = []

    for feed_name, feed_url in RSS_FEEDS.items():
        articles = _parse_feed(feed_url)

        for article in articles:
            if _matches_keywords(article, keyword_list):
                article["credibility"] = _get_credibility(article["source"])
                article["feed_name"] = feed_name
                all_articles.append(article)

    # Deduplicate by title similarity
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"].lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    # Sort by credibility tier then recency
    tier_order = {"tier_1": 0, "tier_2": 1, "tier_3": 2}
    unique_articles.sort(key=lambda a: tier_order.get(a.get("credibility", "tier_3"), 3))

    results = unique_articles[:max_results]

    return json.dumps({
        "keywords": keyword_list,
        "days_back": days_back,
        "total_found": len(unique_articles),
        "returned": len(results),
        "articles": results,
    }, indent=2)


@server.tool(description="Get recent breaking news headlines from top sources")
def get_recent_news(
    max_results: int = 15,
    category: str = "all",
) -> str:
    """
    Get recent news headlines.

    Args:
        max_results: Maximum number of results
        category: Filter by category (all, politics, business, tech, science, crypto)
    """
    # Map categories to feeds
    category_feeds = {
        "all": list(RSS_FEEDS.keys()),
        "politics": ["reuters_politics", "nyt_politics", "reuters_world"],
        "business": ["reuters_business", "nyt_business", "cnbc_top", "marketwatch"],
        "tech": ["reuters_tech", "nyt_tech", "techcrunch", "ars_tech"],
        "science": ["nature"],
        "crypto": ["coindesk"],
    }

    feed_names = category_feeds.get(category, category_feeds["all"])
    all_articles = []

    for feed_name in feed_names:
        if feed_name in RSS_FEEDS:
            articles = _parse_feed(RSS_FEEDS[feed_name])
            for article in articles:
                article["credibility"] = _get_credibility(article["source"])
                article["feed_name"] = feed_name
            all_articles.extend(articles)

    # Deduplicate
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"].lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    results = unique_articles[:max_results]

    return json.dumps({
        "category": category,
        "total_found": len(unique_articles),
        "returned": len(results),
        "articles": results,
    }, indent=2)


@server.tool(description="Get news relevant to a specific prediction market")
def get_market_news(
    market_question: str,
    max_results: int = 10,
) -> str:
    """
    Get news articles relevant to a specific prediction market question.

    Automatically extracts keywords from the question and searches relevant feeds.

    Args:
        market_question: The prediction market question
        max_results: Maximum number of results
    """
    # Extract keywords from the question (skip common words)
    stop_words = {
        "will", "the", "be", "is", "in", "by", "to", "of", "a", "an", "on",
        "for", "and", "or", "at", "from", "with", "that", "this", "than",
        "before", "after", "during", "over", "under", "above", "below",
        "yes", "no", "would", "could", "should", "does", "do", "did",
        "has", "have", "had", "was", "were", "been", "being",
    }

    words = re.findall(r"\b[a-zA-Z]{3,}\b", market_question)
    keywords = [w for w in words if w.lower() not in stop_words]

    # Take the most specific keywords (longer words first)
    keywords.sort(key=len, reverse=True)
    keywords = keywords[:5]

    if not keywords:
        return json.dumps({"error": "Could not extract keywords from question"})

    # Search with extracted keywords
    return search_news(
        keywords=", ".join(keywords),
        days_back=7,
        max_results=max_results,
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@server.resource("news://sources")
def get_news_sources() -> str:
    """List all configured RSS feed sources."""
    sources = []
    for name, url in RSS_FEEDS.items():
        sources.append({
            "name": name,
            "url": url,
            "credibility": _get_credibility(name),
        })
    return json.dumps(sources, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.run(transport="stdio")
