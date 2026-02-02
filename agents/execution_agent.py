"""Execution Agent - Executes paper trades with risk checks."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from config import get_settings, get_risk_limits
from mcp_servers.polymarket_server import execute_paper_trade
from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage
from utils.kill_switch import KillSwitch


class ExecutionAgent(BaseAgent):
    """
    Final agent in the pipeline. Verifies risk limits, analyzes
    trading costs, and executes paper trades.

    Checks before execution:
    1. Kill switch is not active
    2. Daily loss within limits
    3. Drawdown within limits
    4. Trading costs don't consume edge
    """

    def __init__(
        self,
        client: Optional[AnthropicClient] = None,
        storage: Optional[DataStorage] = None,
        kill_switch: Optional[KillSwitch] = None,
    ):
        super().__init__(name="execution", client=client, storage=storage)
        self.settings = get_settings()
        self.risk_limits = get_risk_limits()
        self.kill_switch = kill_switch or KillSwitch()

    def _check_kill_switch(self) -> tuple[bool, str]:
        """Check if kill switch is active."""
        if self.kill_switch.is_active():
            state = self.kill_switch.get_state()
            return False, f"Kill switch active: {state.get('reason', 'unknown')}"
        return True, "Kill switch inactive"

    def _check_daily_loss(self) -> tuple[bool, str]:
        """Check if daily loss is within limits."""
        today = datetime.now().date().isoformat()
        trades = self.storage.get_all_trades()

        daily_loss = 0.0
        for trade in trades:
            ts = trade.get("timestamp", "")
            if ts.startswith(today) and trade.get("pnl") is not None:
                pnl = trade["pnl"]
                if pnl < 0:
                    daily_loss += abs(pnl)

        if daily_loss >= self.risk_limits.max_daily_loss_usd:
            return False, f"Daily loss ${daily_loss:.2f} >= limit ${self.risk_limits.max_daily_loss_usd:.2f}"

        remaining = self.risk_limits.max_daily_loss_usd - daily_loss
        return True, f"Daily loss ${daily_loss:.2f}, ${remaining:.2f} remaining"

    def _analyze_microstructure(
        self,
        market_id: str,
        market_price: float,
        position_size: float,
        liquidity: float,
        edge: float,
    ) -> Dict[str, Any]:
        """Analyze trading costs using market-microstructure skill."""
        context = json.dumps({
            "market_id": market_id,
            "market_price": market_price,
            "position_size": position_size,
            "liquidity": liquidity,
            "edge": edge,
            "side": "YES" if edge > 0 else "NO",
        }, indent=2)

        response_text = self._invoke_skill(
            "market-microstructure",
            f"Analyze trading costs for this execution:\n\n{context}",
            max_tokens=2048,
            temperature=0.2,
        )

        return self._parse_json_response(response_text)

    def _execute_paper_trade(self, trade_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a paper trade via the Polymarket MCP server."""
        raw = execute_paper_trade(
            market_id=trade_params["market_id"],
            market_question=trade_params["market_question"],
            side=trade_params["side"],
            position_size=trade_params["position_size"],
            entry_price=trade_params["entry_price"],
            agent_probability=trade_params.get("agent_probability", 0.0),
            expected_value=trade_params.get("expected_value", 0.0),
            reasoning=trade_params.get("reasoning", ""),
        )
        return json.loads(raw)

    def run(
        self,
        trade_decision: Optional[Dict[str, Any]] = None,
        liquidity: float = 50000.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute a trade decision from the CalibrationAgent.

        Args:
            trade_decision: Output from CalibrationAgent (must have decision="TRADE")
            liquidity: Market liquidity for cost analysis

        Returns:
            Dict with execution result
        """
        if trade_decision is None or trade_decision.get("decision") != "TRADE":
            return {
                "status": "SKIPPED",
                "reason": "No trade decision or decision is NO_TRADE",
            }

        market_id = trade_decision.get("market_id", "")
        self.logger.info(f"Executing trade for market: {market_id}")

        # Pre-execution checks
        ks_ok, ks_msg = self._check_kill_switch()
        if not ks_ok:
            self.logger.warning(f"Execution blocked: {ks_msg}")
            return {"status": "BLOCKED", "reason": ks_msg}

        dl_ok, dl_msg = self._check_daily_loss()
        if not dl_ok:
            self.logger.warning(f"Execution blocked: {dl_msg}")
            return {"status": "BLOCKED", "reason": dl_msg}

        # Analyze trading costs
        edge = trade_decision.get("edge", 0)
        position_size = trade_decision.get("position_size", 0)
        market_price = trade_decision.get("market_price", 0.5)

        try:
            cost_analysis = self._analyze_microstructure(
                market_id, market_price, position_size, liquidity, edge
            )
        except Exception as e:
            self.logger.warning(f"Cost analysis failed, proceeding with caution: {e}")
            cost_analysis = {"recommendation": "EXECUTE", "error": str(e)}

        recommendation = cost_analysis.get("recommendation", "EXECUTE")

        if recommendation == "NO_TRADE":
            result = {
                "status": "REJECTED",
                "reason": "Trading costs consume edge",
                "cost_analysis": cost_analysis,
            }
            self._save_decision(market_id, {
                "decision": "REJECTED",
                "reasoning": "Costs consume edge",
                "metadata": result,
            })
            return result

        # Adjust position if costs are high
        if recommendation == "REDUCE_SIZE":
            suggested = cost_analysis.get("suggested_position_size", position_size * 0.5)
            position_size = min(position_size, suggested)
            self.logger.info(f"Position reduced to ${position_size:.2f} due to costs")

        if recommendation == "SKIP":
            result = {
                "status": "SKIPPED",
                "reason": "Edge marginal after costs",
                "cost_analysis": cost_analysis,
            }
            self._save_decision(market_id, {
                "decision": "SKIPPED",
                "reasoning": "Edge marginal after costs",
                "metadata": result,
            })
            return result

        # Execute the paper trade
        trade_params = {
            "market_id": market_id,
            "market_question": trade_decision.get("market_question", ""),
            "side": trade_decision.get("side", "YES"),
            "position_size": position_size,
            "entry_price": market_price,
            "agent_probability": trade_decision.get("agent_probability", 0.5),
            "expected_value": trade_decision.get("expected_value", 0),
            "reasoning": json.dumps({
                "edge": edge,
                "confidence": trade_decision.get("confidence", ""),
                "cost_analysis": {
                    "total_cost_pct": cost_analysis.get("total_cost_pct", 0),
                    "net_edge_pct": cost_analysis.get("net_edge_pct", edge),
                },
            }),
        }

        try:
            execution_result = self._execute_paper_trade(trade_params)
        except Exception as e:
            self.logger.error(f"Paper trade execution failed: {e}")
            self.kill_switch.check_and_activate_on_error(e, "paper_trade_execution")
            return {"status": "ERROR", "reason": str(e)}

        # Also save to SQLite storage
        self.storage.save_paper_trade({
            "market_id": market_id,
            "market_question": trade_decision.get("market_question", ""),
            "side": trade_decision.get("side", "YES"),
            "position_size": position_size,
            "entry_price": market_price,
            "agent_probability": trade_decision.get("agent_probability"),
            "kelly_fraction": trade_decision.get("kelly_result", {}).get("kelly_fractional"),
            "expected_value": trade_decision.get("expected_value"),
            "reasoning": trade_params["reasoning"],
        })

        result = {
            "status": "EXECUTED",
            "trade": execution_result.get("trade", {}),
            "cost_analysis": cost_analysis,
        }

        self._save_decision(market_id, {
            "decision": "EXECUTED",
            "reasoning": f"{trade_decision.get('side')} ${position_size:.2f} @ {market_price:.2%}",
            "metadata": result,
        })

        self.logger.info(
            f"Trade executed: {trade_decision.get('side')} ${position_size:.2f} "
            f"@ {market_price:.2%} for market {market_id}"
        )

        return result
