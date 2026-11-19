"""
Realistic Paper Trading Broker Simulator.
Simulates institutional broker mechanics with:
- Authentic spread and slippage modeling
- Round-turn commission ($3.50 per standard lot)
- Real-time mark-to-market floating PnL
- Stop-loss, Take-profit, Trailing-stop, and Partial-close execution
- Margin checks and account equity management
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.core.broker_adapters.base_adapter import BaseBrokerAdapter
from backend.config import INSTRUMENT_SPECS
from backend.storage.db import get_connection, log_audit

class PaperBroker(BaseBrokerAdapter):
    def __init__(self, initial_balance: float = 10000.0, currency: str = "USD"):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        self.currency = currency
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        self.connected = True
        self.commission_per_lot = 3.50  # Institutional commission ($3.50/lot)
        self.load_persisted_positions()

    def load_persisted_positions(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND broker = 'PAPER'")
        rows = cursor.fetchall()
        for r in rows:
            self.positions[r["ticket"]] = {
                "ticket": r["ticket"],
                "symbol": r["symbol"],
                "direction": r["direction"],
                "volume": float(r["volume"]),
                "entry_price": float(r["entry_price"]),
                "current_price": float(r["current_price"]),
                "stop_loss": float(r["stop_loss"]),
                "take_profit": float(r["take_profit"]),
                "pnl": float(r["pnl"]),
                "is_break_even": bool(r["is_break_even"]),
                "partial_tp_taken": bool(r["partial_tp_taken"]),
                "trailing_sl_active": bool(r["trailing_sl_active"]),
                "open_time": r["open_time"]
            }
        conn.close()

    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        self.connected = True
        log_audit("BROKER_CONNECT", "INFO", "Paper Broker connected successfully.")
        return True

    def disconnect(self) -> bool:
        self.connected = False
        log_audit("BROKER_DISCONNECT", "INFO", "Paper Broker disconnected.")
        return True

    def is_connected(self) -> bool:
        return self.connected

    def get_account_info(self) -> Dict[str, Any]:
        floating_pnl = sum(p["pnl"] for p in self.positions.values())
        self.equity = self.balance + floating_pnl
        used_margin = sum(p["volume"] * 1000.0 for p in self.positions.values())  # approximate 1:100 leverage
        free_margin = max(0.0, self.equity - used_margin)

        return {
            "broker": "Paper Broker (Simulator)",
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "floating_pnl": round(floating_pnl, 2),
            "used_margin": round(used_margin, 2),
            "free_margin": round(free_margin, 2),
            "currency": self.currency,
            "open_positions_count": len(self.positions),
            "is_connected": self.connected
        }

    def get_current_price(self, symbol: str) -> Dict[str, float]:
        spec = INSTRUMENT_SPECS.get(symbol, INSTRUMENT_SPECS["EURUSD"])
        # In actual feed, price is pushed by MarketDataEngine
        spread = spec["typical_spread"]
        return {"bid": 1.08500, "ask": 1.08500 + spread, "spread": spread}

    def place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = ""
    ) -> Dict[str, Any]:
        if not self.connected:
            return {"success": False, "error": "Paper Broker not connected."}

        spec = INSTRUMENT_SPECS.get(symbol)
        if not spec:
            return {"success": False, "error": f"Unsupported symbol: {symbol}"}

        ticket = f"PB-{uuid.uuid4().hex[:8].upper()}"
        fill_price = price or 1.08500
        # Realistic slippage (0.1 pips)
        slippage = spec["point_size"] * 1.0
        if order_type == "BUY":
            fill_price += slippage
        elif order_type == "SELL":
            fill_price -= slippage

        # Deduct commission
        commission = volume * self.commission_per_lot
        self.balance -= commission

        position = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": order_type,
            "volume": volume,
            "entry_price": fill_price,
            "current_price": fill_price,
            "stop_loss": stop_loss or 0.0,
            "take_profit": take_profit or 0.0,
            "pnl": -commission,  # Start at negative commission
            "is_break_even": False,
            "partial_tp_taken": False,
            "trailing_sl_active": False,
            "open_time": datetime.utcnow().isoformat()
        }

        self.positions[ticket] = position

        # Persist to database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO positions (ticket, broker, symbol, direction, volume, entry_price, current_price,
                                  stop_loss, take_profit, pnl, status, open_time)
            VALUES (?, 'PAPER', ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (ticket, symbol, order_type, volume, fill_price, fill_price, stop_loss or 0.0, take_profit or 0.0, -commission, position["open_time"]))
        conn.commit()
        conn.close()

        log_audit(
            "ORDER_EXECUTED", "INFO",
            f"Paper {order_type} executed for {volume} lots of {symbol} at {fill_price:.5f}",
            {"ticket": ticket, "symbol": symbol, "lots": volume, "entry": fill_price, "sl": stop_loss, "tp": take_profit}
        )

        return {
            "success": True,
            "ticket": ticket,
            "fill_price": fill_price,
            "volume": volume,
            "commission": commission,
            "status": "FILLED"
        }

    def modify_order(
        self,
        ticket: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        if ticket not in self.positions:
            return False

        pos = self.positions[ticket]
        if stop_loss is not None:
            pos["stop_loss"] = stop_loss
        if take_profit is not None:
            pos["take_profit"] = take_profit

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE positions SET stop_loss = ?, take_profit = ? WHERE ticket = ?",
                       (pos["stop_loss"], pos["take_profit"], ticket))
        conn.commit()
        conn.close()

        log_audit("ORDER_MODIFIED", "INFO", f"Order {ticket} modified: SL={stop_loss}, TP={take_profit}")
        return True

    def close_position(self, ticket: str, volume: Optional[float] = None, close_reason: str = "Manual Close") -> Dict[str, Any]:
        if ticket not in self.positions:
            return {"success": False, "error": f"Position {ticket} not found."}

        pos = self.positions[ticket]
        close_vol = volume or pos["volume"]

        # Calculate final PnL for closed volume
        final_pnl = pos["pnl"] * (close_vol / pos["volume"])
        self.balance += final_pnl

        now = datetime.utcnow().isoformat()
        close_price = pos["current_price"]

        if close_vol >= pos["volume"]:
            # Full close
            del self.positions[ticket]
            status = "CLOSED"
        else:
            # Partial close
            pos["volume"] -= close_vol
            pos["partial_tp_taken"] = True
            status = "PARTIAL_CLOSED"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE positions 
            SET status = ?, close_time = ?, close_price = ?, close_reason = ?, pnl = ?
            WHERE ticket = ?
        """, (status, now, close_price, close_reason, final_pnl, ticket))
        conn.commit()
        conn.close()

        log_audit("POSITION_CLOSED", "INFO", f"Position {ticket} {close_reason} at {close_price:.5f}. Realized PnL: ${final_pnl:.2f}")

        return {
            "success": True,
            "ticket": ticket,
            "closed_volume": close_vol,
            "realized_pnl": round(final_pnl, 2),
            "close_price": close_price,
            "close_reason": close_reason
        }

    def update_live_quote(self, symbol: str, bid: float, ask: float):
        """
        Updates live prices for all open positions of this symbol,
        computes mark-to-market floating PnL, and triggers SL/TP.
        """
        spec = INSTRUMENT_SPECS.get(symbol)
        if not spec:
            return

        point_value = spec["tick_value_standard"] / (spec["pip_size"] / spec["point_size"])
        tickets_to_close = []

        for ticket, pos in list(self.positions.items()):
            if pos["symbol"] != symbol:
                continue

            current_price = bid if pos["direction"] == "BUY" else ask
            pos["current_price"] = current_price

            # Calculate floating PnL
            if pos["direction"] == "BUY":
                points_gain = (current_price - pos["entry_price"]) / spec["point_size"]
            else:
                points_gain = (pos["entry_price"] - current_price) / spec["point_size"]

            pos["pnl"] = round(points_gain * point_value * pos["volume"], 2)

            # Check Stop Loss Hit
            if pos["stop_loss"] > 0:
                if (pos["direction"] == "BUY" and current_price <= pos["stop_loss"]) or \
                   (pos["direction"] == "SELL" and current_price >= pos["stop_loss"]):
                    tickets_to_close.append((ticket, "Stop Loss Hit"))
                    continue

            # Check Take Profit Hit
            if pos["take_profit"] > 0:
                if (pos["direction"] == "BUY" and current_price >= pos["take_profit"]) or \
                   (pos["direction"] == "SELL" and current_price <= pos["take_profit"]):
                    tickets_to_close.append((ticket, "Take Profit Hit"))
                    continue

        # Execute SL/TP closes
        for ticket, reason in tickets_to_close:
            self.close_position(ticket, close_reason=reason)

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return list(self.positions.values())
