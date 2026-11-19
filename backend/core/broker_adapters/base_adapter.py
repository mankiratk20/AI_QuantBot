"""
Abstract Base Class for Broker Connectors.
Defines standard order execution, position monitoring, and account inquiry interfaces.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseBrokerAdapter(ABC):
    @abstractmethod
    def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """
        Returns:
            balance: float
            equity: float
            margin: float
            free_margin: float
            currency: str
        """
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> Dict[str, float]:
        """
        Returns:
            bid: float
            ask: float
            spread: float
        """
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        order_type: str,  # BUY, SELL, BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP
        volume: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = ""
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def modify_order(
        self,
        ticket: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        pass

    @abstractmethod
    def close_position(
        self,
        ticket: str,
        volume: Optional[float] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_open_positions(self) -> List[Dict[str, Any]]:
        pass
