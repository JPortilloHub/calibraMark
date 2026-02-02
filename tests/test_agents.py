"""Tests for agent module (unit tests with mocked API calls)."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_settings(tmp_path):
    """Patch settings for tests."""
    import config.settings as settings_mod

    class FakeSettings:
        anthropic_api_key = "test-key"
        anthropic_model = "claude-sonnet-4-20250514"
        data_dir = tmp_path
        log_dir = tmp_path / "logs"
        paper_trading_mode = True
        paper_trading_starting_bankroll = 10000.0
        max_position_size_usd = 1000.0
        max_daily_loss_usd = 200.0
        max_drawdown_percent = 20.0
        kelly_fraction = 0.25
        min_edge_threshold = 0.05
        min_market_liquidity = 10000.0
        min_days_until_resolution = 1
        max_days_until_resolution = 90
        def ensure_directories(self):
            self.data_dir.mkdir(parents=True, exist_ok=True)

    original = settings_mod._settings
    settings_mod._settings = FakeSettings()
    yield FakeSettings()
    settings_mod._settings = original


@pytest.fixture
def mock_risk_limits(mock_settings):
    """Reset risk limits singleton."""
    import config.risk_limits as rl_mod
    original = rl_mod._risk_limits
    rl_mod._risk_limits = None
    yield
    rl_mod._risk_limits = original


def test_base_agent_load_skill():
    """BaseAgent should load skill files and strip frontmatter."""
    from agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        def run(self, **kwargs):
            return {}

    agent = TestAgent.__new__(TestAgent)
    agent.name = "test"
    import logging
    agent.logger = logging.getLogger("test")

    skill = agent._load_skill("probability-calibration")
    assert "Reference Class Analysis" in skill
    assert "---" not in skill  # Frontmatter stripped


def test_base_agent_parse_json():
    """BaseAgent should parse JSON from various formats."""
    from agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        def run(self, **kwargs):
            return {}

    agent = TestAgent.__new__(TestAgent)
    agent.name = "test"

    # Plain JSON
    result = agent._parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}

    # JSON in code block
    result = agent._parse_json_response('Text\n```json\n{"a": 1}\n```\nMore')
    assert result == {"a": 1}

    # JSON embedded in text
    result = agent._parse_json_response('Here is the result: {"b": 2} and done')
    assert result == {"b": 2}


def test_calibration_agent_no_trade_low_edge(mock_settings, mock_risk_limits):
    """CalibrationAgent should return NO_TRADE when edge is below threshold."""
    from agents.calibration_agent import CalibrationAgent

    mock_client = MagicMock()
    # Mock probability response with low edge
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(type="text", text=json.dumps({
            "probability": 0.52,
            "confidence_interval": [0.45, 0.59],
            "confidence_level": "low",
        }))
    ]
    mock_client.create_message.return_value = mock_response

    from utils.data_storage import DataStorage
    storage = DataStorage(db_path=mock_settings.data_dir / "test_cal.db")

    agent = CalibrationAgent(client=mock_client, storage=storage)

    result = agent.run(
        market_id="test-low-edge",
        market_question="Will it rain?",
        market_price=0.50,
    )

    assert result["decision"] == "NO_TRADE"
    assert result["edge"] < 0.05


def test_calibration_agent_trade_decision(mock_settings, mock_risk_limits):
    """CalibrationAgent should return TRADE when edge is sufficient."""
    from agents.calibration_agent import CalibrationAgent

    mock_client = MagicMock()

    call_count = [0]
    def mock_create_message(**kwargs):
        call_count[0] += 1
        mock_response = MagicMock()
        if call_count[0] == 1:
            # Probability estimation
            mock_response.content = [
                MagicMock(type="text", text=json.dumps({
                    "probability": 0.70,
                    "confidence_interval": [0.60, 0.80],
                    "confidence_level": "medium",
                }))
            ]
        else:
            # Kelly calculation
            mock_response.content = [
                MagicMock(type="text", text=json.dumps({
                    "recommendation": "TRADE",
                    "final_position_size": 350.0,
                    "kelly_fractional": 0.035,
                    "edge": 0.15,
                }))
            ]
        return mock_response

    mock_client.create_message = MagicMock(side_effect=mock_create_message)

    from utils.data_storage import DataStorage
    storage = DataStorage(db_path=mock_settings.data_dir / "test_cal2.db")

    agent = CalibrationAgent(client=mock_client, storage=storage)

    result = agent.run(
        market_id="test-trade",
        market_question="Will BTC exceed 100k?",
        market_price=0.55,
    )

    assert result["decision"] == "TRADE"
    assert result["side"] == "YES"
    assert result["edge"] == pytest.approx(0.15)
    assert result["position_size"] == 350.0
