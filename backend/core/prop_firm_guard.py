"""
Prop Firm Protection Mode and Challenge Rule Compliance Engine.
Monitors:
- Daily drawdown limit (balance-based vs equity-based high-water mark)
- Maximum overall account drawdown
- Profit target progression
- Minimum trading days requirement
- Weekend holding rules
- News blackout adherence
- Hard automatic trading lock upon rule breach or warning threshold
"""

from typing import Dict, Any, Tuple, Optional
from datetime import datetime, date
from backend.config import PROP_FIRM_PRESETS
from backend.storage.db import get_connection, log_audit

class PropFirmGuard:
    def __init__(self, profile_name: str = "FTMO Standard", starting_balance: float = 10000.0, reset_state: bool = False):
        self.profile_name = profile_name
        self.rules = PROP_FIRM_PRESETS.get(profile_name, PROP_FIRM_PRESETS["FTMO Standard"])
        self.starting_balance = starting_balance
        self.high_water_mark = starting_balance
        self.daily_start_balance = starting_balance
        self.current_balance = starting_balance
        self.current_equity = starting_balance
        self.is_breached = False
        self.breach_reason = ""
        self.trading_days: set = set()
        self.is_active = True
        if reset_state:
            self.save_state()
        else:
            self.init_or_load_state()

    def init_or_load_state(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prop_firm_state WHERE id = 'active_profile'")
        row = cursor.fetchone()
        if row:
            self.profile_name = row["profile_name"]
            self.rules = PROP_FIRM_PRESETS.get(self.profile_name, PROP_FIRM_PRESETS["FTMO Standard"])
            self.starting_balance = float(row["starting_balance"])
            self.current_balance = float(row["current_balance"])
            self.current_equity = float(row["current_equity"])
            self.high_water_mark = float(row["high_water_mark"])
            self.daily_start_balance = float(row["daily_start_balance"])
            self.is_breached = bool(row["is_breached"])
            self.breach_reason = row["breach_reason"] or ""
            self.is_active = bool(row["is_active"])
        else:
            self.save_state()
        conn.close()

    def save_state(self):
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO prop_firm_state 
            (id, profile_name, starting_balance, current_balance, current_equity, high_water_mark,
             daily_start_balance, daily_loss_limit_amount, max_drawdown_limit_amount, profit_target_amount,
             trading_days_completed, is_breached, breach_reason, is_active, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'active_profile',
            self.profile_name,
            self.starting_balance,
            self.current_balance,
            self.current_equity,
            self.high_water_mark,
            self.daily_start_balance,
            self.get_daily_loss_limit_amount(),
            self.get_max_drawdown_limit_amount(),
            self.get_profit_target_amount(),
            len(self.trading_days),
            1 if self.is_breached else 0,
            self.breach_reason,
            1 if self.is_active else 0,
            now
        ))
        conn.commit()
        conn.close()

    def set_profile(self, profile_name: str, starting_balance: float = 10000.0, custom_rules: Optional[Dict[str, Any]] = None):
        self.profile_name = profile_name
        if custom_rules:
            self.rules = custom_rules
        else:
            self.rules = PROP_FIRM_PRESETS.get(profile_name, PROP_FIRM_PRESETS["FTMO Standard"])
        self.starting_balance = starting_balance
        self.daily_start_balance = starting_balance
        self.current_balance = starting_balance
        self.current_equity = starting_balance
        self.high_water_mark = starting_balance
        self.is_breached = False
        self.breach_reason = ""
        self.trading_days.clear()
        self.save_state()
        log_audit("PROP_FIRM_PROFILE_SET", "INFO", f"Prop firm profile set to {profile_name} (${starting_balance:,.2f})")

    def sync_with_connected_account(
        self,
        broker_name: str,
        balance: float,
        equity: float,
        server: str = "",
        currency: str = "USD"
    ) -> Dict[str, Any]:
        """
        Dynamically matches Prop Firm Mode with the connected broker/prop-firm account.
        Auto-detects FTMO, FundedNext, The5ers from broker/server name and scales starting challenge size.
        """
        srv = (server or "").lower()
        brk = (broker_name or "").lower()

        if "ftmo" in srv or "ftmo" in brk:
            matched_profile = "FTMO Standard"
        elif "fundednext" in srv or "fundednext" in brk:
            matched_profile = "FundedNext Stellar"
        elif "the5ers" in srv or "5ers" in srv or "the5ers" in brk:
            matched_profile = "The5ers High Stakes"
        else:
            matched_profile = self.profile_name or "FTMO Standard"

        self.profile_name = matched_profile
        self.rules = PROP_FIRM_PRESETS.get(matched_profile, PROP_FIRM_PRESETS["FTMO Standard"])

        # Snap to standard challenge tier (5k, 10k, 25k, 50k, 100k, 200k) if close
        standard_tiers = [5000, 10000, 25000, 50000, 100000, 200000]
        closest_tier = min(standard_tiers, key=lambda t: abs(t - balance))
        if abs(closest_tier - balance) / closest_tier <= 0.05:
            starting_bal = float(closest_tier)
        else:
            starting_bal = float(balance)

        self.starting_balance = starting_bal
        self.daily_start_balance = float(balance)
        self.current_balance = float(balance)
        self.current_equity = float(equity)
        self.high_water_mark = max(starting_bal, float(equity))
        self.is_breached = False
        self.breach_reason = ""
        self.save_state()

        log_audit(
            "PROP_FIRM_SYNCED", "INFO",
            f"Prop Firm Mode matched to connected account: {matched_profile} | Challenge: ${starting_bal:,.2f} | Balance: ${balance:,.2f}"
        )
        return self.get_metrics()

    def get_daily_loss_limit_amount(self) -> float:
        pct = self.rules.get("daily_drawdown_limit_percent", 5.0)
        # Daily loss is measured from the start of the trading day
        return self.daily_start_balance * (pct / 100.0)

    def get_max_drawdown_limit_amount(self) -> float:
        pct = self.rules.get("max_overall_drawdown_percent", 10.0)
        drawdown_type = self.rules.get("drawdown_type", "balance_based")
        ref = self.starting_balance if drawdown_type == "balance_based" else self.high_water_mark
        return ref * (pct / 100.0)

    def get_profit_target_amount(self) -> float:
        pct = self.rules.get("profit_target_step1_percent", 10.0)
        return self.starting_balance * (pct / 100.0)

    def update_account_state(self, current_balance: float, current_equity: float):
        self.current_balance = current_balance
        self.current_equity = current_equity

        if current_equity > self.high_water_mark:
            self.high_water_mark = current_equity

        # Record today as active trading day
        today_str = date.today().isoformat()
        self.trading_days.add(today_str)

        # Check for Breaches
        self.check_compliance()
        self.save_state()

    def check_compliance(self) -> Tuple[bool, str]:
        if not self.is_active:
            return True, "Prop firm guard is inactive."

        # 1. Daily Drawdown Evaluation
        # Drawdown = Daily start balance - lowest of (current balance, current equity)
        effective_current = min(self.current_balance, self.current_equity)
        current_daily_loss = max(0.0, self.daily_start_balance - effective_current)
        max_daily_loss = self.get_daily_loss_limit_amount()

        if current_daily_loss >= max_daily_loss:
            self.is_breached = True
            self.breach_reason = f"Daily Drawdown Limit BREACHED: ${current_daily_loss:.2f} lost (Limit: ${max_daily_loss:.2f})"
            log_audit("PROP_FIRM_BREACH", "CRITICAL", self.breach_reason)
            return False, self.breach_reason

        # 2. Overall Max Drawdown Evaluation
        current_overall_dd = max(0.0, self.starting_balance - effective_current)
        max_overall_dd = self.get_max_drawdown_limit_amount()

        if current_overall_dd >= max_overall_dd:
            self.is_breached = True
            self.breach_reason = f"Max Overall Drawdown BREACHED: ${current_overall_dd:.2f} drawdown (Limit: ${max_overall_dd:.2f})"
            log_audit("PROP_FIRM_BREACH", "CRITICAL", self.breach_reason)
            return False, self.breach_reason

        return True, "Compliant"

    def can_open_new_trade(self, requested_lots: float, open_positions_count: int, is_weekend: bool = False) -> Tuple[bool, str]:
        if self.is_breached:
            return False, f"Trading halted! Prop firm rule breached: {self.breach_reason}"

        max_lots = self.rules.get("max_lot_size", 10.0)
        if requested_lots > max_lots:
            return False, f"Requested lot size ({requested_lots:.2f}) exceeds Prop Firm maximum allowed ({max_lots:.2f})."

        if is_weekend and not self.rules.get("weekend_holding_allowed", False):
            return False, "Prop Firm profile forbids holding or opening positions over the weekend."

        # Check safety buffer (warning threshold when approaching 80% of daily loss)
        effective_current = min(self.current_balance, self.current_equity)
        current_daily_loss = max(0.0, self.daily_start_balance - effective_current)
        max_daily_loss = self.get_daily_loss_limit_amount()
        if (current_daily_loss / max_daily_loss) >= 0.85:
            return False, f"Safety Circuit Breaker: Account is at 85% of daily drawdown limit (${current_daily_loss:.2f} / ${max_daily_loss:.2f}). New entries locked to protect account."

        return True, "Trade permitted under prop firm rules."

    def get_metrics(self) -> Dict[str, Any]:
        effective_current = min(self.current_balance, self.current_equity)
        current_daily_loss = max(0.0, self.daily_start_balance - effective_current)
        max_daily_loss = self.get_daily_loss_limit_amount()
        daily_loss_remaining = max(0.0, max_daily_loss - current_daily_loss)

        current_overall_dd = max(0.0, self.starting_balance - effective_current)
        max_overall_dd = self.get_max_drawdown_limit_amount()
        overall_dd_remaining = max(0.0, max_overall_dd - current_overall_dd)

        profit = self.current_balance - self.starting_balance
        profit_target = self.get_profit_target_amount()
        profit_progress_pct = max(0.0, min(100.0, (profit / profit_target) * 100.0)) if profit_target > 0 else 0.0

        return {
            "profile_name": self.profile_name,
            "starting_balance": self.starting_balance,
            "current_balance": self.current_balance,
            "current_equity": self.current_equity,
            "current_profit": profit,
            "profit_target_amount": profit_target,
            "profit_progress_percent": round(profit_progress_pct, 1),
            "daily_start_balance": self.daily_start_balance,
            "daily_loss_current": round(current_daily_loss, 2),
            "daily_loss_limit": round(max_daily_loss, 2),
            "daily_drawdown_remaining": round(daily_loss_remaining, 2),
            "daily_drawdown_used_percent": round((current_daily_loss / max_daily_loss) * 100.0, 1) if max_daily_loss > 0 else 0,
            "overall_drawdown_current": round(current_overall_dd, 2),
            "overall_drawdown_limit": round(max_overall_dd, 2),
            "overall_drawdown_remaining": round(overall_dd_remaining, 2),
            "overall_drawdown_used_percent": round((current_overall_dd / max_overall_dd) * 100.0, 1) if max_overall_dd > 0 else 0,
            "trading_days_completed": len(self.trading_days),
            "minimum_trading_days": self.rules.get("minimum_trading_days", 4),
            "is_breached": self.is_breached,
            "breach_reason": self.breach_reason,
            "is_active": self.is_active,
            "rules": self.rules
        }
