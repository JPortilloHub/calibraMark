"""Tests for kill switch module."""

import pytest
from pathlib import Path


@pytest.fixture
def kill_switch(tmp_path):
    """Create a KillSwitch with a temporary state file."""
    import config.settings as settings_mod

    class FakeSettings:
        data_dir = tmp_path
        log_dir = tmp_path / "logs"
        anthropic_api_key = "test"
        max_position_size_usd = 1000.0
        max_daily_loss_usd = 200.0
        max_drawdown_percent = 20.0
        kelly_fraction = 0.25
        min_edge_threshold = 0.05
        def ensure_directories(self):
            pass

    original = settings_mod._settings
    settings_mod._settings = FakeSettings()

    from utils.kill_switch import KillSwitch
    ks = KillSwitch(state_file=tmp_path / "ks.json")

    yield ks

    settings_mod._settings = original


def test_kill_switch_default_inactive(kill_switch):
    """Kill switch should start inactive."""
    assert kill_switch.is_active() is False


def test_activate_and_deactivate(kill_switch):
    """Should activate and deactivate."""
    kill_switch.activate(reason="Test activation")
    assert kill_switch.is_active() is True

    state = kill_switch.get_state()
    assert state["reason"] == "Test activation"

    kill_switch.deactivate(reason="Test deactivation")
    assert kill_switch.is_active() is False


def test_drawdown_trigger(kill_switch):
    """Should activate on excessive drawdown."""
    triggered = kill_switch.check_and_activate_on_drawdown(
        current_bankroll=7500,
        peak_bankroll=10000,
    )
    assert triggered is True
    assert kill_switch.is_active() is True


def test_drawdown_within_limit(kill_switch):
    """Should not activate on acceptable drawdown."""
    triggered = kill_switch.check_and_activate_on_drawdown(
        current_bankroll=9000,
        peak_bankroll=10000,
    )
    assert triggered is False
    assert kill_switch.is_active() is False


def test_daily_loss_trigger(kill_switch):
    """Should activate on excessive daily loss."""
    triggered = kill_switch.check_and_activate_on_daily_loss(daily_loss=250.0)
    assert triggered is True
    assert kill_switch.is_active() is True


def test_persistence(tmp_path):
    """Kill switch state should persist across instances."""
    import config.settings as settings_mod

    class FakeSettings:
        data_dir = tmp_path
        log_dir = tmp_path / "logs"
        anthropic_api_key = "test"
        max_position_size_usd = 1000.0
        max_daily_loss_usd = 200.0
        max_drawdown_percent = 20.0
        kelly_fraction = 0.25
        min_edge_threshold = 0.05
        def ensure_directories(self):
            pass

    original = settings_mod._settings
    settings_mod._settings = FakeSettings()

    from utils.kill_switch import KillSwitch

    state_file = tmp_path / "ks_persist.json"

    ks1 = KillSwitch(state_file=state_file)
    ks1.activate(reason="Persist test")

    ks2 = KillSwitch(state_file=state_file)
    assert ks2.is_active() is True
    assert ks2.get_state()["reason"] == "Persist test"

    settings_mod._settings = original
