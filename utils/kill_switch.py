"""Emergency kill switch to halt all trading operations."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import get_settings


class KillSwitch:
    """
    Emergency stop mechanism for CalibraMark.

    The kill switch is activated when:
    - Drawdown exceeds limit
    - Daily loss exceeds limit
    - Critical API errors occur
    - Manual activation by user

    Once activated, it persists across restarts until manually reset.
    """

    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize kill switch.

        Args:
            state_file: Path to state file (defaults to data/kill_switch.json)
        """
        settings = get_settings()
        self.state_file = state_file or (settings.data_dir / "kill_switch.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("calibramark.kill_switch")

        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load kill switch state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load kill switch state: {e}")
                return {"active": False}
        return {"active": False}

    def _save_state(self) -> None:
        """Save kill switch state to file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self._state, f, indent=2)
        except IOError as e:
            self.logger.error(f"Failed to save kill switch state: {e}")

    def is_active(self) -> bool:
        """Check if kill switch is active."""
        return self._state.get("active", False)

    def activate(self, reason: str, metadata: Optional[dict] = None) -> None:
        """
        Activate the kill switch.

        Args:
            reason: Reason for activation
            metadata: Optional additional context
        """
        if self.is_active():
            self.logger.warning(f"Kill switch already active. Additional reason: {reason}")
            return

        self._state = {
            "active": True,
            "activated_at": datetime.now().isoformat(),
            "reason": reason,
            "metadata": metadata or {},
        }
        self._save_state()

        self.logger.critical("=" * 80)
        self.logger.critical("🚨 KILL SWITCH ACTIVATED")
        self.logger.critical(f"Reason: {reason}")
        self.logger.critical(f"Time: {self._state['activated_at']}")
        if metadata:
            self.logger.critical(f"Metadata: {json.dumps(metadata, indent=2)}")
        self.logger.critical("All trading operations are HALTED.")
        self.logger.critical("Run /kill-switch to deactivate manually.")
        self.logger.critical("=" * 80)

    def deactivate(self, reason: str = "Manual deactivation") -> bool:
        """
        Deactivate the kill switch.

        Args:
            reason: Reason for deactivation

        Returns:
            True if deactivated, False if was not active
        """
        if not self.is_active():
            self.logger.info("Kill switch is not active")
            return False

        old_state = self._state.copy()

        self._state = {
            "active": False,
            "deactivated_at": datetime.now().isoformat(),
            "deactivation_reason": reason,
            "previous_activation": old_state,
        }
        self._save_state()

        self.logger.warning("=" * 80)
        self.logger.warning("✅ KILL SWITCH DEACTIVATED")
        self.logger.warning(f"Reason: {reason}")
        self.logger.warning(f"Time: {self._state['deactivated_at']}")
        self.logger.warning(f"Was activated: {old_state['activated_at']}")
        self.logger.warning(f"Was activated because: {old_state['reason']}")
        self.logger.warning("Trading operations can resume.")
        self.logger.warning("=" * 80)

        return True

    def get_state(self) -> dict:
        """Get current kill switch state."""
        return self._state.copy()

    def check_and_activate_on_drawdown(self, current_bankroll: float, peak_bankroll: float) -> bool:
        """
        Check drawdown and activate kill switch if limit exceeded.

        Args:
            current_bankroll: Current bankroll value
            peak_bankroll: Peak bankroll value

        Returns:
            True if kill switch was activated
        """
        if self.is_active():
            return False

        if peak_bankroll == 0:
            return False

        from config import get_risk_limits

        risk_limits = get_risk_limits()
        drawdown_pct = ((peak_bankroll - current_bankroll) / peak_bankroll) * 100

        if drawdown_pct > risk_limits.max_drawdown_percent:
            self.activate(
                reason=f"Drawdown limit exceeded: {drawdown_pct:.1f}% > {risk_limits.max_drawdown_percent:.1f}%",
                metadata={
                    "current_bankroll": current_bankroll,
                    "peak_bankroll": peak_bankroll,
                    "drawdown_percent": drawdown_pct,
                    "limit_percent": risk_limits.max_drawdown_percent,
                },
            )
            return True

        return False

    def check_and_activate_on_daily_loss(self, daily_loss: float) -> bool:
        """
        Check daily loss and activate kill switch if limit exceeded.

        Args:
            daily_loss: Absolute daily loss value (positive number)

        Returns:
            True if kill switch was activated
        """
        if self.is_active():
            return False

        from config import get_risk_limits

        risk_limits = get_risk_limits()

        if daily_loss > risk_limits.max_daily_loss_usd:
            self.activate(
                reason=f"Daily loss limit exceeded: ${daily_loss:.2f} > ${risk_limits.max_daily_loss_usd:.2f}",
                metadata={
                    "daily_loss": daily_loss,
                    "limit": risk_limits.max_daily_loss_usd,
                },
            )
            return True

        return False

    def check_and_activate_on_error(self, error: Exception, context: str) -> bool:
        """
        Check if error is critical and activate kill switch.

        Args:
            error: Exception that occurred
            context: Context where error occurred

        Returns:
            True if kill switch was activated
        """
        if self.is_active():
            return False

        # Define critical errors that should halt trading
        critical_errors = [
            "AuthenticationError",
            "PermissionError",
            "InsufficientFunds",
            "WalletError",
            "BlockchainError",
        ]

        error_type = type(error).__name__

        if any(critical in error_type for critical in critical_errors):
            self.activate(
                reason=f"Critical error: {error_type} in {context}",
                metadata={
                    "error_type": error_type,
                    "error_message": str(error),
                    "context": context,
                },
            )
            return True

        return False
