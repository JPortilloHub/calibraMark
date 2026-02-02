"""OpenBB MCP Server - Unified financial data interface.

Provides tools to:
- Query market data through OpenBB's unified API
- Get crypto data
- Access economic calendars
- Pull ETF data
"""

import json
import logging
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger("calibramark.mcp.openbb")

server = FastMCP(
    name="openbb",
    instructions="OpenBB financial data provider. Unified interface to multiple data sources.",
)


def _safe_openbb_call(func, *args, **kwargs) -> Any:
    """Safely call an OpenBB function and handle errors."""
    try:
        from openbb import obb
        result = func(obb, *args, **kwargs)
        # Convert OpenBB result to dict/list
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if hasattr(result, "results"):
            results = result.results
            if hasattr(results, "to_dict"):
                return results.to_dict()
            if isinstance(results, list):
                return [r.model_dump() if hasattr(r, "model_dump") else str(r) for r in results]
            return str(results)
        return str(result)
    except ImportError:
        return {"error": "OpenBB not properly configured. Run: pip install openbb"}
    except Exception as e:
        return {"error": f"OpenBB error: {e}"}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@server.tool(description="Get historical stock/equity price data via OpenBB")
def get_equity_price(
    symbol: str,
    provider: str = "yfinance",
    period: str = "1mo",
) -> str:
    """
    Get equity price data through OpenBB.

    Args:
        symbol: Stock ticker symbol (e.g., AAPL, MSFT)
        provider: Data provider (yfinance, polygon, intrinio, fmp)
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y)
    """
    # Map period to start_date
    from datetime import datetime, timedelta
    period_days = {
        "1d": 1, "5d": 5, "1mo": 30, "3mo": 90,
        "6mo": 180, "1y": 365, "2y": 730,
    }
    days = period_days.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    def _fetch(obb, symbol=symbol, start_date=start_date, provider=provider):
        return obb.equity.price.historical(
            symbol=symbol,
            start_date=start_date,
            provider=provider,
        )

    result = _safe_openbb_call(_fetch)
    return json.dumps({"symbol": symbol, "provider": provider, "data": result}, indent=2, default=str)


@server.tool(description="Get cryptocurrency price data")
def get_crypto_price(
    symbol: str,
    provider: str = "yfinance",
    period: str = "1mo",
) -> str:
    """
    Get cryptocurrency price data.

    Args:
        symbol: Crypto symbol (e.g., BTC-USD, ETH-USD)
        provider: Data provider (yfinance, polygon)
        period: Time period
    """
    from datetime import datetime, timedelta
    period_days = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
    days = period_days.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    def _fetch(obb, symbol=symbol, start_date=start_date, provider=provider):
        return obb.crypto.price.historical(
            symbol=symbol,
            start_date=start_date,
            provider=provider,
        )

    result = _safe_openbb_call(_fetch)
    return json.dumps({"symbol": symbol, "provider": provider, "data": result}, indent=2, default=str)


@server.tool(description="Get economic calendar events")
def get_economic_calendar(
    provider: str = "fmp",
    days_ahead: int = 7,
) -> str:
    """
    Get upcoming economic events.

    Args:
        provider: Data provider (fmp, tradingeconomics)
        days_ahead: Number of days ahead to look
    """
    from datetime import datetime, timedelta
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    def _fetch(obb, start_date=start_date, end_date=end_date, provider=provider):
        return obb.economy.calendar(
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )

    result = _safe_openbb_call(_fetch)
    return json.dumps({"days_ahead": days_ahead, "data": result}, indent=2, default=str)


@server.tool(description="Get broad market overview (indices, sectors)")
def get_market_overview() -> str:
    """
    Get a broad market overview including major indices.
    Uses yfinance as a reliable fallback.
    """
    import yfinance as yf

    indices = {
        "S&P 500": "^GSPC",
        "Dow Jones": "^DJI",
        "NASDAQ": "^IXIC",
        "Russell 2000": "^RUT",
        "VIX": "^VIX",
        "10Y Treasury": "^TNX",
        "US Dollar Index": "DX-Y.NYB",
        "Gold": "GC=F",
        "Oil (WTI)": "CL=F",
        "Bitcoin": "BTC-USD",
        "Ethereum": "ETH-USD",
    }

    overview = {}
    for name, ticker in indices.items():
        try:
            data = yf.Ticker(ticker)
            info = data.info
            hist = data.history(period="2d")

            current = info.get("regularMarketPrice") or info.get("currentPrice")
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

            if current and prev_close:
                change_pct = ((current - prev_close) / prev_close) * 100
            else:
                change_pct = None

            # Fallback to history if info doesn't have prices
            if current is None and not hist.empty:
                current = round(hist["Close"].iloc[-1], 2)
                if len(hist) > 1:
                    prev = hist["Close"].iloc[-2]
                    change_pct = ((current - prev) / prev) * 100

            overview[name] = {
                "ticker": ticker,
                "price": round(current, 2) if current else None,
                "change_pct": round(change_pct, 2) if change_pct else None,
            }
        except Exception as e:
            overview[name] = {"ticker": ticker, "error": str(e)}

    return json.dumps({"market_overview": overview}, indent=2)


@server.tool(description="Get ETF holdings and performance data")
def get_etf_data(
    symbol: str,
) -> str:
    """
    Get ETF information and recent performance.

    Args:
        symbol: ETF symbol (e.g., SPY, QQQ, IWM, GLD)
    """
    import yfinance as yf

    try:
        etf = yf.Ticker(symbol)
        info = etf.info
        hist = etf.history(period="3mo")

        price_data = []
        if not hist.empty:
            for date, row in hist.tail(10).iterrows():
                price_data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "close": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                })

        return json.dumps({
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName", symbol),
            "category": info.get("category"),
            "total_assets": info.get("totalAssets"),
            "expense_ratio": info.get("annualReportExpenseRatio"),
            "ytd_return": info.get("ytdReturn"),
            "three_year_return": info.get("threeYearAverageReturn"),
            "five_year_return": info.get("fiveYearAverageReturn"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "recent_prices": price_data,
        }, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": f"Failed to fetch ETF data for {symbol}: {e}"})


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@server.resource("openbb://providers")
def list_providers() -> str:
    """List available OpenBB data providers."""
    return json.dumps({
        "equity_price": ["yfinance", "polygon", "intrinio", "fmp", "tiingo"],
        "crypto_price": ["yfinance", "polygon"],
        "economic_calendar": ["fmp", "tradingeconomics"],
        "news": ["benzinga", "tiingo", "intrinio"],
        "note": "Provider availability depends on API keys configured in OpenBB",
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.run(transport="stdio")
