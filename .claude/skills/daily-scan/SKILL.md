---
name: daily-scan
description: Manually trigger a full daily market scan cycle. Scans markets, analyzes sentiment and fundamentals, and identifies trades.
allowed-tools: Read, Bash(python *), Glob, Grep
---

Run a full CalibraMark daily market scan cycle.

## Pipeline Steps

1. **Check kill switch** - Verify the system is not in emergency stop mode
   ```python
   import sys
   sys.path.insert(0, '/workspaces/calibraMark')
   from utils.kill_switch import KillSwitch
   ks = KillSwitch()
   if ks.is_active():
       print("KILL SWITCH ACTIVE - No trading allowed")
       # Show kill switch details and exit
   ```

2. **Scan active markets** from Polymarket
   - Fetch markets with minimum $10k liquidity
   - Filter by resolution date (1-90 days out)
   - Classify each market by domain

3. **For each shortlisted market**:
   a. **News Sentiment Analysis**
      - Search relevant news (last 7 days)
      - Score sentiment and credibility

   b. **Fundamental Analysis**
      - Fetch relevant data based on market category
      - Assess fundamental alignment

   c. **Probability Estimation**
      - Synthesize all inputs
      - Generate calibrated probability estimate
      - Check for biases

   d. **Position Sizing** (if edge detected)
      - Calculate Kelly criterion position
      - Apply risk limits

   e. **Execution Decision**
      - Evaluate trading costs
      - Make final TRADE/NO_TRADE decision

4. **Generate daily report**:
   ```
   === CalibraMark Daily Scan ===
   Date: YYYY-MM-DD HH:MM UTC

   Markets Scanned: XX
   Markets Shortlisted: XX
   Trades Executed: X

   New Positions:
   - [market question] | Side: YES/NO | Size: $XXX | Edge: XX%

   Skipped (insufficient edge):
   - [market question] | Edge: X.X% (below 5% threshold)

   Risk Status:
   - Current Drawdown: X.X%
   - Daily P&L: $XX.XX
   - Kill Switch: INACTIVE
   ```

5. **Save scan results** to `data/logs/daily_scan_YYYY-MM-DD.json`

## Notes
- This skill runs the FULL pipeline end-to-end
- If agents are not yet implemented, run available components and note what's missing
- Always check risk limits before executing any trades
- Log all decisions with full reasoning for audit trail
