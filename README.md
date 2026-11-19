# AI-Powered Smart Trading Bot (Institutional Pro Terminal)

An enterprise-grade, institutional algorithmic trading platform and AI quantitative assistant that strictly executes trades according to the **USER'S OWN TRADING STRATEGY**.

---

## Key Highlights & Philosophy

- **User-Centric Strategy Dominance**: The bot strictly honors the user's trading rules. The AI never fabricates or forces its own strategy.
- **Deterministic 17-Step Execution Pipeline**: Validates market freshness, spread, session hours, economic news blackout, market structure alignment, user rule trees (AND/OR logic), position sizing, and prop firm drawdown limits before any order is submitted.
- **Three Safe Operating Modes**:
  1. `Manual Mode`: AI generates signals and structural thesis; user executes manually.
  2. `Semi-Automatic Mode` *(Default)*: Bot prepares qualifying setups and prompts user with an interactive `[Approve]` / `[Reject]` action card before submission.
  3. `Automatic Mode`: Autonomous execution within strict risk limits (*Disabled by default*).
- **Hard Risk & Prop Firm Circuit Breaker**: Real-time balance and equity tracking with instant emergency shutdown if daily or overall drawdown thresholds are threatened.
- **Multi-Broker Architecture**: Built-in Paper Broker simulator, MetaTrader 5 Python Gateway, cTrader Open API connector, and Binance Futures Crypto API.

---

## Terminal Views (15 Core Modules)

1. **Dashboard**: Real-time account balance, equity, mark-to-market floating P&L, open positions, active strategies, and broker status.
2. **Live Trading**: Interactive candlestick charts with multi-timeframe switching (1M, 5M, 15M, 1H, 4H, 1D), EMA 20/50/200, and real-time open trade markers.
3. **Strategy Builder**: Dedicated visual builder for custom user strategies with nested AND/OR logic, multi-timeframe alignment, session filters, and risk thresholds.
4. **AI Market Analysis**: Smart Money Concepts (SMC) & ICT scanner detecting Break of Structure (BOS), Change of Character (CHOCH), Fair Value Gaps (FVG), Order Blocks (OB), Liquidity pools (BSL/SSL), and candlestick patterns.
5. **Trading Signals**: Live signal stream with transparent confluence scoring (0-95%) and natural language structural rationales.
6. **Open Positions**: Live position tracker with real-time PnL, manual modification, and one-click individual close.
7. **Trade History**: Historical executions log with execution tickets and net PnL.
8. **Backtesting Studio**: Historical simulation engine with zero look-ahead bias, realistic spread, slippage, commission modeling ($3.50/lot), and equity curve visualization.
9. **Performance Analytics**: Win rate, profit factor, average risk-to-reward, and breakdown by pair and strategy.
10. **Prop Firm Mode**: Challenge compliance tracker with presets (FTMO, FundedNext, The5ers, Custom) and real-time remaining daily/overall drawdown meters.
11. **Economic Calendar**: Macro-economic event feed (CPI, NFP, FOMC, Rate decisions) with automatic entry blackout timers ($T_{\text{pre}}$ and $T_{\text{post}}$ minutes).
12. **Trading Journal**: Automated post-trade documentation storing entry/exit reasons, market conditions, and lessons learned.
13. **Notifications**: Telegram bot integration and in-app event alerts for executions, SL/TP hits, and risk limits.
14. **Broker Connections**: Health and credential management for Paper Trading, MT5, Binance, and cTrader.
15. **Settings & Security**: Emergency Stop All kill switch, audit logs, and account protection.

---

## Quickstart Guide

### 1. Requirements
- Python 3.10+ (Tested on Python 3.14)
- Modern web browser (Chrome, Edge, Firefox, Brave)

### 2. Launching the Platform
Run the application launcher:
```bash
python run_bot.py
```
Open your browser at:
```
http://127.0.0.1:5000
```

### 3. Running Automated Tests
To run the full unit test suite covering indicators, strategy evaluation, risk sizing, prop firm compliance, broker execution, backtesting, and REST APIs:
```bash
python -m unittest tests/test_trading_bot.py
```

