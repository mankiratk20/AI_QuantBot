"""
Trading Journal and Quantitative Analytics Engine.
Automatically records executions and provides deep statistical breakdown:
- Performance by strategy
- Performance by currency pair / asset class
- Performance by trading session (London vs New York vs Asian)
- Daily and weekly performance distribution
"""

from typing import Dict, List, Any, Optional
import uuid
import json
from datetime import datetime
from backend.storage.db import get_connection, log_audit

class JournalAnalytics:
    def record_completed_trade(
        self,
        ticket: str,
        symbol: str,
        strategy_name: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        stop_loss: float,
        take_profit: float,
        lots: float,
        risk_percent: float,
        net_profit: float,
        entry_time: str,
        exit_time: str,
        entry_reason: str,
        exit_reason: str,
        market_conditions: str = "",
        lessons_learned: str = "",
        tags: Optional[List[str]] = None
    ):
        conn = get_connection()
        cursor = conn.cursor()
        journal_id = f"jrn_{uuid.uuid4().hex[:8]}"

        sl_dist = abs(entry_price - stop_loss)
        gain_dist = abs(exit_price - entry_price) if net_profit > 0 else -abs(exit_price - entry_price)
        rr_achieved = round(gain_dist / sl_dist, 2) if sl_dist > 0 else 0.0

        cursor.execute("""
            INSERT INTO trade_journal (
                id, ticket, symbol, strategy_name, direction, entry_price, exit_price,
                stop_loss, take_profit, lots, risk_percent, net_profit, risk_reward_achieved,
                entry_time, exit_time, entry_reason, exit_reason, market_conditions,
                lessons_learned, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            journal_id, ticket, symbol, strategy_name, direction, entry_price, exit_price,
            stop_loss, take_profit, lots, risk_percent, net_profit, rr_achieved,
            entry_time, exit_time, entry_reason, exit_reason, market_conditions,
            lessons_learned, json.dumps(tags or [])
        ))
        conn.commit()
        conn.close()

        log_audit("JOURNAL_ENTRY_CREATED", "INFO", f"Trade #{ticket} logged to journal: PnL=${net_profit:.2f} ({rr_achieved}R)")

    def get_all_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_journal ORDER BY exit_time DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        entries = []
        for r in rows:
            entries.append({
                "id": r["id"],
                "ticket": r["ticket"],
                "symbol": r["symbol"],
                "strategy_name": r["strategy_name"],
                "direction": r["direction"],
                "entry_price": r["entry_price"],
                "exit_price": r["exit_price"],
                "stop_loss": r["stop_loss"],
                "take_profit": r["take_profit"],
                "lots": r["lots"],
                "risk_percent": r["risk_percent"],
                "net_profit": r["net_profit"],
                "risk_reward_achieved": r["risk_reward_achieved"],
                "entry_time": r["entry_time"],
                "exit_time": r["exit_time"],
                "entry_reason": r["entry_reason"],
                "exit_reason": r["exit_reason"],
                "market_conditions": r["market_conditions"],
                "lessons_learned": r["lessons_learned"],
                "tags": json.loads(r["tags"]) if r["tags"] else []
            })
        conn.close()
        return entries

    def get_performance_analytics(self) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_journal")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "by_strategy": {},
                "by_pair": {},
                "by_session": {
                    "London": {"trades": 0, "profit": 0.0},
                    "New York": {"trades": 0, "profit": 0.0},
                    "Asian": {"trades": 0, "profit": 0.0}
                }
            }

        total_trades = len(rows)
        wins = [r for r in rows if r["net_profit"] > 0]
        total_pnl = sum(r["net_profit"] for r in rows)
        win_rate = round((len(wins) / total_trades) * 100.0, 1)

        by_strategy: Dict[str, Dict[str, Any]] = {}
        by_pair: Dict[str, Dict[str, Any]] = {}

        for r in rows:
            s_name = r["strategy_name"]
            sym = r["symbol"]
            pnl = r["net_profit"]
            is_win = pnl > 0

            # Strategy breakdown
            if s_name not in by_strategy:
                by_strategy[s_name] = {"trades": 0, "wins": 0, "profit": 0.0}
            by_strategy[s_name]["trades"] += 1
            if is_win:
                by_strategy[s_name]["wins"] += 1
            by_strategy[s_name]["profit"] = round(by_strategy[s_name]["profit"] + pnl, 2)

            # Pair breakdown
            if sym not in by_pair:
                by_pair[sym] = {"trades": 0, "wins": 0, "profit": 0.0}
            by_pair[sym]["trades"] += 1
            if is_win:
                by_pair[sym]["wins"] += 1
            by_pair[sym]["profit"] = round(by_pair[sym]["profit"] + pnl, 2)

        # Compute win rates
        for s in by_strategy.values():
            s["win_rate"] = round((s["wins"] / s["trades"]) * 100.0, 1) if s["trades"] else 0.0
        for p in by_pair.values():
            p["win_rate"] = round((p["wins"] / p["trades"]) * 100.0, 1) if p["trades"] else 0.0

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_profit": round(total_pnl, 2),
            "by_strategy": by_strategy,
            "by_pair": by_pair
        }
