"""Fundamentals MCP Server - Financial data from yfinance, SEC EDGAR, FRED.

Provides tools to:
- Get stock price data and fundamentals via yfinance
- Fetch company filings from SEC EDGAR
- Pull macroeconomic indicators from FRED
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
import yfinance as yf
from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger("calibramark.mcp.fundamentals")

# SEC EDGAR public API (no key required, just User-Agent)
SEC_EDGAR_API = "https://efts.sec.gov/LATEST/search-index"
SEC_EDGAR_FILINGS = "https://data.sec.gov"

# FRED API
FRED_API = "https://api.stlouisfed.org/fred"

server = FastMCP(
    name="fundamentals",
    instructions="Financial fundamentals data provider. Stock data, SEC filings, and economic indicators.",
)


# ---------------------------------------------------------------------------
# yfinance tools
# ---------------------------------------------------------------------------

@server.tool(description="Get stock price data and key fundamentals for a ticker")
def get_stock_data(
    ticker: str,
    period: str = "1mo",
) -> str:
    """
    Get stock price data and fundamentals.

    Args:
        ticker: Stock ticker symbol (e.g., AAPL, MSFT)
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Get price history
        hist = stock.history(period=period)

        price_data = []
        if not hist.empty:
            for date, row in hist.tail(30).iterrows():
                price_data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(row["Open"], 2),
                    "high": round(row["High"], 2),
                    "low": round(row["Low"], 2),
                    "close": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                })

        return json.dumps({
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName", ticker),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "dividend_yield": info.get("dividendYield"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
            "beta": info.get("beta"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_date": str(info.get("earningsDate", "")),
            "price_history": price_data,
        }, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": f"Failed to fetch data for {ticker}: {e}"})


@server.tool(description="Get earnings data and upcoming earnings dates")
def get_earnings_data(ticker: str) -> str:
    """
    Get earnings history and upcoming earnings for a stock.

    Args:
        ticker: Stock ticker symbol
    """
    try:
        stock = yf.Ticker(ticker)

        # Get earnings history
        earnings = stock.earnings_history
        earnings_data = []

        if earnings is not None and not earnings.empty:
            for _, row in earnings.tail(8).iterrows():
                earnings_data.append({
                    "date": str(row.name) if hasattr(row, "name") else "",
                    "eps_estimate": row.get("epsEstimate"),
                    "eps_actual": row.get("epsActual"),
                    "surprise_pct": row.get("surprisePercent"),
                })

        # Get next earnings date
        info = stock.info
        next_earnings = info.get("earningsDate")

        return json.dumps({
            "ticker": ticker,
            "next_earnings_date": str(next_earnings) if next_earnings else None,
            "earnings_history": earnings_data,
        }, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": f"Failed to fetch earnings for {ticker}: {e}"})


# ---------------------------------------------------------------------------
# SEC EDGAR tools
# ---------------------------------------------------------------------------

@server.tool(description="Search SEC EDGAR for company filings")
def get_company_filings(
    ticker: str,
    filing_type: str = "10-K",
    limit: int = 5,
) -> str:
    """
    Get recent SEC filings for a company.

    Args:
        ticker: Stock ticker symbol
        filing_type: Filing type (10-K, 10-Q, 8-K, etc.)
        limit: Maximum number of filings
    """
    try:
        # Use EDGAR full-text search
        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": ticker,
            "forms": filing_type,
            "dateRange": "custom",
            "startdt": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            "enddt": datetime.now().strftime("%Y-%m-%d"),
        }
        headers = {
            "User-Agent": "CalibraMark research@calibramark.com",
            "Accept": "application/json",
        }

        response = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params,
            headers=headers,
            timeout=15,
        )

        if response.status_code == 200:
            data = response.json()
            filings = []
            for hit in data.get("hits", {}).get("hits", [])[:limit]:
                source = hit.get("_source", {})
                filings.append({
                    "form_type": source.get("form_type"),
                    "filed_date": source.get("file_date"),
                    "entity_name": source.get("entity_name"),
                    "file_number": source.get("file_num"),
                })
            return json.dumps({"ticker": ticker, "filings": filings}, indent=2)
        else:
            # Fallback: use yfinance for basic info
            stock = yf.Ticker(ticker)
            info = stock.info
            return json.dumps({
                "ticker": ticker,
                "note": "SEC EDGAR search unavailable, showing yfinance data",
                "company_name": info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "full_time_employees": info.get("fullTimeEmployees"),
            }, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to fetch filings for {ticker}: {e}"})


# ---------------------------------------------------------------------------
# FRED / Macro tools
# ---------------------------------------------------------------------------

@server.tool(description="Get a macroeconomic indicator from FRED")
def get_economic_indicator(
    series_id: str,
    observation_count: int = 12,
) -> str:
    """
    Get economic indicator data from FRED (Federal Reserve Economic Data).

    Common series IDs:
    - GDP: Gross Domestic Product
    - UNRATE: Unemployment Rate
    - CPIAUCSL: Consumer Price Index
    - FEDFUNDS: Federal Funds Rate
    - DGS10: 10-Year Treasury Yield
    - SP500: S&P 500 Index
    - DEXUSEU: USD/EUR Exchange Rate
    - M2SL: M2 Money Supply
    - MORTGAGE30US: 30-Year Mortgage Rate
    - HOUST: Housing Starts

    Args:
        series_id: FRED series ID (e.g., GDP, UNRATE, CPIAUCSL)
        observation_count: Number of recent observations
    """
    import os

    fred_key = os.environ.get("FRED_API_KEY")

    if fred_key:
        try:
            params = {
                "series_id": series_id,
                "api_key": fred_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": observation_count,
            }

            response = requests.get(
                f"{FRED_API}/series/observations",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            observations = []
            for obs in data.get("observations", []):
                observations.append({
                    "date": obs.get("date"),
                    "value": obs.get("value"),
                })

            # Get series info
            info_params = {
                "series_id": series_id,
                "api_key": fred_key,
                "file_type": "json",
            }
            info_response = requests.get(
                f"{FRED_API}/series",
                params=info_params,
                timeout=15,
            )
            series_info = {}
            if info_response.status_code == 200:
                serieses = info_response.json().get("seriess", [])
                if serieses:
                    series_info = {
                        "title": serieses[0].get("title"),
                        "frequency": serieses[0].get("frequency"),
                        "units": serieses[0].get("units"),
                    }

            return json.dumps({
                "series_id": series_id,
                "info": series_info,
                "observations": observations,
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": f"FRED API error: {e}"})

    else:
        # Fallback: use yfinance for common indicators
        fallback_tickers = {
            "SP500": "^GSPC",
            "DGS10": "^TNX",
            "FEDFUNDS": "^IRX",
        }

        if series_id in fallback_tickers:
            return get_stock_data(fallback_tickers[series_id], period="3mo")

        return json.dumps({
            "error": "FRED_API_KEY not set. Set it in .env for economic data.",
            "hint": "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html",
            "common_series": {
                "GDP": "Gross Domestic Product",
                "UNRATE": "Unemployment Rate",
                "CPIAUCSL": "Consumer Price Index",
                "FEDFUNDS": "Federal Funds Rate",
                "DGS10": "10-Year Treasury Yield",
            },
        })


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@server.resource("fundamentals://indicators")
def list_indicators() -> str:
    """List common FRED economic indicators."""
    return json.dumps({
        "GDP": "Gross Domestic Product",
        "UNRATE": "Unemployment Rate",
        "CPIAUCSL": "Consumer Price Index (All Urban Consumers)",
        "FEDFUNDS": "Federal Funds Effective Rate",
        "DGS10": "10-Year Treasury Constant Maturity Rate",
        "DGS2": "2-Year Treasury Constant Maturity Rate",
        "SP500": "S&P 500 Index",
        "DEXUSEU": "US Dollar / Euro Exchange Rate",
        "M2SL": "M2 Money Supply",
        "MORTGAGE30US": "30-Year Fixed Rate Mortgage Average",
        "HOUST": "Housing Starts Total",
        "PAYEMS": "Total Nonfarm Payrolls",
        "RSAFS": "Advance Retail Sales",
        "DCOILWTICO": "Crude Oil Prices (WTI)",
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.run(transport="stdio")
