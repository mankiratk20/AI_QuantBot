"""
MetaTrader 5 Python Gateway and Socket Bridge Adapter.
Connects directly to MetaTrader 5 terminal via python API or EA socket bridge.
Supports OrderSend, PositionGet, AccountInfo, and SymbolInfoTick.
"""

from typing import Dict, Any, List, Optional
from backend.core.broker_adapters.base_adapter import BaseBrokerAdapter
from backend.storage.db import log_audit

class MT5Adapter(BaseBrokerAdapter):
    def __init__(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None):
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self.mt5_lib = None
        self._check_mt5_installed()

    def _check_mt5_installed(self):
        try:
            import MetaTrader5 as mt5
            self.mt5_lib = mt5
        except ImportError:
            self.mt5_lib = None

    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        creds = credentials or {}
        self.login = creds.get("login") or self.login
        self.password = creds.get("password") or self.password
        self.server = creds.get("server") or self.server

        if not self.mt5_lib:
            log_audit("MT5_CONNECT_FAIL", "WARNING", "MetaTrader5 Python library is not installed on this system. Running in bridge mode.")
            return False

        try:
            if self.login and self.password and self.server:
                res = self.mt5_lib.initialize(login=int(self.login), password=self.password, server=self.server)
            else:
                res = self.mt5_lib.initialize()

            if res:
                self.connected = True
                account_info = self.mt5_lib.account_info()
                log_audit("MT5_CONNECT_SUCCESS", "INFO", f"Connected to MT5 server {self.server}. Account #{account_info.login if account_info else 'N/A'}")
                return True
            else:
                err = self.mt5_lib.last_error()
                log_audit("MT5_CONNECT_FAIL", "ERROR", f"MT5 initialization failed: {err}")
                return False
        except Exception as e:
            log_audit("MT5_CONNECT_ERROR", "ERROR", f"MT5 connection exception: {str(e)}")
            return False

    def disconnect(self) -> bool:
        if self.mt5_lib and self.connected:
            self.mt5_lib.shutdown()
        self.connected = False
        return True

    def is_connected(self) -> bool:
        return self.connected

    def get_account_info(self) -> Dict[str, Any]:
        if not self.connected or not self.mt5_lib:
            return {
                "broker": "MetaTrader 5 (Disconnected)",
                "balance": 0.0,
                "equity": 0.0,
                "floating_pnl": 0.0,
                "currency": "USD",
                "is_connected": False
            }

        info = self.mt5_lib.account_info()
        if not info:
            return {"is_connected": False, "error": "Failed to fetch MT5 account info"}

        term = self.mt5_lib.terminal_info()
        algo_enabled = bool(term.trade_allowed) if term else True
        account_trade_allowed = bool(info.trade_allowed) if info else True

        return {
            "broker": f"MetaTrader 5 ({info.company})",
            "balance": float(info.balance),
            "equity": float(info.equity),
            "floating_pnl": float(info.profit),
            "used_margin": float(info.margin),
            "free_margin": float(info.margin_free),
            "currency": info.currency,
            "login": info.login,
            "algo_trading_enabled": algo_enabled,
            "trade_allowed": account_trade_allowed,
            "is_connected": True
        }

    def get_current_price(self, symbol: str) -> Dict[str, float]:
        if not self.connected or not self.mt5_lib:
            return {"bid": 0.0, "ask": 0.0, "spread": 0.0}

        tick = self.mt5_lib.symbol_info_tick(symbol)
        if not tick:
            return {"bid": 0.0, "ask": 0.0, "spread": 0.0}

        return {
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread": float(tick.ask - tick.bid)
        }

    def place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "SmartBot"
    ) -> Dict[str, Any]:
        if not self.connected or not self.mt5_lib:
            return {"success": False, "error": "MT5 is not connected"}

        mt5 = self.mt5_lib

        # Check Terminal Algo Trading Status
        terminal_info = mt5.terminal_info()
        if terminal_info and not terminal_info.trade_allowed:
            err_msg = (
                "AutoTrading is disabled in your MetaTrader 5 terminal! "
                "To enable: Click the 'Algo Trading' button in MT5's top toolbar to turn it GREEN, "
                "or open Tools -> Options -> Expert Advisors and check 'Allow Algo Trading'."
            )
            log_audit("MT5_ORDER_BLOCKED", "WARNING", err_msg)
            return {"success": False, "error": err_msg}

        # Check Account Trading Permission
        account_info = mt5.account_info()
        if account_info and not account_info.trade_allowed:
            err_msg = (
                "Trading is not permitted for this MT5 account! "
                "Ensure you logged in with your Trader / Master password (not the Investor / Read-Only password)."
            )
            log_audit("MT5_ORDER_BLOCKED", "ERROR", err_msg)
            return {"success": False, "error": err_msg}

        order_dict = {
            "BUY": mt5.ORDER_TYPE_BUY,
            "SELL": mt5.ORDER_TYPE_SELL,
            "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
            "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
        }

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"success": False, "error": f"Failed to get live market tick for {symbol}"}

        # Dynamically determine broker-supported filling mode
        sym_info = mt5.symbol_info(symbol)
        filling_types = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
        if sym_info and hasattr(sym_info, "filling_mode"):
            modes = sym_info.filling_mode
            if modes & 1:  # FOK
                filling_types = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
            elif modes & 2:  # IOC
                filling_types = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
            else:
                filling_types = [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC]

        exec_price = price or (tick.ask if order_type == "BUY" else tick.bid)
        last_error = ""

        # Try supported filling modes
        for fill_mode in filling_types:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(volume),
                "type": order_dict.get(order_type, mt5.ORDER_TYPE_BUY),
                "price": float(exec_price),
                "sl": float(stop_loss) if stop_loss else 0.0,
                "tp": float(take_profit) if take_profit else 0.0,
                "deviation": 25,
                "magic": 987654,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": fill_mode,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                log_audit("MT5_ORDER_DONE", "INFO", f"MT5 order filled! Ticket #{result.order} for {volume} lots of {symbol}")
                return {
                    "success": True,
                    "ticket": str(result.order),
                    "fill_price": float(result.price),
                    "volume": float(result.volume),
                    "retcode": result.retcode
                }
            elif result:
                retcode = result.retcode
                comment_str = result.comment or ""

                if retcode == 10027 or "autotrading" in comment_str.lower() or "disabled by client" in comment_str.lower():
                    last_error = (
                        "AutoTrading is disabled in your MetaTrader 5 terminal! "
                        "To enable: Click the 'Algo Trading' button in MT5's top toolbar to turn it GREEN, "
                        "or go to Tools -> Options -> Expert Advisors and check 'Allow Algo Trading'."
                    )
                    break
                elif retcode == 10017 or "trade disabled" in comment_str.lower():
                    last_error = "Trading is disabled on this account/symbol. Ensure you are not logged in with an Investor / Read-Only password."
                    break
                elif retcode == 10019:
                    last_error = f"Insufficient margin / balance on MT5 account for {volume} lots of {symbol}."
                    break
                elif retcode == 10030:
                    # Unsupported filling mode, continue to next filling type
                    last_error = f"Unsupported filling mode: {comment_str}"
                    continue
                else:
                    last_error = f"MT5 error ({retcode}): {comment_str}"
            else:
                last_error = f"MT5 order execution failed: {mt5.last_error()}"

        log_audit("MT5_ORDER_REJECTED", "ERROR", f"MT5 order rejected: {last_error}")
        return {"success": False, "error": last_error}

    def modify_order(
        self,
        ticket: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        if not self.connected or not self.mt5_lib:
            return False

        mt5 = self.mt5_lib
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(ticket),
            "sl": float(stop_loss) if stop_loss else 0.0,
            "tp": float(take_profit) if take_profit else 0.0,
        }
        res = mt5.order_send(request)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    def close_position(self, ticket: str, volume: Optional[float] = None) -> Dict[str, Any]:
        if not self.connected or not self.mt5_lib:
            return {"success": False, "error": "MT5 is not connected"}

        mt5 = self.mt5_lib
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return {"success": False, "error": f"Position #{ticket} not found in MT5"}

        pos = positions[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

        close_vol = volume or pos.volume
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(ticket),
            "symbol": pos.symbol,
            "volume": float(close_vol),
            "type": close_type,
            "price": float(close_price),
            "deviation": 20,
            "magic": 987654,
            "comment": "Close by SmartBot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            return {"success": True, "ticket": ticket, "close_price": close_price, "volume": close_vol}
        return {"success": False, "error": res.comment if res else "Failed to close position"}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        if not self.connected or not self.mt5_lib:
            return []

        mt5 = self.mt5_lib
        positions = mt5.positions_get()
        if not positions:
            return []

        results = []
        for p in positions:
            results.append({
                "ticket": str(p.ticket),
                "symbol": p.symbol,
                "direction": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": float(p.volume),
                "entry_price": float(p.price_open),
                "current_price": float(p.price_current),
                "stop_loss": float(p.sl),
                "take_profit": float(p.tp),
                "pnl": float(p.profit)
            })
        return results
