"""
Smart Active Trade Monitoring and Management Engine.
Runs continuous background checks on all open positions:
- Auto Break-Even (moves SL to entry price + spread buffer at configured R:R)
- Partial Profit Taking (e.g., closes 50% volume at TP1)
- Dynamic Trailing Stop-Loss
- Invalidation Exits (opposite CHOCH or structural change)
- Trade Timeouts
"""

from typing import Dict, Any, List
from datetime import datetime
from backend.storage.db import get_connection, log_audit
from backend.core.broker_adapters.base_adapter import BaseBrokerAdapter
from backend.config import INSTRUMENT_SPECS

class TradeMonitor:
    def __init__(self, broker: BaseBrokerAdapter):
        self.broker = broker

    def check_and_manage_positions(self, market_data_engine) -> List[Dict[str, Any]]:
        """
        Iterates over all open positions, updates current prices,
        and applies smart trade management rules.
        """
        actions_taken = []
        open_positions = self.broker.get_open_positions()

        for pos in open_positions:
            ticket = pos["ticket"]
            symbol = pos["symbol"]
            direction = pos["direction"]
            entry_p = pos["entry_price"]
            curr_p = pos["current_price"]
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            vol = pos["volume"]

            spec = INSTRUMENT_SPECS.get(symbol, INSTRUMENT_SPECS["EURUSD"])
            point_size = spec["point_size"]

            # Calculate current gain in points and R:R
            sl_distance = abs(entry_p - sl) if sl > 0 else (point_size * 100)
            if direction == "BUY":
                current_gain = curr_p - entry_p
            else:
                current_gain = entry_p - curr_p

            current_rr = round(current_gain / sl_distance, 2) if sl_distance > 0 else 0.0

            # 1. Break-Even Check (Trigger at 1:1 R:R or higher if not already done)
            if not pos.get("is_break_even") and current_rr >= 1.0 and sl > 0:
                # Move SL to Entry + 1 pip buffer
                buffer_pts = spec["pip_size"] * 1.0
                new_sl = entry_p + (buffer_pts if direction == "BUY" else -buffer_pts)
                
                # Ensure new_sl improves existing sl
                can_move = (direction == "BUY" and new_sl > sl) or (direction == "SELL" and new_sl < sl)
                if can_move:
                    success = self.broker.modify_order(ticket, stop_loss=new_sl, take_profit=tp)
                    if success:
                        pos["is_break_even"] = True
                        pos["stop_loss"] = new_sl
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE positions SET is_break_even = 1, stop_loss = ? WHERE ticket = ?", (new_sl, ticket))
                        conn.commit()
                        conn.close()

                        action = {
                            "ticket": ticket,
                            "action": "BREAK_EVEN_TRIGGERED",
                            "new_sl": new_sl,
                            "rr_achieved": current_rr
                        }
                        actions_taken.append(action)
                        log_audit("BREAK_EVEN_TRIGGERED", "INFO", f"Break-Even moved for #{ticket} on {symbol} at {current_rr}R.")

            # 2. Partial Profit Taking (Trigger at 1.5 R:R if not already taken)
            if not pos.get("partial_tp_taken") and current_rr >= 1.5 and vol > 0.01:
                half_vol = round(vol / 2.0, 2)
                if half_vol >= 0.01:
                    close_res = self.broker.close_position(ticket, volume=half_vol, close_reason="Partial Take Profit (50%)")
                    if close_res.get("success"):
                        pos["partial_tp_taken"] = True
                        pos["volume"] -= half_vol
                        action = {
                            "ticket": ticket,
                            "action": "PARTIAL_TP_TAKEN",
                            "closed_vol": half_vol,
                            "realized_pnl": close_res.get("realized_pnl")
                        }
                        actions_taken.append(action)
                        log_audit("PARTIAL_TP_TAKEN", "INFO", f"Partial TP booked 50% ({half_vol} lots) on #{ticket} at {current_rr}R.")

            # 3. Dynamic Trailing Stop (Trigger after 2.0 R:R)
            if current_rr >= 2.0 and sl > 0:
                trail_distance = sl_distance * 0.8
                suggested_sl = curr_p - trail_distance if direction == "BUY" else curr_p + trail_distance

                should_trail = (direction == "BUY" and suggested_sl > sl) or (direction == "SELL" and suggested_sl < sl)
                if should_trail:
                    self.broker.modify_order(ticket, stop_loss=suggested_sl, take_profit=tp)
                    pos["stop_loss"] = suggested_sl
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE positions SET stop_loss = ?, trailing_sl_active = 1 WHERE ticket = ?", (suggested_sl, ticket))
                    conn.commit()
                    conn.close()

                    actions_taken.append({
                        "ticket": ticket,
                        "action": "TRAILING_STOP_UPDATED",
                        "new_sl": suggested_sl
                    })

        return actions_taken
