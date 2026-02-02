---
name: analyze-calibration
description: Generate calibration curves and bias analysis reports. Use to evaluate prediction quality.
allowed-tools: Read, Bash(python *), Glob, Grep
---

Analyze the calibration quality of CalibraMark predictions.

## Steps

1. **Load prediction history** from `data/calibration_history/` and `data/paper_trades/`

2. **Calculate calibration metrics**:
   ```python
   import sys
   sys.path.insert(0, '/workspaces/calibraMark')
   from evaluation.calibration_metrics import (
       calculate_brier_score,
       calculate_ece,
       generate_calibration_curve,
       analyze_calibration_by_bucket,
   )
   ```

3. **Generate calibration curve**:
   - Plot predicted probabilities vs actual outcomes
   - Show perfect calibration line for reference
   - Save plot to `data/calibration_history/calibration_curve.png`

4. **Analyze by probability bucket**:
   - Bucket predictions into ranges (0-10%, 10-20%, ..., 90-100%)
   - Compare average prediction to actual outcome rate
   - Identify systematic biases

5. **Display formatted report**:

```
=== CalibraMark Calibration Report ===
Date: YYYY-MM-DD
Total Predictions: XXX

Overall Metrics:
- Brier Score: 0.XXX (target < 0.15)
- ECE: 0.XXX
- Log Score: X.XXX

Calibration by Bucket:
  0-10%: Predicted avg 5%, Actual 8% (underconfident)
  10-20%: Predicted avg 15%, Actual 12% (slightly overconfident)
  ...
  90-100%: Predicted avg 95%, Actual 88% (overconfident)

Systematic Biases Detected:
- [Description of any systematic over/under-confidence patterns]

Recommendations:
- [Actionable suggestions for improving calibration]
```

6. **Check edge decay** using rolling window analysis:
   - 7-day rolling Brier score
   - 30-day rolling Brier score
   - Trend detection (improving/stable/deteriorating)

## Notes
- If insufficient data (< 30 predictions), warn that results are not statistically meaningful
- Save report to `data/calibration_history/report_YYYY-MM-DD.json`
- Compare current calibration to historical reports to detect drift
