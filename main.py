"""CalibraMark - Main orchestrator for the prediction market analysis pipeline.

Runs the daily scan cycle:
1. Market Scanner -> Shortlist markets
2. For each market: News Sentiment -> Fundamentals -> Calibration -> Execution
3. Update Paper Trading Monitor
4. Generate daily report
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.market_scanner import MarketScannerAgent
from agents.news_sentiment import NewsSentimentAgent
from agents.fundamentals_agent import FundamentalsAgent
from agents.calibration_agent import CalibrationAgent
from agents.execution_agent import ExecutionAgent
from config import get_settings
from evaluation.paper_trading_monitor import PaperTradingMonitor
from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage
from utils.kill_switch import KillSwitch
from utils.logging_config import setup_logging


def run_pipeline(
    classify: bool = True,
    max_markets: int = 10,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run the full CalibraMark pipeline.

    Args:
        classify: Whether to classify markets using AI
        max_markets: Maximum markets to analyze
        dry_run: If True, skip execution step

    Returns:
        Pipeline results summary
    """
    settings = get_settings()
    settings.ensure_directories()

    logger = logging.getLogger("calibramark.pipeline")
    logger.info("=" * 60)
    logger.info("CalibraMark Pipeline Starting")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE PAPER TRADING'}")
    logger.info("=" * 60)

    # Check kill switch first
    kill_switch = KillSwitch()
    if kill_switch.is_active():
        state = kill_switch.get_state()
        logger.critical(f"Kill switch is ACTIVE: {state.get('reason', 'unknown')}")
        return {
            "status": "BLOCKED",
            "reason": f"Kill switch active: {state.get('reason')}",
            "timestamp": datetime.now().isoformat(),
        }

    # Initialize shared components
    client = AnthropicClient()
    storage = DataStorage()

    # Initialize agents
    scanner = MarketScannerAgent(client=client, storage=storage)
    news_agent = NewsSentimentAgent(client=client, storage=storage)
    fundamentals = FundamentalsAgent(client=client, storage=storage)
    calibration = CalibrationAgent(client=client, storage=storage)
    execution = ExecutionAgent(client=client, storage=storage, kill_switch=kill_switch)

    # Get current bankroll
    monitor = PaperTradingMonitor(storage=storage)
    bankroll = monitor.get_current_bankroll()

    results = {
        "timestamp": datetime.now().isoformat(),
        "bankroll": bankroll,
        "markets_scanned": 0,
        "markets_analyzed": 0,
        "trades_executed": 0,
        "trades_skipped": 0,
        "trade_details": [],
        "errors": [],
    }

    # Step 1: Scan markets
    logger.info("Step 1: Scanning markets...")
    try:
        scan_result = scanner.run(classify=classify, max_to_classify=max_markets)
        markets = scan_result.get("markets", [])
        results["markets_scanned"] = scan_result.get("total_fetched", 0)
    except Exception as e:
        logger.error(f"Market scan failed: {e}")
        results["errors"].append(f"Market scan failed: {e}")
        return results

    logger.info(f"Shortlisted {len(markets)} markets for analysis")

    # Step 2: Analyze each market
    for i, market in enumerate(markets):
        market_id = market.get("id", f"unknown_{i}")
        question = market.get("question", "Unknown market")
        classification = market.get("classification", {})
        category = classification.get("primary_category", "Other")
        keywords = classification.get("keywords", [])

        # Get market price
        outcomes = market.get("outcomes", [])
        market_price = 0.5
        if isinstance(outcomes, list) and len(outcomes) >= 1:
            if isinstance(outcomes[0], dict):
                market_price = float(outcomes[0].get("price", 0.5))
            elif isinstance(outcomes[0], str):
                # Sometimes outcomes are just strings like "Yes", "No"
                pass

        logger.info(f"\n--- Market {i+1}/{len(markets)}: {question[:80]} ---")
        logger.info(f"Category: {category}, Price: {market_price:.2%}")

        results["markets_analyzed"] += 1

        # 2a: News sentiment
        try:
            news_result = news_agent.run(
                market_question=question,
                market_id=market_id,
                market_price=market_price,
            )
        except Exception as e:
            logger.warning(f"News analysis failed for {market_id}: {e}")
            news_result = {}
            results["errors"].append(f"News failed for {market_id}: {e}")

        # 2b: Fundamentals
        try:
            fund_result = fundamentals.run(
                market_question=question,
                market_id=market_id,
                market_price=market_price,
                category=category,
                keywords=keywords,
            )
        except Exception as e:
            logger.warning(f"Fundamentals analysis failed for {market_id}: {e}")
            fund_result = {}
            results["errors"].append(f"Fundamentals failed for {market_id}: {e}")

        # 2c: Calibration (gatekeeper)
        try:
            trade_decision = calibration.run(
                market_id=market_id,
                market_question=question,
                market_price=market_price,
                news_sentiment=news_result,
                fundamentals=fund_result,
                classification=classification,
                bankroll=bankroll,
            )
        except Exception as e:
            logger.error(f"Calibration failed for {market_id}: {e}")
            results["errors"].append(f"Calibration failed for {market_id}: {e}")
            continue

        decision = trade_decision.get("decision", "NO_TRADE")

        if decision != "TRADE":
            logger.info(f"NO_TRADE: {trade_decision.get('reason', 'insufficient edge')}")
            results["trades_skipped"] += 1
            results["trade_details"].append({
                "market_id": market_id,
                "question": question[:100],
                "decision": "NO_TRADE",
                "reason": trade_decision.get("reason", ""),
                "edge": trade_decision.get("edge", 0),
            })
            continue

        # 2d: Execution
        if dry_run:
            logger.info(f"DRY RUN: Would trade {trade_decision.get('side')} ${trade_decision.get('position_size', 0):.2f}")
            results["trade_details"].append({
                "market_id": market_id,
                "question": question[:100],
                "decision": "TRADE (dry run)",
                "side": trade_decision.get("side"),
                "position_size": trade_decision.get("position_size"),
                "edge": trade_decision.get("edge"),
            })
            continue

        try:
            exec_result = execution.run(
                trade_decision=trade_decision,
                liquidity=market.get("liquidity", 50000),
            )
        except Exception as e:
            logger.error(f"Execution failed for {market_id}: {e}")
            results["errors"].append(f"Execution failed for {market_id}: {e}")
            continue

        status = exec_result.get("status", "ERROR")
        if status == "EXECUTED":
            results["trades_executed"] += 1
            bankroll -= trade_decision.get("position_size", 0)  # Reduce available bankroll

        results["trade_details"].append({
            "market_id": market_id,
            "question": question[:100],
            "decision": status,
            "side": trade_decision.get("side"),
            "position_size": trade_decision.get("position_size"),
            "edge": trade_decision.get("edge"),
        })

    # Step 3: Generate summary
    results["api_usage"] = client.get_usage_stats()

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Complete")
    logger.info(f"Markets scanned: {results['markets_scanned']}")
    logger.info(f"Markets analyzed: {results['markets_analyzed']}")
    logger.info(f"Trades executed: {results['trades_executed']}")
    logger.info(f"Trades skipped: {results['trades_skipped']}")
    logger.info(f"Errors: {len(results['errors'])}")
    logger.info(f"API cost: ${results['api_usage']['total_cost']:.4f}")
    logger.info("=" * 60)

    # Save daily report
    report_dir = Path("data/logs")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"daily_scan_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Report saved to {report_path}")

    return results


def main():
    """Entry point for CalibraMark."""
    import argparse

    parser = argparse.ArgumentParser(description="CalibraMark - Prediction Market Analysis")
    parser.add_argument("--dry-run", action="store_true", help="Run without executing trades")
    parser.add_argument("--max-markets", type=int, default=10, help="Max markets to analyze")
    parser.add_argument("--no-classify", action="store_true", help="Skip AI classification")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    setup_logging(log_level=args.log_level)

    results = run_pipeline(
        classify=not args.no_classify,
        max_markets=args.max_markets,
        dry_run=args.dry_run,
    )

    # Print summary to stdout
    print(f"\nCalibraMark Scan Complete")
    print(f"Markets: {results.get('markets_scanned', 0)} scanned, {results.get('markets_analyzed', 0)} analyzed")
    print(f"Trades: {results.get('trades_executed', 0)} executed, {results.get('trades_skipped', 0)} skipped")
    if results.get("errors"):
        print(f"Errors: {len(results['errors'])}")

    return 0 if not results.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
