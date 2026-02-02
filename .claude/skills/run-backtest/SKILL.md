---
name: run-backtest
description: Run historical backtests on resolved Polymarket data. Use to evaluate system performance on past markets.
allowed-tools: Read, Bash(python *), Glob, Grep
---

Run a backtest of the CalibraMark prediction system on historical resolved markets.

## Steps

1. **Load historical data** from `data/historical_markets/`
   - Read resolved markets JSON files
   - Filter by date range if specified

2. **Run backtesting engine**:
   ```python
   import sys
   sys.path.insert(0, '/workspaces/calibraMark')
   from evaluation.backtesting import Backtester
   ```

3. **Execute backtest** with the following parameters:
   - Date range (default: last 6 months)
   - Minimum liquidity filter (default: $10k)
   - Agent pipeline function

4. **Generate results**:
   - Brier score
   - Calibration curve
   - P&L summary
   - Win rate and trade count
   - Statistical significance

5. **Display formatted results**:

```
=== CalibraMark Backtest Results ===
Period: YYYY-MM-DD to YYYY-MM-DD
Markets Analyzed: XXX
Trades Executed: XXX

Performance:
- Brier Score: 0.XXX (target < 0.20)
- Win Rate: XX.X%
- Total P&L: $XXX.XX
- Sharpe Ratio: X.XX
- Max Drawdown: XX.X%

Calibration:
- ECE (Expected Calibration Error): 0.XXX
- Overconfidence detected in: [ranges]
- Underconfidence detected in: [ranges]

Statistical Significance:
- P&L significance (p-value): 0.XXX
- Bootstrap CI (95%): [$XXX, $XXX]
```

## Notes
- If no historical data exists, prompt the user to run `scripts/fetch_historical_data.py` first
- Save backtest results to `data/backtest_results/` for comparison over time
- Always compare against a naive baseline (always predict 50%)
