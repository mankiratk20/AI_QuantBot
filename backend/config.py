"""
Configuration and constants for AI-Powered Smart Trading Bot.
Defines supported instruments, contract specifications, trading sessions,
and default risk parameters.
"""

import os
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Automatically load .env file if present
ENV_FILE = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_FILE):
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                    if _k not in os.environ:
                        os.environ[_k] = _v
    except Exception:
        pass

DATABASE_PATH = os.path.join(DATA_DIR, "trading_bot.db")

# Supported Instruments with institutional contract specs
INSTRUMENT_SPECS: Dict[str, Dict[str, Any]] = {
    "EURUSD": {
        "name": "EUR / USD",
        "category": "forex",
        "contract_size": 100000,
        "digits": 5,
        "pip_size": 0.0001,
        "point_size": 0.00001,
        "tick_value_standard": 10.0,  # $10 per pip on 1 standard lot
        "typical_spread": 0.00012,
        "quote_currency": "USD",
        "description": "Euro vs US Dollar"
    },
    "GBPUSD": {
        "name": "GBP / USD",
        "category": "forex",
        "contract_size": 100000,
        "digits": 5,
        "pip_size": 0.0001,
        "point_size": 0.00001,
        "tick_value_standard": 10.0,
        "typical_spread": 0.00015,
        "quote_currency": "USD",
        "description": "British Pound vs US Dollar"
    },
    "GBPJPY": {
        "name": "GBP / JPY",
        "category": "forex",
        "contract_size": 100000,
        "digits": 3,
        "pip_size": 0.01,
        "point_size": 0.001,
        "tick_value_standard": 6.8,  # ~$6.8 - $7.0 USD per pip depending on USDJPY
        "typical_spread": 0.018,
        "quote_currency": "JPY",
        "description": "British Pound vs Japanese Yen"
    },
    "USDJPY": {
        "name": "USD / JPY",
        "category": "forex",
        "contract_size": 100000,
        "digits": 3,
        "pip_size": 0.01,
        "point_size": 0.001,
        "tick_value_standard": 6.8,
        "typical_spread": 0.012,
        "quote_currency": "JPY",
        "description": "US Dollar vs Japanese Yen"
    },
    "XAUUSD": {
        "name": "Gold / USD",
        "category": "metals",
        "contract_size": 100,  # 100 troy ounces per lot
        "digits": 2,
        "pip_size": 0.10,      # $0.10 move = $10 per lot
        "point_size": 0.01,    # 1 point ($0.01) = $1 per lot
        "tick_value_standard": 10.0,  # $10 per $0.10 pip move
        "typical_spread": 0.25,
        "quote_currency": "USD",
        "description": "Spot Gold vs US Dollar"
    },
    "US30": {
        "name": "US Wall Street 30 (Dow Jones)",
        "category": "indices",
        "contract_size": 1,
        "digits": 1,
        "pip_size": 1.0,
        "point_size": 0.1,
        "tick_value_standard": 1.0,  # $1 per point on 1 lot
        "typical_spread": 2.5,
        "quote_currency": "USD",
        "description": "Dow Jones Industrial Average CFD"
    },
    "NAS100": {
        "name": "US Tech 100 (Nasdaq)",
        "category": "indices",
        "contract_size": 1,
        "digits": 1,
        "pip_size": 1.0,
        "point_size": 0.1,
        "tick_value_standard": 1.0,
        "typical_spread": 1.5,
        "quote_currency": "USD",
        "description": "Nasdaq 100 CFD"
    },
    "BTCUSD": {
        "name": "Bitcoin / USD",
        "category": "crypto",
        "contract_size": 1,
        "digits": 2,
        "pip_size": 1.0,
        "point_size": 0.01,
        "tick_value_standard": 1.0,  # $1 per $1 move on 1 BTC
        "typical_spread": 8.0,
        "quote_currency": "USD",
        "description": "Bitcoin vs US Dollar"
    }
}

# Supported Timeframes
TIMEFRAMES = ["1M", "5M", "15M", "30M", "1H", "4H", "1D"]

# Standard Global Trading Sessions (UTC hours)
TRADING_SESSIONS = {
    "Sydney": {"open_utc": 21, "close_utc": 6},
    "Tokyo": {"open_utc": 0, "close_utc": 9},
    "London": {"open_utc": 7, "close_utc": 16},
    "New York": {"open_utc": 12, "close_utc": 21},
    "London-NY Overlap": {"open_utc": 12, "close_utc": 16}
}

# Default Institutional Risk Parameters
DEFAULT_RISK_CONFIG = {
    "account_balance": 10000.0,
    "account_currency": "USD",
    "risk_percent_per_trade": 1.0,      # 1% per trade
    "max_daily_loss_percent": 3.0,       # 3% max daily loss
    "max_weekly_loss_percent": 6.0,      # 6% max weekly loss
    "max_account_drawdown_percent": 10.0,# 10% max total drawdown
    "max_open_trades": 3,
    "max_simultaneous_exposure_lots": 5.0,
    "min_risk_reward_ratio": 1.5,
    "daily_profit_target_percent": 3.0,
    "max_trades_per_day": 5,
    "consecutive_loss_limit": 3,
    "cooldown_minutes_after_consecutive_losses": 60,
    "emergency_kill_switch_active": False,
    "trading_mode": "semi_automatic"     # manual | semi_automatic | automatic (auto disabled by default)
}

# Prop Firm Rules Presets
PROP_FIRM_PRESETS = {
    "FTMO Standard": {
        "daily_drawdown_limit_percent": 5.0,
        "max_overall_drawdown_percent": 10.0,
        "profit_target_step1_percent": 10.0,
        "profit_target_step2_percent": 5.0,
        "minimum_trading_days": 4,
        "weekend_holding_allowed": False,
        "news_trading_allowed": True,
        "max_lot_size": 10.0,
        "drawdown_type": "balance_based"
    },
    "FundedNext Stellar": {
        "daily_drawdown_limit_percent": 5.0,
        "max_overall_drawdown_percent": 10.0,
        "profit_target_step1_percent": 8.0,
        "profit_target_step2_percent": 5.0,
        "minimum_trading_days": 5,
        "weekend_holding_allowed": True,
        "news_trading_allowed": True,
        "max_lot_size": 15.0,
        "drawdown_type": "balance_based"
    },
    "The5ers High Stakes": {
        "daily_drawdown_limit_percent": 5.0,
        "max_overall_drawdown_percent": 10.0,
        "profit_target_step1_percent": 8.0,
        "profit_target_step2_percent": 5.0,
        "minimum_trading_days": 3,
        "weekend_holding_allowed": True,
        "news_trading_allowed": True,
        "max_lot_size": 20.0,
        "drawdown_type": "equity_based"
    },
    "Custom Prop Firm": {
        "daily_drawdown_limit_percent": 4.0,
        "max_overall_drawdown_percent": 8.0,
        "profit_target_step1_percent": 8.0,
        "profit_target_step2_percent": 5.0,
        "minimum_trading_days": 5,
        "weekend_holding_allowed": False,
        "news_trading_allowed": False,
        "max_lot_size": 5.0,
        "drawdown_type": "equity_based"
    }
}
