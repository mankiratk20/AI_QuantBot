"""
Deterministic User Strategy Builder and Execution Engine.
Allows users to construct strategies using Price Action, SMC, ICT,
Support/Resistance, Trend Following, and Indicator conditions with nested AND/OR logic.
The bot executes strictly according to user-defined rules.
"""

from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import json
import uuid
from datetime import datetime
from backend.storage.db import get_connection, log_audit
from backend.core.smc_engine import analyze_market_state
from backend.core.indicators import calculate_ema, calculate_sma, calculate_rsi, calculate_macd, calculate_atr

# Built-in Strategy Templates available for user activation or customization
DEFAULT_PRESET_STRATEGIES = [
    {
        "id": "smc_liquidity_fvg_long",
        "name": "ICT / SMC Liquidity Sweep & FVG Retest",
        "description": "Smart Money strategy buying on sell-side liquidity sweep followed by bullish CHOCH and Fair Value Gap fill.",
        "strategy_type": "Smart Money Concepts (SMC)",
        "instruments": ["EURUSD", "GBPUSD", "XAUUSD"],
        "timeframes": ["15M"],
        "sessions": ["London", "New York", "London-NY Overlap"],
        "risk_settings": {
            "risk_percent": 1.0,
            "min_risk_reward": 2.0,
            "max_spread_pips": 2.5,
            "max_trades_per_day": 4,
            "trailing_sl_enabled": True,
            "break_even_rr": 1.0,
            "partial_tp_rr": 1.5,
            "partial_tp_percent": 50
        },
        "rules": {
            "operator": "AND",
            "conditions": [
                {"category": "market_structure", "field": "trend", "operator": "!=", "value": "BEARISH"},
                {"category": "smc", "field": "bullish_choch_present", "operator": "==", "value": True},
                {"category": "indicator", "field": "rsi", "operator": "<=", "value": 65}
            ]
        },
        "is_active": 1
    },
    {
        "id": "gold_order_block_breakout",
        "name": "XAUUSD Institutional Order Block Trend",
        "description": "High-probability Gold strategy entering on 1H Bullish Order Block mitigation with 5M confirmation.",
        "strategy_type": "Institutional Order Block",
        "instruments": ["XAUUSD"],
        "timeframes": ["15M"],
        "sessions": ["London", "New York"],
        "risk_settings": {
            "risk_percent": 1.0,
            "min_risk_reward": 2.5,
            "max_spread_pips": 3.0,
            "max_trades_per_day": 3,
            "trailing_sl_enabled": True,
            "break_even_rr": 1.2,
            "partial_tp_rr": 2.0,
            "partial_tp_percent": 50
        },
        "rules": {
            "operator": "AND",
            "conditions": [
                {"category": "smc", "field": "bullish_ob_mitigated", "operator": "==", "value": True},
                {"category": "indicator", "field": "ema_20_above_50", "operator": "==", "value": True}
            ]
        },
        "is_active": 1
    },
    {
        "id": "trend_pullback_ema_rsi",
        "name": "Trend Following Dynamic Pullback",
        "description": "Classic trend-following strategy using EMA 20/50 alignment with RSI dynamic dip entry.",
        "strategy_type": "Trend Following",
        "instruments": ["EURUSD", "GBPUSD", "GBPJPY", "BTCUSD"],
        "timeframes": ["1H", "4H"],
        "sessions": ["London", "New York", "Tokyo"],
        "risk_settings": {
            "risk_percent": 1.0,
            "min_risk_reward": 1.8,
            "max_spread_pips": 2.0,
            "max_trades_per_day": 5,
            "trailing_sl_enabled": True,
            "break_even_rr": 1.0,
            "partial_tp_rr": 1.5,
            "partial_tp_percent": 50
        },
        "rules": {
            "operator": "AND",
            "conditions": [
                {"category": "indicator", "field": "ema_20_above_50", "operator": "==", "value": True},
                {"category": "indicator", "field": "rsi", "operator": "<=", "value": 52},
                {"category": "market_structure", "field": "trend", "operator": "!=", "value": "BEARISH"}
            ]
        },
        "is_active": 1
    }
]

