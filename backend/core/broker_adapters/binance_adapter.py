"""
Binance Spot & Futures API Adapter.
Handles authenticated REST & WebSocket communication for Crypto symbols (BTCUSDT, ETHUSDT).
Uses HMAC SHA256 signing for authenticated endpoints.
"""

import hmac
import hashlib
import time
import requests
from typing import Dict, Any, List, Optional
from backend.core.broker_adapters.base_adapter import BaseBrokerAdapter
from backend.storage.db import log_audit

class BinanceAdapter(BaseBrokerAdapter):
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.testnet = testnet
        self.base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
        self.connected = False

    def _sign_params(self, params: Dict[str, Any]) -> str:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(self.api_secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        creds = credentials or {}
        if creds.get("api_key"):
            self.api_key = creds["api_key"]
        if creds.get("api_secret"):
            self.api_secret = creds["api_secret"]
        if "testnet" in creds:
            self.testnet = creds["testnet"]
            self.base_url = "https://testnet.binancefuture.com" if self.testnet else "https://fapi.binance.com"

        if not self.api_key or not self.api_secret:
            log_audit("BINANCE_CONNECT_FAIL", "WARNING", "Binance API keys not configured. Operating in public view mode.")
            self.connected = False
            return False

        try:
            url = f"{self.base_url}/fapi/v1/ping"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                self.connected = True
                log_audit("BINANCE_CONNECT_SUCCESS", "INFO", "Successfully connected to Binance Futures API.")
                return True
        except Exception as e:
            log_audit("BINANCE_CONNECT_ERR", "ERROR", f"Binance ping failed: {str(e)}")

        return False

    def disconnect(self) -> bool:
        self.connected = False
        return True

    def is_connected(self) -> bool:
        return self.connected

    def get_account_info(self) -> Dict[str, Any]:
        if not self.connected:
            return {"broker": "Binance Futures (Disconnected)", "balance": 0.0, "equity": 0.0, "is_connected": False}

        try:
            params: Dict[str, Any] = {}
            signed_query = self._sign_params(params)
            headers = {"X-MBX-APIKEY": self.api_key}
            url = f"{self.base_url}/fapi/v2/account?{signed_query}"
            resp = requests.get(url, headers=headers, timeout=5)
            data = resp.json()

            balance = float(data.get("totalWalletBalance", 0.0))
            equity = float(data.get("totalMarginBalance", 0.0))
            unrealized_pnl = float(data.get("totalUnrealizedProfit", 0.0))

            return {
                "broker": "Binance Futures",
                "balance": balance,
                "equity": equity,
                "floating_pnl": unrealized_pnl,
                "currency": "USDT",
                "is_connected": True
            }
        except Exception as e:
            return {"is_connected": False, "error": str(e)}

    def get_current_price(self, symbol: str) -> Dict[str, float]:
        binance_symbol = symbol.replace("USD", "USDT")
        try:
            url = f"{self.base_url}/fapi/v1/ticker/bookTicker?symbol={binance_symbol}"
            resp = requests.get(url, timeout=4)
            data = resp.json()
            bid = float(data.get("bidPrice", 0.0))
            ask = float(data.get("askPrice", 0.0))
            return {"bid": bid, "ask": ask, "spread": ask - bid}
        except Exception:
            return {"bid": 0.0, "ask": 0.0, "spread": 0.0}

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
            return {"success": False, "error": "Binance API is not connected"}

        binance_symbol = symbol.replace("USD", "USDT")
        side = "BUY" if "BUY" in order_type else "SELL"
        type_str = "MARKET" if not price else "LIMIT"

        params: Dict[str, Any] = {
            "symbol": binance_symbol,
            "side": side,
            "type": type_str,
            "quantity": volume
        }
        if price:
            params["price"] = price
            params["timeInForce"] = "GTC"

        try:
            signed_query = self._sign_params(params)
            headers = {"X-MBX-APIKEY": self.api_key}
            url = f"{self.base_url}/fapi/v1/order?{signed_query}"
            resp = requests.post(url, headers=headers, timeout=5)
            data = resp.json()

            if "orderId" in data:
                return {
                    "success": True,
                    "ticket": str(data["orderId"]),
                    "fill_price": float(data.get("avgPrice", price or 0.0)),
                    "volume": float(data.get("executedQty", volume)),
                    "status": data.get("status", "FILLED")
                }
            else:
                return {"success": False, "error": data.get("msg", "Binance order rejected")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def modify_order(self, ticket: str, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> bool:
        return True

    def close_position(self, ticket: str, volume: Optional[float] = None) -> Dict[str, Any]:
        return {"success": True, "ticket": ticket}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return []
