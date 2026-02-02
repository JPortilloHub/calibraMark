"""Tests for evaluation module."""

import numpy as np
import pytest


def test_brier_score_perfect():
    """Perfect predictions should have Brier score of 0."""
    from evaluation.calibration_metrics import calculate_brier_score

    predictions = [1.0, 0.0, 1.0, 0.0]
    outcomes = [1, 0, 1, 0]
    score = calculate_brier_score(predictions, outcomes)
    assert score == pytest.approx(0.0)


def test_brier_score_worst():
    """Worst predictions should have Brier score of 1."""
    from evaluation.calibration_metrics import calculate_brier_score

    predictions = [0.0, 1.0, 0.0, 1.0]
    outcomes = [1, 0, 1, 0]
    score = calculate_brier_score(predictions, outcomes)
    assert score == pytest.approx(1.0)


def test_brier_score_coin_flip():
    """50/50 predictions should have Brier score of 0.25."""
    from evaluation.calibration_metrics import calculate_brier_score

    predictions = [0.5, 0.5, 0.5, 0.5]
    outcomes = [1, 0, 1, 0]
    score = calculate_brier_score(predictions, outcomes)
    assert score == pytest.approx(0.25)


def test_sharpe_ratio():
    """Sharpe ratio should be positive for consistently positive returns."""
    from evaluation.statistical_tests import calculate_sharpe_ratio

    returns = [0.01, 0.02, 0.015, 0.008, 0.012, 0.025, 0.01]
    sharpe = calculate_sharpe_ratio(returns)
    assert sharpe > 0


def test_max_drawdown():
    """Max drawdown should detect the largest peak-to-trough decline."""
    from evaluation.statistical_tests import calculate_max_drawdown

    equity_curve = [100, 110, 105, 95, 100, 90, 95]
    result = calculate_max_drawdown(equity_curve)
    # Returns tuple: (max_dd_pct, peak_idx, trough_idx)
    if isinstance(result, tuple):
        dd = result[0]
    else:
        dd = result
    # Peak was 110, trough was 90 -> 18.18%
    assert dd == pytest.approx(18.18, abs=0.1)


def test_win_rate_ci():
    """Win rate confidence interval should contain the true rate."""
    from evaluation.statistical_tests import calculate_win_rate_ci

    wins = 55
    total = 100
    lower, upper = calculate_win_rate_ci(wins, total)
    assert lower < 0.55
    assert upper > 0.55


def test_bootstrap_confidence_interval():
    """Bootstrap CI should contain the sample mean."""
    from evaluation.statistical_tests import bootstrap_confidence_interval

    np.random.seed(42)
    data = np.random.normal(100, 10, 50).tolist()
    # bootstrap_confidence_interval takes (data, confidence_level, n_iterations)
    lower, upper = bootstrap_confidence_interval(data, 0.95)
    sample_mean = np.mean(data)
    assert lower < sample_mean
    assert upper > sample_mean
