# MetaTrader 5 (MT5) Terminal Setup & Execution Guide

This guide walks you through downloading, installing, configuring, and connecting your MetaTrader 5 terminal to the AI-Powered Smart Trading Bot.

---

## Step 1: Download & Install MetaTrader 5

If you do not already have MetaTrader 5 installed on your Windows PC:
1. **From your Broker** (Recommended): Download MT5 directly from your broker's website (e.g., FTMO, FundedNext, ICMarkets, Exness, RoboForex) so the broker servers are pre-configured.
2. **From Official MetaQuotes**: Download from [metatrader5.com](https://www.metatrader5.com/en/download).
3. Run the installer (`mt5setup.exe`) and complete installation (default location: `C:\Program Files\MetaTrader 5\terminal64.exe`).

---

## Step 2: Log In to Your Trading Account

1. Launch MetaTrader 5 from your Start Menu or Desktop.
2. Go to **File** -> **Login to Trade Account** (or press `Ctrl + O` -> `Server`).
3. Enter:
   - **Login**: Your Account ID / Number.
   - **Password**: Your Trader Password.
   - **Server**: Select your exact broker server (e.g. `FTMO-Demo`, `MetaQuotes-Demo`, `ICMarketsSC-Live`).
4. Click **OK**.
5. Verify connection: Look at the bottom right corner of MT5. You should see incoming/outgoing bytes (e.g., `124/15 kb`) and green signal bars.

---

## Step 3: Enable Automated Trading Settings in MT5

To allow the Python trading bot to communicate with MT5:
1. Click the **"Algo Trading"** button on MT5's top toolbar (ensure it turns **Green**).
2. Go to **Tools** -> **Options** (or press `Ctrl + O`).
3. Click the **Expert Advisors** tab.
4. Check the following boxes:
   - [x] **Allow Algo Trading**
   - [x] **Allow DLL imports**
   - [x] **Allow WebRequest for listed URL** -> Add: `http://127.0.0.1:5000`
5. Click **OK**.

---

## Step 4: Connecting MT5 to the AI Trading Bot

1. Start your trading bot:
   ```powershell
   python run_bot.py
   ```
2. Open your web browser at: `http://127.0.0.1:5000`
3. Click **"Broker Connections"** in the sidebar (or click the top header broker button).
4. In the **MetaTrader 5 (MT5)** card:
   - Enter your **Login ID**, **Password**, and **Server**.
   - Click **"Connect MT5 Real Account"**.
5. The terminal will immediately verify the connection, display your live balance and equity, and sync market data.
