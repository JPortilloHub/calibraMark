---
name: check-status
description: Display current system status, P&L, and performance metrics
allowed-tools: Read, Bash(python *)
---

Display CalibraMark system status with current performance metrics and graduation criteria.

## Steps to Execute

1. **Load Current Data**
   - Read paper trading database: `data/calibramark.db`
   - Or if database doesn't exist, check for JSON files in `data/paper_trades/`

2. **Calculate Metrics**
   - Current bankroll (starting bankroll + sum of all P&L)
   - Total P&L
   - Today's P&L
   - Max drawdown
   - Brier score (30-day)
   - Win rate
   - Total trades executed
   - Sharpe ratio (if sufficient data)

3. **Check Kill Switch Status**
   - Read `data/kill_switch.json`
   - If file doesn't exist, kill switch is INACTIVE

4. **Check Graduation Criteria**
   - Brier score < 0.15
   - Positive P&L with p < 0.05
   - Max drawdown < 20%
   - Win rate > 52%
   - At least 30 days of trading data

5. **Display Formatted Output**

## Output Format

```
=== CalibraMark Status ===
Date: YYYY-MM-DD HH:MM UTC

💰 Performance
- Current Bankroll: $X,XXX.XX
- Total P&L: $XXX.XX (+X.X%)
- Today's P&L: $XX.XX
- Max Drawdown: X.X%

📊 Calibration (30-day)
- Brier Score: 0.XXX
- Win Rate: XX%
- Total Trades: XX
- Sharpe Ratio: X.XX

🚨 Risk Status
- Kill Switch: [ACTIVE / INACTIVE]
- Daily Loss Limit: $XX / $200 remaining
- Position Count: X active positions
- Current Drawdown: X.X% / 20% limit

✅ Graduation Criteria (30-day)
  [✓/✗] Brier < 0.15 (actual: 0.XXX)
  [✓/✗] Positive P&L (p=0.XXX)
  [✓/✗] Win Rate > 52% (actual: XX%)
  [✓/✗] Max Drawdown < 20% (actual: X.X%)
  [✓/✗] Minimum 30 days active

Status: [READY FOR REAL TRADING / CONTINUE PAPER TRADING]
```

## Implementation Approach

You can use Python to calculate metrics:

```python
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

# Load database
db_path = Path("data/calibramark.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all trades
    cursor.execute("SELECT * FROM paper_trades ORDER BY timestamp")
    trades = cursor.fetchall()

    # Calculate metrics
    # ... (implement calculations)

    conn.close()
else:
    print("No database found. System has not recorded any trades yet.")
```

Or use the evaluation modules if they're available:

```python
from evaluation import PaperTradingMonitor
from utils import DataStorage, KillSwitch

storage = DataStorage()
monitor = PaperTradingMonitor(storage)
kill_switch = KillSwitch()

# Get status
report = monitor.generate_status_report()
print(report)

# Check kill switch
if kill_switch.is_active():
    print("\n⚠️  KILL SWITCH IS ACTIVE")
    state = kill_switch.get_state()
    print(f"Activated: {state['activated_at']}")
    print(f"Reason: {state['reason']}")
```

## If No Data Exists

If the database is empty or doesn't exist:

```
=== CalibraMark Status ===
Date: YYYY-MM-DD HH:MM UTC

ℹ️  No trading data available yet.

Current Configuration:
- Paper Trading Mode: ENABLED
- Starting Bankroll: $10,000
- Max Position Size: $1,000
- Max Daily Loss: $200
- Max Drawdown: 20%
- Kelly Fraction: 0.25

System is ready to start trading.
Run /daily-scan to begin the first scan cycle.
```

## Error Handling

If you encounter errors:
- Check if data directory exists
- Check if database schema is initialized
- Provide helpful error message
- Suggest running initialization if needed
