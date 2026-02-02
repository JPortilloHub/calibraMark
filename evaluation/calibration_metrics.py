"""Calibration metrics for probability predictions."""

import logging
from typing import List, Tuple

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss


logger = logging.getLogger("calibramark.calibration")


def calculate_brier_score(predictions: List[float], outcomes: List[int]) -> float:
    """
    Calculate Brier score for probability predictions.

    Brier score measures the mean squared difference between predicted probabilities
    and actual outcomes. Lower is better (0 = perfect, 1 = worst).

    Args:
        predictions: List of predicted probabilities (0-1)
        outcomes: List of actual outcomes (0 or 1)

    Returns:
        Brier score (0-1, lower is better)
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have the same length")

    if len(predictions) == 0:
        return 0.0

    # Convert to numpy arrays
    y_true = np.array(outcomes)
    y_prob = np.array(predictions)

    # Validate inputs
    if not all(0 <= p <= 1 for p in y_prob):
        raise ValueError("All predictions must be between 0 and 1")

    if not all(o in [0, 1] for o in y_true):
        raise ValueError("All outcomes must be 0 or 1")

    return float(brier_score_loss(y_true, y_prob))


def calculate_ece(
    predictions: List[float], outcomes: List[int], n_bins: int = 10
) -> float:
    """
    Calculate Expected Calibration Error (ECE).

    ECE is the weighted average of the absolute difference between predicted
    and observed frequencies across bins.

    Args:
        predictions: List of predicted probabilities (0-1)
        outcomes: List of actual outcomes (0 or 1)
        n_bins: Number of bins for grouping predictions

    Returns:
        ECE value (0-1, lower is better)
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have the same length")

    if len(predictions) == 0:
        return 0.0

    y_true = np.array(outcomes)
    y_prob = np.array(predictions)

    # Create bins
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]

    ece = 0.0
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        # Find predictions in this bin
        in_bin = (y_prob > bin_lower) & (y_prob <= bin_upper)
        prop_in_bin = np.mean(in_bin)

        if prop_in_bin > 0:
            # Average predicted probability in bin
            avg_predicted = np.mean(y_prob[in_bin])
            # Actual frequency of positive outcomes in bin
            avg_actual = np.mean(y_true[in_bin])
            # Weighted absolute difference
            ece += prop_in_bin * abs(avg_predicted - avg_actual)

    return float(ece)


def generate_calibration_curve(
    predictions: List[float], outcomes: List[int], n_bins: int = 10, strategy: str = "uniform"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate calibration curve data.

    Args:
        predictions: List of predicted probabilities (0-1)
        outcomes: List of actual outcomes (0 or 1)
        n_bins: Number of bins
        strategy: Binning strategy ('uniform' or 'quantile')

    Returns:
        Tuple of (fraction_of_positives, mean_predicted_value) arrays
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have the same length")

    if len(predictions) == 0:
        return np.array([]), np.array([])

    y_true = np.array(outcomes)
    y_prob = np.array(predictions)

    fraction_of_positives, mean_predicted_value = calibration_curve(
        y_true, y_prob, n_bins=n_bins, strategy=strategy
    )

    return fraction_of_positives, mean_predicted_value


def analyze_calibration_by_bucket(
    predictions: List[float], outcomes: List[int], n_bins: int = 10
) -> List[dict]:
    """
    Analyze calibration broken down by probability buckets.

    Args:
        predictions: List of predicted probabilities (0-1)
        outcomes: List of actual outcomes (0 or 1)
        n_bins: Number of bins

    Returns:
        List of dicts with bucket analysis
    """
    if len(predictions) == 0:
        return []

    y_true = np.array(outcomes)
    y_prob = np.array(predictions)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]

    analysis = []

    for i, (bin_lower, bin_upper) in enumerate(zip(bin_lowers, bin_uppers)):
        in_bin = (y_prob > bin_lower) & (y_prob <= bin_upper)
        count = np.sum(in_bin)

        if count > 0:
            avg_predicted = float(np.mean(y_prob[in_bin]))
            avg_actual = float(np.mean(y_true[in_bin]))
            bias = avg_predicted - avg_actual

            analysis.append(
                {
                    "bucket": f"{bin_lower:.1f}-{bin_upper:.1f}",
                    "bucket_index": i,
                    "count": int(count),
                    "avg_predicted": avg_predicted,
                    "avg_actual": avg_actual,
                    "bias": bias,
                    "status": "overconfident" if bias > 0.05 else "underconfident"
                    if bias < -0.05
                    else "well_calibrated",
                }
            )

    return analysis


def calculate_log_score(predictions: List[float], outcomes: List[int]) -> float:
    """
    Calculate logarithmic scoring rule (log loss).

    Proper scoring rule that heavily penalizes confident wrong predictions.

    Args:
        predictions: List of predicted probabilities (0-1)
        outcomes: List of actual outcomes (0 or 1)

    Returns:
        Log loss (lower is better, 0 = perfect)
    """
    if len(predictions) == 0:
        return 0.0

    y_true = np.array(outcomes)
    y_prob = np.array(predictions)

    # Clip probabilities to avoid log(0)
    y_prob = np.clip(y_prob, 1e-15, 1 - 1e-15)

    # Calculate log loss
    log_loss = -np.mean(y_true * np.log(y_prob) + (1 - y_true) * np.log(1 - y_prob))

    return float(log_loss)
