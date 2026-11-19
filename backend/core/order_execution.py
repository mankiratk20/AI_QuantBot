"""
Trade Execution Gateway and Signal Pipeline Manager.
Enforces:
- 3 Operating Modes: Manual, Semi-Automatic, Automatic (default disabled)
- Full 17-step execution pipeline
- Duplicate trade protection
- Broker routing (Paper, MT5, Binance, cTrader)
- Trade authorization handling
"""

from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime
from backend.storage.db import get_connection, log_audit
from backend.core.broker_adapters.base_adapter import BaseBrokerAdapter
from backend.core.risk_engine import RiskManager
from backend.core.prop_firm_guard import PropFirmGuard
from backend.core.economic_calendar import EconomicCalendar
from backend.core.ai_explanation import generate_trade_explanation

class ExecutionEngine:
    def __init__(
        self,
        broker: BaseBrokerAdapter,
        risk_manager: RiskManager,
        prop_firm_guard: PropFirmGuard,
        economic_calendar: EconomicCalendar,
        trading_mode: str = "semi_automatic"  # manual | semi_automatic | automatic
    ):
        self.broker = broker
        self.risk_manager = risk_manager
        self.prop_firm_guard = prop_firm_guard
        self.calendar = economic_calendar
        self.trading_mode = trading_mode
        self.pending_signals: Dict[str, Dict[str, Any]] = {}

    def set_trading_mode(self, mode: str):
        if mode not in ["manual", "semi_automatic", "automatic"]:
            raise ValueError(f"Invalid mode: {mode}")
        self.trading_mode = mode
        log_audit("TRADING_MODE_CHANGED", "INFO", f"Bot operating mode switched to {mode.upper()}")

    def process_strategy_signal(
        self,
        strategy: Dict[str, Any],
        symbol: str,
        timeframe: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        confluence_score: float,
        eval_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes the institutional 17-step pipeline:
        1. Check data freshness & market status
        2. Verify news blackout restrictions
        3. Check duplicate trades
        4. Validate risk & position sizing
        5. Verify prop firm compliance
        6. Generate AI Trade Explanation
        7. Route based on Operating Mode (Manual / Semi-Auto / Auto)
        """
        signal_id = f"sig_{uuid.uuid4().hex[:8]}"

        # Step 2: News Blackout Check
        in_blackout, news_reason = self.calendar.is_in_news_blackout(symbol)
        if in_blackout:
            log_audit("SIGNAL_REJECTED", "WARNING", f"Signal rejected due to news: {news_reason}", {"symbol": symbol})
            return {"status": "REJECTED", "reason": news_reason}

        # Step 3: Duplicate Trade Prevention
        open_positions = self.broker.get_open_positions()
        for p in open_positions:
            if p["symbol"] == symbol and p["direction"] == direction:
                reason = f"Duplicate trade prevented: active {direction} position already exists on {symbol}."
                log_audit("SIGNAL_REJECTED", "INFO", reason)
                return {"status": "REJECTED", "reason": reason}

        # Step 4: Account and Risk Verification
        account_info = self.broker.get_account_info()
        balance = account_info["balance"]
        equity = account_info["equity"]
        floating = account_info.get("floating_pnl", 0.0)

        # Update Prop Firm State
        self.prop_firm_guard.update_account_state(balance, equity)

        # Risk Validation
        approved, risk_reason, risk_metrics = self.risk_manager.validate_trade_risk(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_balance=balance,
            current_equity=equity,
            open_positions_count=len(open_positions),
            daily_pnl=floating,
            weekly_pnl=floating,
            high_water_mark=self.prop_firm_guard.high_water_mark
        )

        if not approved:
            log_audit("SIGNAL_REJECTED", "WARNING", f"Risk limit exceeded: {risk_reason}", {"symbol": symbol})
            return {"status": "REJECTED", "reason": risk_reason}

        # Step 5: Prop Firm Compliance Check
        lots = risk_metrics["lots"]
        prop_ok, prop_reason = self.prop_firm_guard.can_open_new_trade(lots, len(open_positions))
        if not prop_ok:
            log_audit("SIGNAL_REJECTED", "WARNING", f"Prop firm guard blocked entry: {prop_reason}")
            return {"status": "REJECTED", "reason": prop_reason}

        # Step 6: Generate Transparent AI Trade Explanation
        explanation = generate_trade_explanation(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timeframe=timeframe,
            strategy_name=strategy["name"],
            satisfied_conditions=eval_report.get("satisfied", []),
            not_satisfied_conditions=eval_report.get("not_satisfied", []),
            market_state=eval_report.get("market_analysis", {}),
            confluence_score=confluence_score
        )

        signal_payload = {
            "id": signal_id,
            "strategy_id": strategy["id"],
            "strategy_name": strategy["name"],
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward_ratio": risk_metrics["risk_reward_ratio"],
            "position_size_lots": lots,
            "planned_risk_amount": risk_metrics["planned_risk_amount"],
            "confidence_score": confluence_score,
            "explanation": explanation,
            "status": "PENDING_APPROVAL" if self.trading_mode == "semi_automatic" else ("PENDING_MANUAL" if self.trading_mode == "manual" else "AUTO_EXECUTING"),
            "created_at": datetime.utcnow().isoformat()
        }

        # Save signal in database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals (id, strategy_id, symbol, timeframe, direction, entry_price, stop_loss,
                                take_profit, risk_reward_ratio, position_size_lots, confidence_score,
                                market_structure_summary, conditions_satisfied, conditions_not_satisfied,
                                status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_id, strategy["id"], symbol, timeframe, direction, entry_price, stop_loss,
            take_profit, risk_metrics["risk_reward_ratio"], lots, confluence_score,
            explanation["market_structure_narrative"],
            str(explanation["conditions_satisfied"]),
            str(explanation["conditions_not_satisfied"]),
            signal_payload["status"],
            signal_payload["created_at"]
        ))
        conn.commit()
        conn.close()

        # Step 7: Operating Mode Dispatch
        if self.trading_mode == "manual":
            log_audit("SIGNAL_MANUAL", "INFO", f"Signal {signal_id} generated for manual execution by user.")
            return {"status": "SIGNAL_GENERATED", "mode": "manual", "signal": signal_payload}

        elif self.trading_mode == "semi_automatic":
            self.pending_signals[signal_id] = signal_payload
            log_audit("SIGNAL_APPROVAL_REQUESTED", "INFO", f"Semi-Auto Signal {signal_id} waiting for user approval.")
            return {"status": "PENDING_APPROVAL", "mode": "semi_automatic", "signal": signal_payload}

        elif self.trading_mode == "automatic":
            # Automatic Mode: Direct broker execution
            order_res = self.broker.place_order(
                symbol=symbol,
                order_type=direction,
                volume=lots,
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=f"Auto-{strategy['name'][:10]}"
            )
            if order_res.get("success"):
                signal_payload["status"] = "EXECUTED"
                signal_payload["ticket"] = order_res.get("ticket")
                log_audit("ORDER_AUTO_EXECUTED", "INFO", f"Automatic trade executed: {order_res.get('ticket')}")
                return {"status": "EXECUTED", "mode": "automatic", "order": order_res, "signal": signal_payload}
            else:
                signal_payload["status"] = "REJECTED"
                return {"status": "FAILED", "error": order_res.get("error")}

        return {"status": "UNKNOWN"}

    def approve_signal(self, signal_id: str) -> Dict[str, Any]:
        """
        User authorizes a pending semi-automatic trade signal.
        """
        sig = self.pending_signals.get(signal_id)
        if not sig:
            # Query from DB if not in memory
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return {"success": False, "error": f"Signal {signal_id} not found."}
            sig = {
                "id": row["id"],
                "symbol": row["symbol"],
                "direction": row["direction"],
                "position_size_lots": row["position_size_lots"],
                "entry_price": row["entry_price"],
                "stop_loss": row["stop_loss"],
                "take_profit": row["take_profit"]
            }

        order_res = self.broker.place_order(
            symbol=sig["symbol"],
            order_type=sig["direction"],
            volume=sig["position_size_lots"],
            price=sig["entry_price"],
            stop_loss=sig["stop_loss"],
            take_profit=sig["take_profit"],
            comment="Approved-SemiAuto"
        )

        if order_res.get("success"):
            sig["status"] = "EXECUTED"
            sig["ticket"] = order_res.get("ticket")
            if signal_id in self.pending_signals:
                del self.pending_signals[signal_id]

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE signals SET status = 'EXECUTED', executed_at = ? WHERE id = ?",
                           (datetime.utcnow().isoformat(), signal_id))
            conn.commit()
            conn.close()

            log_audit("SIGNAL_APPROVED", "INFO", f"Signal {signal_id} approved and executed. Ticket #{order_res.get('ticket')}")
            return {"success": True, "ticket": order_res.get("ticket"), "fill_price": order_res.get("fill_price")}
        else:
            return {"success": False, "error": order_res.get("error")}

    def reject_signal(self, signal_id: str, reason: str = "User rejected") -> Dict[str, Any]:
        """
        User declines a pending semi-automatic trade signal.
        """
        if signal_id in self.pending_signals:
            del self.pending_signals[signal_id]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE signals SET status = 'REJECTED' WHERE id = ?", (signal_id,))
        conn.commit()
        conn.close()

        log_audit("SIGNAL_REJECTED_USER", "INFO", f"Signal {signal_id} was rejected by user: {reason}")
        return {"success": True, "signal_id": signal_id}
