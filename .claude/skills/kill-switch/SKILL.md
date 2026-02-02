---
name: kill-switch
description: Activate or deactivate the emergency kill switch. Use to halt all trading activity.
allowed-tools: Read, Bash(python *), Glob
---

Manage the CalibraMark emergency kill switch.

## Usage

When invoked, determine the requested action:
- **activate**: Stop all trading immediately
- **deactivate**: Resume trading (requires confirmation)
- **status**: Check current kill switch state

## Steps

1. **Load kill switch module**:
   ```python
   import sys
   sys.path.insert(0, '/workspaces/calibraMark')
   from utils.kill_switch import KillSwitch
   ks = KillSwitch()
   ```

2. **Check current status**:
   ```python
   status = ks.get_status()
   print(f"Kill Switch: {'ACTIVE' if status['is_active'] else 'INACTIVE'}")
   if status['is_active']:
       print(f"Reason: {status['reason']}")
       print(f"Activated: {status['activated_at']}")
   ```

3. **If activating**:
   ```python
   ks.activate(reason="Manual activation via /kill-switch")
   print("Kill switch ACTIVATED. All trading halted.")
   ```

4. **If deactivating**:
   - Display current status and reason for activation
   - Show current drawdown and daily P&L
   - Confirm the user wants to resume trading
   ```python
   ks.deactivate()
   print("Kill switch DEACTIVATED. Trading can resume.")
   ```

## Display Format

```
=== CalibraMark Kill Switch ===

Status: ACTIVE / INACTIVE
Reason: [reason for activation, if active]
Activated At: [timestamp, if active]

Current Risk Metrics:
- Drawdown: X.X% (limit: 20%)
- Daily Loss: $XX.XX (limit: $200)
- Open Positions: X

Action Taken: [activated/deactivated/no change]
```

## Automatic Triggers
The kill switch activates automatically when:
- Drawdown exceeds 20%
- Daily loss exceeds $200
- Critical API errors (3+ consecutive failures)

Manual deactivation is required to resume after automatic triggers.
