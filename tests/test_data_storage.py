"""Tests for data storage module."""

import pytest
from pathlib import Path


@pytest.fixture
def storage(tmp_path):
    """Create a DataStorage instance with a temporary database."""
    # Patch settings to use tmp_path
    import config.settings as settings_mod

    class FakeSettings:
        data_dir = tmp_path
        log_dir = tmp_path / "logs"
        anthropic_api_key = "test"
        def ensure_directories(self):
            self.data_dir.mkdir(parents=True, exist_ok=True)

    original = settings_mod._settings
    settings_mod._settings = FakeSettings()

    from utils.data_storage import DataStorage
    ds = DataStorage(db_path=tmp_path / "test.db")

    yield ds

    settings_mod._settings = original


def test_save_and_retrieve_trade(storage):
    """Should save and retrieve a paper trade."""
    trade_id = storage.save_paper_trade({
        "market_id": "test-123",
        "market_question": "Will it rain tomorrow?",
        "side": "YES",
        "position_size": 100.0,
        "entry_price": 0.60,
    })

    assert trade_id > 0

    trades = storage.get_open_trades()
    assert len(trades) == 1
    assert trades[0]["market_id"] == "test-123"
    assert trades[0]["side"] == "YES"
    assert trades[0]["position_size"] == 100.0


def test_update_trade_resolution(storage):
    """Should update a trade with resolution data."""
    trade_id = storage.save_paper_trade({
        "market_id": "test-456",
        "market_question": "Will BTC hit 100k?",
        "side": "YES",
        "position_size": 200.0,
        "entry_price": 0.45,
    })

    storage.update_trade_resolution(trade_id, exit_price=1.0, pnl=110.0, outcome="WIN")

    trades = storage.get_all_trades()
    assert trades[0]["status"] == "CLOSED"
    assert trades[0]["pnl"] == 110.0
    assert trades[0]["outcome"] == "WIN"


def test_save_market_snapshot(storage):
    """Should save a market snapshot."""
    storage.save_market_snapshot({
        "market_id": "snap-123",
        "market_question": "Test market",
        "yes_price": 0.65,
        "no_price": 0.35,
        "liquidity": 50000,
        "volume": 120000,
    })
    # No error = success (no getter for snapshots currently)


def test_save_agent_decision(storage):
    """Should save an agent decision."""
    storage.save_agent_decision(
        agent_name="test_agent",
        market_id="dec-789",
        decision={
            "decision": "TRADE",
            "reasoning": "Strong edge detected",
            "metadata": {"edge": 0.12},
        },
    )


def test_save_calibration_metrics(storage):
    """Should save calibration metrics."""
    storage.save_calibration_metrics({
        "brier_score": 0.12,
        "win_rate": 0.58,
        "total_trades": 50,
        "avg_edge": 0.08,
        "sharpe_ratio": 1.5,
        "max_drawdown": 0.12,
    })

    history = storage.get_calibration_history(days=7)
    assert len(history) == 1
    assert history[0]["brier_score"] == 0.12


def test_export_to_json(storage, tmp_path):
    """Should export a table to JSON."""
    storage.save_paper_trade({
        "market_id": "exp-1",
        "market_question": "Export test",
        "side": "NO",
        "position_size": 50.0,
        "entry_price": 0.80,
    })

    export_path = tmp_path / "export.json"
    storage.export_to_json("paper_trades", export_path)

    import json
    with open(export_path) as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["market_id"] == "exp-1"