---

## Live Trading Chart & Real Account Setup

### 1. Live Trading Chart Visibility
The live trading terminal is equipped with a self-contained, high-DPI HTML5 institutional chart engine (`frontend/static/js/chart.js`):
- **Instant Local Rendering**: Zero external CDN latency or blocking. Renders reliably even offline or behind firewalls.
- **Dynamic Auto-Resize**: Automatically resizes to 100% of the viewport container upon clicking the **Live Trading** tab.
- **Technical Overlays**: Real-time EMA 20 (Cyan), EMA 50 (Orange), Break of Structure (BOS), Change of Character (CHOCH), Fair Value Gaps (FVG), and Order Blocks (OB).
- **Position Tracking**: Visualizes active entry lines, Stop Loss (Red), and Take Profit (Green).

### 2. Where & How to Add Your Real Trading Account
Navigate to **"Broker Connections"** in the sidebar (or click the **`[🔌 Broker: ...]`** button at the top header):

#### A. MetaTrader 5 (MT5 Real / Prop Firm Account)
1. In the **MetaTrader 5** connection card:
   - Enter your **Account Login / ID** (e.g., `51829102`).
   - Enter your **Trader Password**.
   - Enter your **Broker Server Name** (e.g., `MetaQuotes-Demo`, `FTMO-Server`, `ICMarketsSC-Live`, `FundedNext-Server`).
2. Click **"Connect MT5 Real Account"**.
3. The bot connects directly to your MT5 terminal, synchronizes your real balance, equity, and margin, and streams tick data directly from your broker.

#### B. Binance Crypto (Futures / Spot)
1. In the **Binance Crypto** connection card:
   - Enter your **Binance API Key**.
   - Enter your **Binance API Secret**.
   - Toggle **Testnet** if using demo futures.
2. Click **"Connect Binance Account"**.
3. The bot connects with HMAC SHA256 authentication and starts monitoring crypto markets (BTCUSDT, ETHUSDT).

#### C. Spotware cTrader Open API
1. Enter your **Client ID**, **Client Secret**, and **Account ID**.
2. Click **"Connect cTrader Account"**.

#### D. Risk-Free Paper Trading Simulator
- At any time, you can switch back to the simulated environment with configurable balance ($5,000 to $200,000) using the **"Switch to Risk-Free Paper Simulator"** button.

---

## Strategy Rule Configuration Example

Strategies are stored in JSON rule trees supporting nested logical operations:
```json
{
  "name": "ICT Liquidity Sweep & FVG Retest",
  "strategy_type": "Smart Money Concepts (SMC)",
  "instruments": ["EURUSD", "GBPUSD", "XAUUSD"],
  "timeframes": ["15M"],
  "rules": {
    "operator": "AND",
    "conditions": [
      { "field": "trend", "operator": "==", "value": "BULLISH" },
      { "field": "bullish_choch_present", "operator": "==", "value": true },
      { "field": "active_bullish_fvg", "operator": "==", "value": true },
      { "field": "rsi", "operator": "<=", "value": 65 }
    ]
  },
  "risk_settings": {
    "risk_percent": 1.0,
    "min_risk_reward": 2.0,
    "max_spread_pips": 2.5
  }
}
```

---

## Mathematical Position Sizing Formula

$$\text{Planned Monetary Risk} = \text{Account Balance} \times \left(\frac{\text{Risk \%}}{100}\right)$$

$$\text{Stop Loss Points} = \frac{|\text{Entry Price} - \text{Stop Loss Price}|}{\text{Point Size}}$$

$$\text{Position Size (Lots)} = \frac{\text{Planned Monetary Risk}}{\text{Stop Loss Points} \times \text{Point Value per Lot}}$$

All position calculations strictly respect instrument contract sizes, tick values, and minimum micro-lot increments (0.01).

---

## Security & Risk Notice
Trading Forex, Commodities, Indices, and Cryptocurrencies involves substantial risk of loss. The AI-Powered Smart Trading Bot enforces strict risk discipline, but users should always thoroughly backtest and forward-test on paper accounts before deploying capital.
