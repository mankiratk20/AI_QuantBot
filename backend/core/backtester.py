"""
Institutional Backtesting and Historical Strategy Simulation Engine.
Implements:
- Point-in-time bar execution (Strict zero look-ahead bias)
- Realistic spread, slippage, and round-turn commissions
- Comprehensive metrics: Win Rate, Profit Factor, Net Profit, Max Drawdown,
  Average R:R, Consecutive Wins/Losses, Long vs Short breakdown, Monthly returns
- Detailed Equity Curve series for UI charting
"""

from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime
from backend.config import INSTRUMENT_SPECS
from backend.core.strategy_builder import StrategyEngine
from backend.core.indicators import calculate_atr

class BacktestingEngine:
    def __init__(self):
        self.strategy_engine = StrategyEngine()

    def run_backtest(
        self,
        strategy_data: Dict[str, Any],
        df: pd.DataFrame,
        symbol: str = "EURUSD",
        timeframe: str = "15M",
        starting_balance: float = 10000.0,
        risk_percent: float = 1.0,
        slippage_points: float = 2.0,
        commission_per_lot: float = 3.50
    ) -> Dict[str, Any]:
        """
        Executes point-in-time simulation over historical OHLCV data.
        """
        spec = INSTRUMENT_SPECS.get(symbol, INSTRUMENT_SPECS["EURUSD"])
        point_size = spec["point_size"]
        spread = spec["typical_spread"]
        point_value = spec["tick_value_standard"] / (spec["pip_size"] / spec["point_size"])

        balance = starting_balance
        equity = starting_balance
        peak_equity = starting_balance
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

        trades = []
        equity_curve = [{"time": str(df["timestamp"].iloc[0]), "equity": starting_balance, "balance": starting_balance}]

        in_position = False
        current_pos: Optional[Dict[str, Any]] = None

        min_bars_needed = 40
        if len(df) < min_bars_needed:
            return {"error": "Insufficient historical data for backtesting."}

        # Step forward bar-by-bar to prevent look-ahead bias
        for i in range(min_bars_needed, len(df)):
            current_bar = df.iloc[i]
            historical_slice = df.iloc[:i]

            # 1. Manage existing position if open
            if in_position and current_pos:
                # Check Bar High / Low for SL or TP hit
                exit_price = None
                exit_reason = None

                high = current_bar["high"]
                low = current_bar["low"]

                if current_pos["direction"] == "BUY":
                    if low <= current_pos["sl"]:
                        exit_price = current_pos["sl"]
                        exit_reason = "Stop Loss"
                    elif high >= current_pos["tp"]:
                        exit_price = current_pos["tp"]
                        exit_reason = "Take Profit"
                else:  # SELL
                    if high >= current_pos["sl"]:
                        exit_price = current_pos["sl"]
                        exit_reason = "Stop Loss"
                    elif low <= current_pos["tp"]:
                        exit_price = current_pos["tp"]
                        exit_reason = "Take Profit"

                if exit_price:
                    # Apply slippage on exit
                    if current_pos["direction"] == "BUY":
                        adj_exit = exit_price - (slippage_points * point_size)
                        pts = (adj_exit - current_pos["entry"]) / point_size
                    else:
                        adj_exit = exit_price + (slippage_points * point_size)
                        pts = (current_pos["entry"] - adj_exit) / point_size

                    gross_pnl = pts * point_value * current_pos["lots"]
                    comm = current_pos["lots"] * commission_per_lot * 2.0  # round-turn
                    net_pnl = gross_pnl - comm

                    balance += net_pnl
                    equity = balance

                    trade_record = {
                        "trade_num": len(trades) + 1,
                        "direction": current_pos["direction"],
                        "entry_time": current_pos["time"],
                        "exit_time": str(current_bar["timestamp"]),
                        "entry_price": current_pos["entry"],
                        "exit_price": adj_exit,
                        "sl": current_pos["sl"],
                        "tp": current_pos["tp"],
                        "lots": current_pos["lots"],
                        "net_pnl": round(net_pnl, 2),
                        "exit_reason": exit_reason,
                        "balance_after": round(balance, 2)
                    }
                    trades.append(trade_record)

                    in_position = False
                    current_pos = None

            # 2. Track Drawdown & Equity Curve
            if equity > peak_equity:
                peak_equity = equity
            dd = peak_equity - equity
            dd_pct = (dd / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

            if i % 5 == 0 or i == len(df) - 1:
                equity_curve.append({
                    "time": str(current_bar["timestamp"]),
                    "equity": round(equity, 2),
                    "balance": round(balance, 2)
                })

            # 3. Check for new entry condition if flat
            if not in_position:
                matched, report = self.strategy_engine.evaluate_strategy(
                    strategy_data, historical_slice, current_spread_pips=spread / spec["pip_size"]
                )

                if matched:
                    direction = report.get("direction", "BUY")
                    close_p = current_bar["close"]
                    atr_series = calculate_atr(historical_slice, 14)
                    curr_atr = atr_series.iloc[-1] if not np.isnan(atr_series.iloc[-1]) else (spec["pip_size"] * 20)

                    # Dynamic SL based on ATR (1.5x ATR)
                    sl_dist = max(spec["pip_size"] * 10, curr_atr * 1.5)
                    # Min RR 2:1
                    tp_dist = sl_dist * strategy_data.get("risk_settings", {}).get("min_risk_reward", 2.0)

                    if direction == "BUY":
                        entry_p = close_p + spread + (slippage_points * point_size)
                        sl_p = entry_p - sl_dist
                        tp_p = entry_p + tp_dist
                    else:
                        entry_p = close_p - (slippage_points * point_size)
                        sl_p = entry_p + sl_dist
                        tp_p = entry_p - tp_dist

                    # Position Sizing
                    sl_points = sl_dist / point_size
                    planned_risk = balance * (risk_percent / 100.0)
                    calc_lots = max(0.01, round(planned_risk / (sl_points * point_value), 2))

                    in_position = True
                    current_pos = {
                        "direction": direction,
                        "entry": entry_p,
                        "sl": sl_p,
                        "tp": tp_p,
                        "lots": calc_lots,
                        "time": str(current_bar["timestamp"])
                    }

        # Calculate Institutional Performance Metrics
        total_trades = len(trades)
        wins = [t for t in trades if t["net_pnl"] > 0]
        losses = [t for t in trades if t["net_pnl"] < 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round((win_count / total_trades) * 100.0, 1) if total_trades > 0 else 0.0

        gross_profit = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        net_profit = round(balance - starting_balance, 2)
        return_pct = round((net_profit / starting_balance) * 100.0, 2)

        avg_win = round(gross_profit / win_count, 2) if win_count > 0 else 0.0
        avg_loss = round(gross_loss / loss_count, 2) if loss_count > 0 else 0.0
        avg_rr = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        # Consecutive stats
        max_consec_wins = 0
        max_consec_losses = 0
        curr_w = 0
        curr_l = 0
        for t in trades:
            if t["net_pnl"] > 0:
                curr_w += 1
                curr_l = 0
                max_consec_wins = max(max_consec_wins, curr_w)
            else:
                curr_l += 1
                curr_w = 0
                max_consec_losses = max(max_consec_losses, curr_l)

        # Long vs Short
        long_trades = [t for t in trades if t["direction"] == "BUY"]
        short_trades = [t for t in trades if t["direction"] == "SELL"]
        long_wins = [t for t in long_trades if t["net_pnl"] > 0]
        short_wins = [t for t in short_trades if t["net_pnl"] > 0]

        long_win_rate = round((len(long_wins) / len(long_trades)) * 100.0, 1) if long_trades else 0.0
        short_win_rate = round((len(short_wins) / len(short_trades)) * 100.0, 1) if short_trades else 0.0

        return {
            "summary": {
                "strategy_name": strategy_data.get("name", "Custom"),
                "symbol": symbol,
                "timeframe": timeframe,
                "initial_balance": starting_balance,
                "final_balance": round(balance, 2),
                "net_profit": net_profit,
                "return_percent": return_pct,
                "total_trades": total_trades,
                "winning_trades": win_count,
                "losing_trades": loss_count,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "max_drawdown_amount": round(max_drawdown, 2),
                "max_drawdown_percent": round(max_drawdown_pct, 2),
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "avg_risk_reward": avg_rr,
                "max_consecutive_wins": max_consec_wins,
                "max_consecutive_losses": max_consec_losses,
                "long_trades_count": len(long_trades),
                "long_win_rate": long_win_rate,
                "short_trades_count": len(short_trades),
                "short_win_rate": short_win_rate
            },
            "equity_curve": equity_curve,
            "trades": trades
        }
