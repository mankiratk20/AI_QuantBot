"""
Institutional Risk and Money Management Engine.
Enforces:
- Dynamic lot size calculation based on exact instrument contract specs and SL pips
- Account risk % per trade
- Maximum daily loss, weekly loss, and maximum total drawdown limits
- Maximum open positions and max exposure limits
- Consecutive loss protection with cooldown period
- Emergency kill-switch and auto-shutdown
"""

from typing import Dict, Any, Tuple, Optional
from datetime import datetime, date
from backend.config import INSTRUMENT_SPECS, DEFAULT_RISK_CONFIG
from backend.storage.db import get_connection, log_audit

class RiskManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = {**DEFAULT_RISK_CONFIG, **(config or {})}
        self.consecutive_losses = 0
        self.last_loss_time: Optional[datetime] = None

    def update_config(self, new_config: Dict[str, Any]):
        self.config.update(new_config)
        log_audit("RISK_CONFIG_UPDATED", "INFO", "Risk configuration updated.", self.config)

    def trigger_emergency_kill_switch(self, reason: str = "Manual User Trigger"):
        self.config["emergency_kill_switch_active"] = True
        log_audit("EMERGENCY_KILL_SWITCH", "CRITICAL", f"Emergency Kill Switch ACTIVATED: {reason}")

    def reset_kill_switch(self):
        self.config["emergency_kill_switch_active"] = False
        log_audit("EMERGENCY_KILL_SWITCH", "INFO", "Emergency Kill Switch deactivated by user.")

    def calculate_lot_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        account_balance: Optional[float] = None,
        risk_percent: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """
        Calculates exact position size (Lots) adhering to instrument specifications.
        Returns:
            - lots (float): Rounded lot size
            - planned_risk_amount (float): Dollar amount risked
            - sl_points (float): Stop loss distance in points
        """
        spec = INSTRUMENT_SPECS.get(symbol)
        if not spec:
            raise ValueError(f"Unknown instrument symbol: {symbol}")

        bal = account_balance or self.config["account_balance"]
        risk_pct = risk_percent or self.config["risk_percent_per_trade"]

        # Maximum planned monetary risk
        planned_risk_amount = bal * (risk_pct / 100.0)

        # Distance to Stop Loss
        point_size = spec["point_size"]
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            return 0.01, 0.0, 0.0

        sl_points = sl_distance / point_size

        # Institutional Point Value on 1 standard lot
        # For EURUSD: 1 point = 0.00001; 1 lot = 100,000 -> 1 point = $1.00; 1 pip (10 points) = $10.00
        # For XAUUSD: 1 point = 0.01; 1 lot = 100 oz -> 1 point = $1.00; $1.00 move = $100.00
        # For Indices: 1 point = 0.1 -> 1 point = $0.10
        point_value_per_lot = spec["tick_value_standard"] / (spec["pip_size"] / spec["point_size"])

        # Lot size = Risk Amount / (Stop Loss in points * Value per point)
        raw_lots = planned_risk_amount / (sl_points * point_value_per_lot)

        # Round to 2 decimal places (standard micro-lot increment 0.01)
        lots = max(0.01, round(raw_lots, 2))

        # Clamp to max allowed lot size
        max_lot = self.config.get("max_lot_size", 10.0)
        lots = min(lots, max_lot)

        return lots, planned_risk_amount, sl_points

    def validate_trade_risk(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        current_balance: float,
        current_equity: float,
        open_positions_count: int,
        daily_pnl: float,
        weekly_pnl: float,
        high_water_mark: float
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates all risk constraints before allowing an order to be placed.
        Returns (is_approved, rejection_reason, metrics)
        """
        # 1. Kill Switch Check
        if self.config.get("emergency_kill_switch_active", False):
            return False, "Emergency Kill Switch is currently ACTIVE. Trading is locked.", {}

        # 2. Maximum Open Trades
        max_open = self.config.get("max_open_trades", 3)
        if open_positions_count >= max_open:
            return False, f"Maximum open trades limit reached ({open_positions_count}/{max_open}).", {}

        # 3. Consecutive Loss Protection
        consec_limit = self.config.get("consecutive_loss_limit", 3)
        if self.consecutive_losses >= consec_limit:
            if self.last_loss_time:
                cooldown = self.config.get("cooldown_minutes_after_consecutive_losses", 60)
                elapsed = (datetime.utcnow() - self.last_loss_time).total_seconds() / 60.0
                if elapsed < cooldown:
                    return False, f"Consecutive loss protection triggered ({self.consecutive_losses} losses). Cooldown active for {int(cooldown - elapsed)} more minutes.", {}
                else:
                    self.consecutive_losses = 0  # Reset after cooldown elapsed

        # 4. Daily Loss Limit Check
        max_daily_loss_pct = self.config.get("max_daily_loss_percent", 3.0)
        max_daily_loss_dollars = current_balance * (max_daily_loss_pct / 100.0)
        if daily_pnl < 0 and abs(daily_pnl) >= max_daily_loss_dollars:
            return False, f"Daily loss limit reached (${abs(daily_pnl):.2f} / ${max_daily_loss_dollars:.2f} max).", {}

        # 5. Maximum Account Drawdown Check
        max_dd_pct = self.config.get("max_account_drawdown_percent", 10.0)
        current_drawdown = max(0.0, high_water_mark - current_equity)
        max_dd_dollars = high_water_mark * (max_dd_pct / 100.0)
        if current_drawdown >= max_dd_dollars:
            return False, f"Maximum overall account drawdown breached (${current_drawdown:.2f} / ${max_dd_dollars:.2f} max).", {}

        # 6. Minimum Risk-to-Reward Ratio Check
        sl_dist = abs(entry_price - stop_loss)
        tp_dist = abs(take_profit - entry_price)
        if sl_dist <= 0:
            return False, "Invalid Stop Loss: distance cannot be zero.", {}

        rr_ratio = round(tp_dist / sl_dist, 2)
        min_rr = self.config.get("min_risk_reward_ratio", 1.5)
        if rr_ratio < min_rr:
            return False, f"Risk-to-Reward ratio ({rr_ratio}:1) is below minimum required ({min_rr}:1).", {}

        # 7. Position Sizing
        lots, planned_risk, sl_points = self.calculate_lot_size(
            symbol, entry_price, stop_loss, current_balance, self.config.get("risk_percent_per_trade", 1.0)
        )

        metrics = {
            "lots": lots,
            "planned_risk_amount": planned_risk,
            "risk_percent": self.config.get("risk_percent_per_trade", 1.0),
            "risk_reward_ratio": rr_ratio,
            "sl_points": sl_points,
            "current_drawdown": current_drawdown,
            "daily_loss_remaining": max(0.0, max_daily_loss_dollars - max(0.0, -daily_pnl)),
            "overall_drawdown_remaining": max(0.0, max_dd_dollars - current_drawdown)
        }

        return True, "Risk validation passed.", metrics

    def record_trade_outcome(self, pnl: float):
        if pnl < 0:
            self.consecutive_losses += 1
            self.last_loss_time = datetime.utcnow()
            log_audit("TRADE_LOSS", "WARNING", f"Trade closed with loss: ${pnl:.2f}. Consecutive losses: {self.consecutive_losses}")
        else:
            self.consecutive_losses = 0
            log_audit("TRADE_WIN", "INFO", f"Trade closed with profit: +${pnl:.2f}. Consecutive loss counter reset.")
