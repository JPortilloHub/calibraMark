"""Statistical significance tests and metrics."""

import logging
from typing import List, Tuple

import numpy as np
from scipy import stats


logger = logging.getLogger("calibramark.statistics")


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    """
    Calculate Sharpe ratio for a series of returns.

    Sharpe ratio measures risk-adjusted return. Higher is better.
    Typical interpretation:
    - < 1: Not great
    - 1-2: Good
    - 2-3: Very good
    - > 3: Excellent

    Args:
        returns: List of returns (as decimals, e.g., 0.05 for 5%)
        risk_free_rate: Annual risk-free rate (default 0)

    Returns:
        Sharpe ratio (annualized)
    """
    if len(returns) == 0:
        return 0.0

    returns_array = np.array(returns)

    # Calculate excess returns
    excess_returns = returns_array - risk_free_rate

    # Calculate mean and std
    mean_excess_return = np.mean(excess_returns)
    std_excess_return = np.std(excess_returns, ddof=1)

    if std_excess_return == 0:
        return 0.0

    # Annualize (assuming daily returns, 252 trading days per year)
    sharpe = (mean_excess_return / std_excess_return) * np.sqrt(252)

    return float(sharpe)


def calculate_max_drawdown(equity_curve: List[float]) -> Tuple[float, int, int]:
    """
    Calculate maximum drawdown from an equity curve.

    Args:
        equity_curve: List of equity values over time

    Returns:
        Tuple of (max_drawdown_pct, start_index, end_index)
    """
    if len(equity_curve) == 0:
        return 0.0, 0, 0

    equity = np.array(equity_curve)

    # Calculate running maximum
    running_max = np.maximum.accumulate(equity)

    # Calculate drawdown at each point
    drawdown = (equity - running_max) / running_max

    # Find maximum drawdown
    max_dd_idx = np.argmin(drawdown)
    max_dd = abs(drawdown[max_dd_idx])

    # Find start of drawdown (last peak before max drawdown)
    start_idx = np.where(running_max == running_max[max_dd_idx])[0][0]

    return float(max_dd * 100), int(start_idx), int(max_dd_idx)


def bootstrap_confidence_interval(
    data: List[float], confidence: float = 0.95, n_iterations: int = 10000
) -> Tuple[float, float]:
    """
    Calculate confidence interval using bootstrap method.

    Args:
        data: Sample data
        confidence: Confidence level (e.g., 0.95 for 95%)
        n_iterations: Number of bootstrap iterations

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if len(data) == 0:
        return 0.0, 0.0

    data_array = np.array(data)
    n = len(data_array)

    # Generate bootstrap samples
    bootstrap_means = np.zeros(n_iterations)
    for i in range(n_iterations):
        sample = np.random.choice(data_array, size=n, replace=True)
        bootstrap_means[i] = np.mean(sample)

    # Calculate confidence interval
    alpha = 1 - confidence
    lower = np.percentile(bootstrap_means, alpha / 2 * 100)
    upper = np.percentile(bootstrap_means, (1 - alpha / 2) * 100)

    return float(lower), float(upper)


def test_positive_expectation(
    pnl_values: List[float], alpha: float = 0.05
) -> Tuple[bool, float, float]:
    """
    Test if P&L has positive expectation (one-tailed t-test).

    H0: mean P&L <= 0
    H1: mean P&L > 0

    Args:
        pnl_values: List of P&L values
        alpha: Significance level (default 0.05)

    Returns:
        Tuple of (is_significant, t_statistic, p_value)
    """
    if len(pnl_values) < 2:
        return False, 0.0, 1.0

    pnl_array = np.array(pnl_values)

    # One-sample t-test against 0
    t_stat, p_value_two_tailed = stats.ttest_1samp(pnl_array, 0)

    # Convert to one-tailed (testing if mean > 0)
    p_value = p_value_two_tailed / 2 if t_stat > 0 else 1 - p_value_two_tailed / 2

    is_significant = p_value < alpha

    return is_significant, float(t_stat), float(p_value)


def calculate_win_rate_ci(
    wins: int, total: int, confidence: float = 0.95
) -> Tuple[float, float]:
    """
    Calculate confidence interval for win rate using Wilson score interval.

    Args:
        wins: Number of wins
        total: Total number of trades
        confidence: Confidence level

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if total == 0:
        return 0.0, 0.0

    p = wins / total
    z = stats.norm.ppf(1 - (1 - confidence) / 2)

    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * np.sqrt((p * (1 - p) / total + z**2 / (4 * total**2))) / denominator

    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)

    return float(lower), float(upper)


def permutation_test(
    group1: List[float], group2: List[float], n_permutations: int = 10000
) -> float:
    """
    Permutation test for difference in means.

    Args:
        group1: First group of values
        group2: Second group of values
        n_permutations: Number of permutations

    Returns:
        p-value
    """
    if len(group1) == 0 or len(group2) == 0:
        return 1.0

    # Observed difference
    observed_diff = abs(np.mean(group1) - np.mean(group2))

    # Combine groups
    combined = np.concatenate([group1, group2])
    n1 = len(group1)

    # Permutation test
    count = 0
    for _ in range(n_permutations):
        np.random.shuffle(combined)
        perm_group1 = combined[:n1]
        perm_group2 = combined[n1:]
        perm_diff = abs(np.mean(perm_group1) - np.mean(perm_group2))

        if perm_diff >= observed_diff:
            count += 1

    p_value = count / n_permutations

    return p_value


def calculate_sortino_ratio(returns: List[float], target_return: float = 0.0) -> float:
    """
    Calculate Sortino ratio (like Sharpe but only penalizes downside volatility).

    Args:
        returns: List of returns
        target_return: Target/minimum acceptable return

    Returns:
        Sortino ratio (annualized)
    """
    if len(returns) == 0:
        return 0.0

    returns_array = np.array(returns)

    # Calculate excess returns
    excess_returns = returns_array - target_return

    # Calculate mean excess return
    mean_excess = np.mean(excess_returns)

    # Calculate downside deviation (only negative returns)
    downside_returns = excess_returns[excess_returns < 0]

    if len(downside_returns) == 0:
        return float("inf") if mean_excess > 0 else 0.0

    downside_std = np.std(downside_returns, ddof=1)

    if downside_std == 0:
        return 0.0

    # Annualize
    sortino = (mean_excess / downside_std) * np.sqrt(252)

    return float(sortino)


def calculate_calmar_ratio(returns: List[float], equity_curve: List[float]) -> float:
    """
    Calculate Calmar ratio (return / max drawdown).

    Args:
        returns: List of returns
        equity_curve: Equity curve

    Returns:
        Calmar ratio
    """
    if len(returns) == 0 or len(equity_curve) == 0:
        return 0.0

    # Annualized return
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
    n_days = len(returns)
    annualized_return = (1 + total_return) ** (252 / n_days) - 1

    # Max drawdown
    max_dd, _, _ = calculate_max_drawdown(equity_curve)

    if max_dd == 0:
        return float("inf") if annualized_return > 0 else 0.0

    calmar = annualized_return / (max_dd / 100)

    return float(calmar)
