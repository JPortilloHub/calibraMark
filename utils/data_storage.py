"""Data storage and persistence layer for CalibraMark."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_settings


class DataStorage:
    """
    Data storage manager using SQLite for structured data and JSON for exports.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize data storage.

        Args:
            db_path: Optional path to SQLite database (defaults to data/calibramark.db)
        """
        settings = get_settings()
        self.db_path = db_path or (settings.data_dir / "calibramark.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Paper trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    market_question TEXT NOT NULL,
                    side TEXT NOT NULL,
                    position_size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    pnl REAL,
                    status TEXT NOT NULL,
                    agent_probability REAL,
                    kelly_fraction REAL,
                    expected_value REAL,
                    reasoning TEXT,
                    resolved_at TEXT,
                    outcome TEXT
                )
            """)

            # Market snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    market_question TEXT NOT NULL,
                    yes_price REAL NOT NULL,
                    no_price REAL NOT NULL,
                    liquidity REAL,
                    volume REAL,
                    resolution_date TEXT
                )
            """)

            # Agent decisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reasoning TEXT,
                    metadata TEXT
                )
            """)

            # Calibration history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calibration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    brier_score REAL NOT NULL,
                    win_rate REAL NOT NULL,
                    total_trades INTEGER NOT NULL,
                    avg_edge REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL
                )
            """)

            # Create indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_market ON paper_trades(market_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON paper_trades(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_market ON market_snapshots(market_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_decisions_agent ON agent_decisions(agent_name)"
            )

            conn.commit()

    def save_paper_trade(self, trade: Dict[str, Any]) -> int:
        """
        Save a paper trade to the database.

        Args:
            trade: Trade data dictionary

        Returns:
            Trade ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO paper_trades (
                    timestamp, market_id, market_question, side, position_size,
                    entry_price, exit_price, pnl, status, agent_probability,
                    kelly_fraction, expected_value, reasoning, resolved_at, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trade.get("timestamp", datetime.now().isoformat()),
                    trade["market_id"],
                    trade["market_question"],
                    trade["side"],
                    trade["position_size"],
                    trade["entry_price"],
                    trade.get("exit_price"),
                    trade.get("pnl"),
                    trade.get("status", "OPEN"),
                    trade.get("agent_probability"),
                    trade.get("kelly_fraction"),
                    trade.get("expected_value"),
                    trade.get("reasoning"),
                    trade.get("resolved_at"),
                    trade.get("outcome"),
                ),
            )
            trade_id = cursor.lastrowid
            conn.commit()
            return trade_id

    def update_trade_resolution(
        self, trade_id: int, exit_price: float, pnl: float, outcome: str
    ) -> None:
        """Update a trade with resolution data."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE paper_trades
                SET exit_price = ?, pnl = ?, status = 'CLOSED',
                    resolved_at = ?, outcome = ?
                WHERE id = ?
            """,
                (exit_price, pnl, datetime.now().isoformat(), outcome, trade_id),
            )
            conn.commit()

    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get all open trades."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_trades WHERE status = 'OPEN' ORDER BY timestamp")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_trades(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all trades, optionally limited."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM paper_trades ORDER BY timestamp DESC"
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def save_market_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Save a market snapshot."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO market_snapshots (
                    timestamp, market_id, market_question, yes_price, no_price,
                    liquidity, volume, resolution_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    snapshot.get("timestamp", datetime.now().isoformat()),
                    snapshot["market_id"],
                    snapshot["market_question"],
                    snapshot["yes_price"],
                    snapshot["no_price"],
                    snapshot.get("liquidity"),
                    snapshot.get("volume"),
                    snapshot.get("resolution_date"),
                ),
            )
            conn.commit()

    def save_agent_decision(self, agent_name: str, market_id: str, decision: Dict[str, Any]) -> None:
        """Save an agent's decision."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_decisions (
                    timestamp, agent_name, market_id, decision, reasoning, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().isoformat(),
                    agent_name,
                    market_id,
                    decision.get("decision", ""),
                    decision.get("reasoning", ""),
                    json.dumps(decision.get("metadata", {})),
                ),
            )
            conn.commit()

    def save_calibration_metrics(self, metrics: Dict[str, Any]) -> None:
        """Save daily calibration metrics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO calibration_history (
                    date, brier_score, win_rate, total_trades, avg_edge,
                    sharpe_ratio, max_drawdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metrics.get("date", datetime.now().date().isoformat()),
                    metrics["brier_score"],
                    metrics["win_rate"],
                    metrics["total_trades"],
                    metrics.get("avg_edge"),
                    metrics.get("sharpe_ratio"),
                    metrics.get("max_drawdown"),
                ),
            )
            conn.commit()

    def get_calibration_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get calibration history for the last N days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM calibration_history
                ORDER BY date DESC
                LIMIT ?
            """,
                (days,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def export_to_json(self, table: str, filepath: Path) -> None:
        """Export a table to JSON file."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table}")
            data = [dict(row) for row in cursor.fetchall()]

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