class StrategyEngine:
    def __init__(self):
        self.ensure_default_strategies()

    def ensure_default_strategies(self):
        conn = get_connection()
        cursor = conn.cursor()
        for strat in DEFAULT_PRESET_STRATEGIES:
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT OR REPLACE INTO strategies (id, name, description, strategy_type, instruments, timeframes, sessions, rules, risk_settings, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strat["id"],
                    strat["name"],
                    strat["description"],
                    strat["strategy_type"],
                    json.dumps(strat["instruments"]),
                    json.dumps(strat["timeframes"]),
                    json.dumps(strat["sessions"]),
                    json.dumps(strat["rules"]),
                    json.dumps(strat["risk_settings"]),
                    strat["is_active"],
                    now,
                    now
                )
            )
        conn.commit()
        conn.close()

    def get_all_strategies(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
                """
                SELECT * FROM strategies 
                WHERE user_id = 'SYSTEM' OR user_id = ? 
                ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END, updated_at DESC
                """,
                (user_id, user_id)
            )
        else:
            cursor.execute("SELECT * FROM strategies WHERE user_id = 'SYSTEM' ORDER BY updated_at DESC")
        
        rows = cursor.fetchall()
        strategies = []
        for r in rows:
            strat_user = r["user_id"] if "user_id" in r.keys() and r["user_id"] else "SYSTEM"
            strategies.append({
                "id": r["id"],
                "user_id": strat_user,
                "is_personal": strat_user != "SYSTEM",
                "is_owner": bool(user_id and strat_user == user_id),
                "name": r["name"],
                "description": r["description"],
                "strategy_type": r["strategy_type"],
                "instruments": json.loads(r["instruments"]),
                "timeframes": json.loads(r["timeframes"]),
                "sessions": json.loads(r["sessions"]),
                "rules": json.loads(r["rules"]),
                "risk_settings": json.loads(r["risk_settings"]),
                "is_active": bool(r["is_active"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"]
            })
        conn.close()
        return strategies

    def save_strategy(self, data: Dict[str, Any], user_id: Optional[str] = None) -> str:
        conn = get_connection()
        cursor = conn.cursor()
        strat_id = data.get("id") or f"strat_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        target_user = user_id or data.get("user_id") or "SYSTEM"

        cursor.execute("SELECT id, user_id FROM strategies WHERE id = ?", (strat_id,))
        existing_row = cursor.fetchone()

        instruments = json.dumps(data.get("instruments", ["EURUSD"]))
        timeframes = json.dumps(data.get("timeframes", ["15M"]))
        sessions = json.dumps(data.get("sessions", ["London", "New York"]))
        rules = json.dumps(data.get("rules", {"operator": "AND", "conditions": []}))
        risk_settings = json.dumps(data.get("risk_settings", {}))
        is_active = 1 if data.get("is_active", True) else 0

        if existing_row:
            owner_id = existing_row["user_id"] if "user_id" in existing_row.keys() and existing_row["user_id"] else "SYSTEM"
            # Protect other users' personal strategies
            if owner_id != "SYSTEM" and user_id and owner_id != user_id:
                conn.close()
                raise PermissionError("Access denied: You cannot modify another trader's personal strategy.")

            cursor.execute(
                """
                UPDATE strategies 
                SET name = ?, description = ?, strategy_type = ?, instruments = ?, timeframes = ?,
                    sessions = ?, rules = ?, risk_settings = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    data.get("name", "Custom Strategy"),
                    data.get("description", ""),
                    data.get("strategy_type", "Price Action"),
                    instruments, timeframes, sessions, rules, risk_settings, is_active, now, strat_id
                )
            )
        else:
            cursor.execute(
                """
                INSERT INTO strategies (id, user_id, name, description, strategy_type, instruments, timeframes, sessions, rules, risk_settings, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strat_id,
                    target_user,
                    data.get("name", "Custom Strategy"),
                    data.get("description", ""),
                    data.get("strategy_type", "Price Action"),
                    instruments, timeframes, sessions, rules, risk_settings, is_active, now, now
                )
            )

        conn.commit()
        conn.close()

        action = "STRATEGY_UPDATED" if existing_row else "STRATEGY_CREATED"
        log_audit(action, "INFO", f"Strategy '{data.get('name')}' saved successfully.", {"strategy_id": strat_id, "user_id": target_user})
        return strat_id

    def delete_strategy(self, strategy_id: str, user_id: Optional[str] = None) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id FROM strategies WHERE id = ?", (strategy_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False

        owner = row["user_id"] if "user_id" in row.keys() and row["user_id"] else "SYSTEM"
        if owner == "SYSTEM":
            conn.close()
            raise PermissionError("System preset institutional strategies cannot be deleted.")
        if user_id and owner != user_id:
            conn.close()
            raise PermissionError("Access denied: You can only delete your own personal strategies.")

        cursor.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        conn.commit()
        conn.close()
        log_audit("STRATEGY_DELETED", "INFO", f"Strategy {strategy_id} deleted by user {user_id}.")
        return True

    def set_active_state(self, strategy_id: str, is_active: bool, user_id: Optional[str] = None):
        conn = get_connection()
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT user_id FROM strategies WHERE id = ?", (strategy_id,))
            row = cursor.fetchone()
            if row:
                owner = row["user_id"] if "user_id" in row.keys() and row["user_id"] else "SYSTEM"
                if owner != "SYSTEM" and owner != user_id:
                    conn.close()
                    raise PermissionError("Access denied: Cannot toggle another trader's private strategy.")

        cursor.execute("UPDATE strategies SET is_active = ?, updated_at = ? WHERE id = ?", 
                       (1 if is_active else 0, datetime.now().isoformat(), strategy_id))
        conn.commit()
        conn.close()
        log_audit("STRATEGY_TOGGLED", "INFO", f"Strategy {strategy_id} active status set to {is_active}.")

    def evaluate_strategy(self, strategy: Dict[str, Any], df: pd.DataFrame, current_spread_pips: float = 1.0) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluates a strategy against current market data.
        Returns:
            - matched (bool): Whether all mandatory conditions are satisfied.
            - evaluation_report (dict): Detailed breakdown of conditions evaluated,
              satisfied vs not satisfied, and market state metrics.
        """
        rules = strategy.get("rules", {})
        risk_settings = strategy.get("risk_settings", {})

        # 1. Check spread restriction
        max_spread = risk_settings.get("max_spread_pips", 5.0)
        if current_spread_pips > max_spread:
            return False, {
                "matched": False,
                "rejection_reason": f"Current spread ({current_spread_pips:.2f} pips) exceeds strategy maximum ({max_spread:.2f} pips).",
                "satisfied": [],
                "not_satisfied": [{"condition": "max_spread_pips", "current": current_spread_pips, "limit": max_spread}]
            }

        # 2. Extract technical indicators & SMC state
        market_analysis = analyze_market_state(df)
        close_series = df['close']
        ema_20 = calculate_ema(close_series, 20).iloc[-1]
        ema_50 = calculate_ema(close_series, 50).iloc[-1]
        ema_200 = calculate_ema(close_series, 200).iloc[-1] if len(close_series) >= 200 else ema_50
        rsi = calculate_rsi(close_series, 14).iloc[-1]
        macd_data = calculate_macd(close_series)
        macd_val = macd_data["macd"].iloc[-1]
        macd_sig = macd_data["signal"].iloc[-1]

        # SMC feature flags
        has_bullish_choch = any(c["type"] == "BULLISH_CHOCH" for c in market_analysis["chochs"])
        has_bearish_choch = any(c["type"] == "BEARISH_CHOCH" for c in market_analysis["chochs"])
        has_bullish_fvg = any(f["type"] == "BULLISH_FVG" and not f["is_mitigated"] for f in market_analysis["fvgs"])
        has_bearish_fvg = any(f["type"] == "BEARISH_FVG" and not f["is_mitigated"] for f in market_analysis["fvgs"])
        has_bullish_ob = any(o["type"] == "BULLISH_OB" and not o["is_mitigated"] for o in market_analysis["order_blocks"])
        has_bearish_ob = any(o["type"] == "BEARISH_OB" and not o["is_mitigated"] for o in market_analysis["order_blocks"])
        recent_patterns = [p["pattern"] for p in market_analysis["candlestick_patterns"]]

        context = {
            "trend": market_analysis["trend"],
            "structure_bias": market_analysis["structure_bias"],
            "bullish_choch_present": has_bullish_choch,
            "bearish_choch_present": has_bearish_choch,
            "active_bullish_fvg": has_bullish_fvg,
            "active_bearish_fvg": has_bearish_fvg,
            "bullish_ob_mitigated": has_bullish_ob,
            "bearish_ob_mitigated": has_bearish_ob,
            "candlestick": recent_patterns,
            "rsi": float(rsi),
            "ema_20_above_50": bool(ema_20 > ema_50),
            "ema_50_above_200": bool(ema_50 > ema_200),
            "macd_above_signal": bool(macd_val > macd_sig),
            "last_price": market_analysis["last_price"]
        }

        # 3. Recursively evaluate rules tree
        satisfied_conditions = []
        not_satisfied_conditions = []

        def eval_node(node: Dict[str, Any]) -> bool:
            operator = node.get("operator", "AND").upper()
            conditions = node.get("conditions", [])

            if not conditions:
                return True

            results = []
            for item in conditions:
                if "conditions" in item:
                    # Nested sub-tree
                    sub_res = eval_node(item)
                    results.append(sub_res)
                else:
                    field = item.get("field")
                    op = item.get("operator", "==")
                    expected = item.get("value")
                    actual = context.get(field)

                    passed = False
                    if op == "==":
                        passed = (actual == expected)
                    elif op == "!=":
                        passed = (actual != expected)
                    elif op == ">=":
                        passed = (actual is not None and actual >= expected)
                    elif op == "<=":
                        passed = (actual is not None and actual <= expected)
                    elif op == ">":
                        passed = (actual is not None and actual > expected)
                    elif op == "<":
                        passed = (actual is not None and actual < expected)
                    elif op == "in":
                        if isinstance(actual, list):
                            passed = any(x in expected for x in actual)
                        else:
                            passed = (actual in expected)

                    cond_summary = {
                        "field": field,
                        "operator": op,
                        "expected": expected,
                        "actual": actual,
                        "passed": passed
                    }

                    if passed:
                        satisfied_conditions.append(cond_summary)
                    else:
                        not_satisfied_conditions.append(cond_summary)

                    results.append(passed)

            if operator == "AND":
                return all(results)
            elif operator == "OR":
                return any(results)
            return False

        strategy_matched = eval_node(rules)

        # Determine signal direction
        direction = "BUY"
        if "BEARISH" in market_analysis["trend"] or has_bearish_choch or has_bearish_fvg:
            if context.get("rsi", 50) > 55 or has_bearish_ob:
                direction = "SELL"

        return strategy_matched, {
            "matched": strategy_matched,
            "direction": direction,
            "context": context,
            "market_analysis": market_analysis,
            "satisfied": satisfied_conditions,
            "not_satisfied": not_satisfied_conditions
        }
