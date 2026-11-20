/**
 * Smart Trading Bot - Core Application Controller.
 * Manages 15 terminal views, real-time SSE stream, order interactions,
 * TradingView live charts, prop firm monitoring, and notification toasts.
 */

const TV_SYMBOLS = {
  "EURUSD": "FX:EURUSD",
  "GBPUSD": "FX:GBPUSD",
  "GBPJPY": "FX:GBPJPY",
  "USDJPY": "FX:USDJPY",
  "XAUUSD": "OANDA:XAUUSD",
  "US30": "TVC:DJI",
  "NAS100": "TVC:IXIC",
  "BTCUSD": "BINANCE:BTCUSDT"
};

const TV_TIMEFRAMES = {
  "1M": "1",
  "5M": "5",
  "15M": "15",
  "30M": "30",
  "1H": "60",
  "4H": "240",
  "1D": "D"
};

class SmartBotApp {
  constructor() {
    this.currentView = "view-dashboard";
    this.chart = null;
    this.tvWidget = null;
    this.chartMode = "tradingview"; // "tradingview" or "smc"
    this.activeCurrency = "USD";
    this.accountBalance = 10000.0;
    this.stratBuilder = null;
    this.eventSource = null;
    this.activeSymbol = "EURUSD";
    this.activeTimeframe = "15M";
    this.latestState = null;
    this.selectedOrderType = "MARKET";
    this.selectedDirection = "BUY";
    this.calendarCurrencyFilter = "ALL";
    this.calendarImpactFilter = "ALL";
    this.calendarSearchQuery = "";
    this.allCalendarEvents = [];
    this.currentUser = null;
    this.authToken = localStorage.getItem("quant_auth_token") || null;
    this.authMode = "LOGIN_CREDENTIALS";
    this.currentLoginSessionToken = null;
    this.currentSignupEmail = null;
    this.currentResetSessionToken = null;
    this.currentResetEmail = null;
    this.terminalInitialized = false;
    this.init();
  }

  formatCurrency(val, currency = this.activeCurrency) {
    const num = Number(val) || 0;
    const formatted = num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (currency === "EUR") return `€${formatted}`;
    if (currency === "GBP") return `£${formatted}`;
    if (currency === "JPY") return `¥${formatted}`;
    if (currency === "USDT") return `${formatted} USDT`;
    return `$${formatted}`;
  }

  async init() {
    this.bindNavigation();
    this.bindGlobalControls();
    const isAuth = await this.checkCurrentUser();
    if (isAuth) {
      await this.initTerminalWorkspace();
    } else {
      this.showAuthPortal();
    }
  }

  async initTerminalWorkspace() {
    this.updateAuthUI();

    const sidebar = document.getElementById("app-sidebar");
    const mainWrapper = document.getElementById("app-main-wrapper");
    const authPortal = document.getElementById("auth-portal-screen");

    if (authPortal) authPortal.style.display = "none";
    if (sidebar) sidebar.style.display = "flex";
    if (mainWrapper) mainWrapper.style.display = "flex";

    this.updateAuthUI();

    if (this.terminalInitialized) return;
    this.terminalInitialized = true;

    this.initSSEStream();
    await this.fetchBrokerConfig();
    await this.refreshDashboard();

    // Initialize Chart and Strategy Builder
    if (!window.stratBuilder) {
      window.stratBuilder = new StrategyBuilderUI();
    } else {
      await window.stratBuilder.fetchStrategies();
      window.stratBuilder.renderStrategyList();
    }

    if (!this.chart) {
      this.chart = new TradingChart("main-tradingview-chart");
    }

    await this.loadChartSymbol(this.activeSymbol, this.activeTimeframe);
    this.populateBacktestStrategies();
  }

  bindNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((item) => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const targetView = item.getAttribute("data-view");
        this.switchView(targetView);
      });
    });
  }

  switchView(viewId) {
    document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
    const activeNav = document.querySelector(`.nav-item[data-view="${viewId}"]`);
    if (activeNav) activeNav.classList.add("active");

    document.querySelectorAll(".view-container").forEach((v) => v.classList.remove("active"));
    const target = document.getElementById(viewId);
    if (target) {
      target.classList.add("active");
      this.currentView = viewId;
      this.onViewActivated(viewId);
    }
  }

  onViewActivated(viewId) {
    if (viewId === "view-live-trading") {
      setTimeout(() => {
        if (this.chartMode === "tradingview") {
          this.initTradingViewWidget(this.activeSymbol, this.activeTimeframe);
        } else if (this.chart) {
          this.chart.resize();
        }
        this.loadChartSymbol(this.activeSymbol, this.activeTimeframe);
      }, 60);
    } else if (viewId === "view-signals") {
      this.fetchSignals();
    } else if (viewId === "view-positions") {
      this.fetchPositions();
    } else if (viewId === "view-prop-firm") {
      this.fetchPropFirm();
    } else if (viewId === "view-calendar") {
      this.fetchCalendar();
    } else if (viewId === "view-journal") {
      this.fetchJournal();
    } else if (viewId === "view-analytics") {
      this.fetchAnalytics();
    } else if (viewId === "view-ai-analysis") {
      this.fetchAIAnalysis();
    } else if (viewId === "view-notifications") {
      this.fetchNotifications();
    } else if (viewId === "view-brokers") {
      this.fetchBrokerConfig();
    } else if (viewId === "view-backtesting") {
      this.populateBacktestStrategies();
    } else if (viewId === "view-audit-logs") {
      this.fetchAuditLogs();
    }
  }

  bindGlobalControls() {
    // Emergency Kill Switch Button
    const killBtn = document.getElementById("btn-global-kill-switch");
    if (killBtn) {
      killBtn.addEventListener("click", async () => {
        const isCurrentlyActive = killBtn.classList.contains("active");
        const action = isCurrentlyActive ? "deactivate" : "ACTIVATE";
        if (confirm(`Are you sure you want to ${action} the Emergency Kill Switch?`)) {
          await fetch("/api/settings/kill-switch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ active: !isCurrentlyActive })
          });
          await this.refreshDashboard();
        }
      });
    }

    // Emergency Close All Button
    const closeAllBtn = document.getElementById("btn-close-all-positions");
    if (closeAllBtn) {
      closeAllBtn.addEventListener("click", async () => {
        if (confirm("WARNING: Forcibly close ALL open positions right now?")) {
          const res = await fetch("/api/positions/close-all", { method: "POST" });
          const data = await res.json();
          this.showToast(`Closed ${data.closed_count} positions immediately.`, "danger");
          this.fetchPositions();
        }
      });
    }

    // Trigger AI Scan Button
    const scanBtn = document.getElementById("btn-trigger-scan");
    if (scanBtn) {
      scanBtn.addEventListener("click", async () => {
        scanBtn.innerText = "Scanning Market Structure...";
        scanBtn.disabled = true;
        try {
          const res = await fetch("/api/signals/scan", { method: "POST" });
          const data = await res.json();
          if (data.signals_generated_count > 0) {
            this.showToast(`AI Scan Complete: ${data.signals_generated_count} qualifying setup(s) found!`, "success");
            this.fetchSignals();
          } else {
            this.showToast("AI Scan Complete: No setups met 100% of strategy rules.", "info");
          }
        } catch (e) {
          this.showToast("Market scan failed: " + e.message, "danger");
        } finally {
          scanBtn.innerText = "Scan Live Setups";
          scanBtn.disabled = false;
        }
      });
    }

    // Trading Mode Selector
    const modeSelect = document.getElementById("select-trading-mode");
    if (modeSelect) {
      modeSelect.addEventListener("change", async (e) => {
        const mode = e.target.value;
        if (mode === "automatic") {
          const ok = confirm("CAUTION: Automatic Mode enables unattended order execution. The bot will execute trades within strict risk limits. Confirm enable?");
          if (!ok) {
            e.target.value = "semi_automatic";
            return;
          }
        }
        await fetch("/api/settings/mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode })
        });
        this.showToast(`Trading Mode switched to ${mode.toUpperCase()}`, "info");
      });
    }
  }

  initSSEStream() {
    this.eventSource = new EventSource("/api/stream/events");
    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.latestState = data;
        this.updateRealTimeUI(data);
      } catch (e) {
        console.error("SSE parse error", e);
      }
    };
    this.eventSource.onerror = () => {
      console.warn("SSE connection interrupted. Reconnecting in background...");
    };
  }

  updateRealTimeUI(data) {
    // 1. Top Header Quick KPIs & Connected Account Insights
    if (data.account) {
      const acc = data.account;
      this.activeCurrency = acc.currency || "USD";
      this.accountBalance = acc.balance || 0;

      const topBal = document.getElementById("top-balance");
      const topEq = document.getElementById("top-equity");
      const topPnl = document.getElementById("top-floating-pnl");
      const topBroker = document.getElementById("top-broker-label");

      if (topBal) topBal.innerText = this.formatCurrency(acc.balance);
      if (topEq) topEq.innerText = this.formatCurrency(acc.equity);
      if (topPnl) {
        const pnl = acc.floating_pnl || 0;
        topPnl.innerText = `${pnl >= 0 ? '+' : ''}${this.formatCurrency(pnl)}`;
        topPnl.className = `ticker-val ${pnl >= 0 ? 'bullish' : 'bearish'}`;
      }
      if (topBroker) topBroker.innerText = `Broker: ${acc.broker || 'Paper'}`;

      // Dashboard View Synchronized KPIs
      const dashBal = document.getElementById("dash-balance");
      const dashEq = document.getElementById("dash-equity");
      const dashBroker = document.getElementById("dash-broker");
      if (dashBal) dashBal.innerText = this.formatCurrency(acc.balance);
      if (dashEq) dashEq.innerText = this.formatCurrency(acc.equity);
      if (dashBroker) dashBroker.innerText = acc.broker || "Paper Broker";

      // Broker View Synchronized Cards
      const bBal = document.getElementById("active-broker-balance");
      const bEq = document.getElementById("active-broker-equity");
      const bFree = document.getElementById("active-broker-free-margin");
      const bProv = document.getElementById("active-broker-provider");
      if (bBal) bBal.innerText = this.formatCurrency(acc.balance);
      if (bEq) bEq.innerText = this.formatCurrency(acc.equity);
      if (bFree) bFree.innerText = this.formatCurrency(acc.free_margin ?? acc.balance);
      if (bProv) bProv.innerText = acc.broker || "Paper Simulator";

      // Live Trading Header & Order Execution Ticket Indicator
      const brokerInd = document.getElementById("active-broker-indicator");
      if (brokerInd) brokerInd.innerText = `Broker: ${acc.broker || 'Paper'}`;
      const submitBroker = document.getElementById("label-submit-broker");
      if (submitBroker) submitBroker.innerText = acc.broker || "Paper Simulator";
      const orderTarget = document.getElementById("order-target-broker");
      if (orderTarget) {
        orderTarget.innerText = acc.is_connected ? "CONNECTED" : "READY";
      }

      // MT5 AutoTrading permission check
      const algoWarn = document.getElementById("algo-trading-warning-banner");
      if (algoWarn) {
        if (acc.broker && acc.broker.includes("MetaTrader") && acc.algo_trading_enabled === false) {
          algoWarn.style.display = "block";
        } else {
          algoWarn.style.display = "none";
        }
      }
    }

    // 1.5 Update Live Trading Quotes & Order Ticket Prices
    if (data.quotes && data.quotes[this.activeSymbol]) {
      const q = data.quotes[this.activeSymbol];
      const bidEl = document.getElementById("live-ticker-bid");
      const askEl = document.getElementById("live-ticker-ask");
      const spreadEl = document.getElementById("live-ticker-spread");
      const sellPriceEl = document.getElementById("ticket-sell-price");
      const buyPriceEl = document.getElementById("ticket-buy-price");

      if (bidEl) bidEl.innerText = q.bid;
      if (askEl) askEl.innerText = q.ask;
      if (spreadEl) spreadEl.innerText = q.spread_pips;
      if (sellPriceEl) sellPriceEl.innerText = q.bid;
      if (buyPriceEl) buyPriceEl.innerText = q.ask;

      this.updateSubmitButtonText(q);
    }

    // 2. Active Positions Live PnL
    if (data.positions && this.currentView === "view-positions") {
      this.renderPositionsTable(data.positions);
    }

    // 3. Update Chart Mark-to-Market Lines if active
    if (this.chart && data.positions) {
      this.chart.applyActivePositionLines(data.positions);
    }

    // 4. Smart Management Action Toasts
    if (data.actions && data.actions.length > 0) {
      data.actions.forEach((act) => {
        if (act.action === "BREAK_EVEN_TRIGGERED") {
          this.showToast(`Break-Even triggered for #${act.ticket} at ${act.rr_achieved}R! SL moved to risk-free.`, "success");
        } else if (act.action === "PARTIAL_TP_TAKEN") {
          this.showToast(`Partial Take-Profit booked: 50% (${act.closed_vol} lots) on #${act.ticket} (+${this.formatCurrency(act.realized_pnl)})!`, "success");
        }
      });
    }
  }

  async refreshDashboard() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      const acc = data.account || {};

      this.activeCurrency = acc.currency || "USD";
      this.accountBalance = acc.balance || 0;

      const topBal = document.getElementById("top-balance");
      const topEq = document.getElementById("top-equity");
      const topBroker = document.getElementById("top-broker-label");
      if (topBal) topBal.innerText = this.formatCurrency(acc.balance);
      if (topEq) topEq.innerText = this.formatCurrency(acc.equity);
      if (topBroker) topBroker.innerText = `Broker: ${acc.broker || 'Paper'}`;

      const dashBal = document.getElementById("dash-balance");
      const dashEq = document.getElementById("dash-equity");
      const dashOpen = document.getElementById("dash-open-trades");
      const dashBroker = document.getElementById("dash-broker");
      const dashStrats = document.getElementById("dash-active-strats");

      if (dashBal) dashBal.innerText = this.formatCurrency(acc.balance);
      if (dashEq) dashEq.innerText = this.formatCurrency(acc.equity);
      if (dashOpen) dashOpen.innerText = data.open_positions_count;
      if (dashBroker) dashBroker.innerText = acc.broker || "Paper Broker";
      if (dashStrats) dashStrats.innerText = data.active_strategy_count;

      const bBal = document.getElementById("active-broker-balance");
      const bEq = document.getElementById("active-broker-equity");
      const bFree = document.getElementById("active-broker-free-margin");
      const bProv = document.getElementById("active-broker-provider");
      if (bBal) bBal.innerText = this.formatCurrency(acc.balance);
      if (bEq) bEq.innerText = this.formatCurrency(acc.equity);
      if (bFree) bFree.innerText = this.formatCurrency(acc.free_margin ?? acc.balance);
      if (bProv) bProv.innerText = acc.broker || "Paper Simulator";

      const killBtn = document.getElementById("btn-global-kill-switch");
      if (killBtn) {
        if (data.kill_switch_active) {
          killBtn.classList.add("active");
          killBtn.innerText = "LOCKED (Kill Switch)";
        } else {
          killBtn.classList.remove("active");
          killBtn.innerText = "Emergency Stop All";
        }
      }

      const modeSelect = document.getElementById("select-trading-mode");
      if (modeSelect) modeSelect.value = data.trading_mode;

      this.calculateOrderRiskPreview();

    } catch (e) {
      console.error(e);
    }
  }

  initTradingViewWidget(symbol, timeframe) {
    const container = document.getElementById("tradingview_embed_widget");
    if (!container) return;
    if (typeof TradingView === "undefined") {
      console.warn("TradingView library not loaded yet.");
      return;
    }

    const tvSym = TV_SYMBOLS[symbol] || symbol;
    const tvTf = TV_TIMEFRAMES[timeframe] || "15";

    container.innerHTML = "";
    try {
      this.tvWidget = new TradingView.widget({
        autosize: true,
        symbol: tvSym,
        interval: tvTf,
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        enable_publishing: false,
        allow_symbol_change: true,
        container_id: "tradingview_embed_widget",
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        withdateranges: true,
        details: true,
        hotlist: true,
        calendar: true
      });
    } catch (e) {
      console.error("Failed to mount TradingView widget:", e);
    }
  }

  switchChartMode(mode) {
    this.chartMode = mode;
    const tvContainer = document.getElementById("tradingview-widget-container");
    const smcContainer = document.getElementById("main-tradingview-chart");
    const smcLegend = document.getElementById("smc-legend-indicators");
    const btnTv = document.getElementById("btn-chart-mode-tv");
    const btnSmc = document.getElementById("btn-chart-mode-smc");

    if (mode === "tradingview") {
      if (tvContainer) tvContainer.style.display = "block";
      if (smcContainer) smcContainer.style.display = "none";
      if (smcLegend) smcLegend.style.display = "none";
      if (btnTv) btnTv.className = "btn btn-sm btn-primary";
      if (btnSmc) btnSmc.className = "btn btn-sm btn-secondary";
      this.initTradingViewWidget(this.activeSymbol, this.activeTimeframe);
    } else {
      if (tvContainer) tvContainer.style.display = "none";
      if (smcContainer) smcContainer.style.display = "block";
      if (smcLegend) smcLegend.style.display = "inline-block";
      if (btnTv) btnTv.className = "btn btn-sm btn-secondary";
      if (btnSmc) btnSmc.className = "btn btn-sm btn-primary";
      // Allow browser to calculate non-zero dimensions after display block
      setTimeout(() => {
        if (this.chart) {
          this.chart.fitContent();
          this.loadChartSymbol(this.activeSymbol, this.activeTimeframe);
        }
      }, 50);
    }
  }

  fitChart() {
    if (this.chartMode === "tradingview") {
      this.initTradingViewWidget(this.activeSymbol, this.activeTimeframe);
      this.showToast("TradingView chart refit to window.", "info");
    } else if (this.chart) {
      this.chart.fitContent();
      this.loadChartSymbol(this.activeSymbol, this.activeTimeframe);
      this.showToast("AI SMC Overlays refit & synchronized with live data.", "info");
    }
  }

  async loadChartSymbol(symbol, timeframe) {
    this.activeSymbol = symbol;
    this.activeTimeframe = timeframe;

    const selectEl = document.getElementById("chart-symbol-select");
    if (selectEl && selectEl.value !== symbol) {
      selectEl.value = symbol;
    }

    if (this.chartMode === "tradingview") {
      this.initTradingViewWidget(symbol, timeframe);
    }

    // Load custom candlestick and SMC annotations in parallel
    try {
      const [barsRes, analysisRes] = await Promise.all([
        fetch(`/api/market-data/bars/${symbol}/${timeframe}`),
        fetch(`/api/market-data/analysis/${symbol}/${timeframe}`)
      ]);

      const bars = await barsRes.json();
      const analysis = await analysisRes.json();

      if (this.chart) {
        this.chart.activeSymbol = symbol;
        this.chart.activeTimeframe = timeframe;
        this.chart.loadData(bars);
        this.chart.applySMCAnnotations(analysis);
      }
    } catch (e) {
      console.warn("Market data fetch error:", e);
    }
  }

  async fetchSignals() {
    const res = await fetch("/api/signals");
    const signals = await res.json();
    const container = document.getElementById("signals-feed-container");
    if (!container) return;

    if (signals.length === 0) {
      container.innerHTML = `<div style="color:#94a3b8; text-align:center; padding:30px;">No active trade signals. Click 'Scan Live Setups' above to run the strategy engine.</div>`;
      return;
    }

    container.innerHTML = "";
    signals.forEach((sig) => {
      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "14px";
      const isBuy = sig.direction === "BUY";

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
          <div>
            <span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}">${sig.direction}</span>
            <span style="font-weight:700; font-size:1.1rem; margin-left:8px;">${sig.symbol}</span>
            <span style="color:#94a3b8; font-size:0.8rem; margin-left:6px;">${sig.timeframe}</span>
            <span class="badge" style="background:#1e293b; color:#38bdf8; margin-left:8px;">Score: ${sig.confidence_score.toFixed(1)}%</span>
          </div>
          <div>
            ${sig.status === 'PENDING_APPROVAL' ? `
              <button class="btn btn-sm btn-success" onclick="window.app.approveSignal('${sig.id}')">Approve & Execute</button>
              <button class="btn btn-sm btn-danger" style="margin-left:6px;" onclick="window.app.rejectSignal('${sig.id}')">Reject</button>
            ` : `<span class="badge badge-pending">${sig.status}</span>`}
          </div>
        </div>

        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-bottom:12px; font-size:0.82rem; background:#182234; padding:10px; border-radius:6px;">
          <div><span style="color:#94a3b8;">Entry:</span> <strong>${sig.entry_price}</strong></div>
          <div><span style="color:#94a3b8;">Stop Loss:</span> <strong style="color:#ef4444;">${sig.stop_loss}</strong></div>
          <div><span style="color:#94a3b8;">Take Profit:</span> <strong style="color:#10b981;">${sig.take_profit}</strong></div>
          <div><span style="color:#94a3b8;">Size:</span> <strong>${sig.position_size_lots} Lots</strong> (${sig.risk_reward_ratio}:1 R:R)</div>
        </div>

        <div style="font-size:0.83rem; color:#cbd5e1; line-height:1.4;">
          <strong>AI Structural Thesis:</strong> ${sig.market_structure_summary || "Conditions strictly matched user strategy."}
        </div>
      `;
      container.appendChild(card);
    });
  }

  async approveSignal(signalId) {
    const res = await fetch(`/api/signals/approve/${signalId}`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      this.showToast(`Signal authorized! Executed ticket #${data.ticket}`, "success");
      this.fetchSignals();
    } else {
      this.showToast(`Execution rejected: ${data.error}`, "danger");
    }
  }

  async rejectSignal(signalId) {
    await fetch(`/api/signals/reject/${signalId}`, { method: "POST" });
    this.showToast("Signal declined.", "info");
    this.fetchSignals();
  }

  async fetchPositions() {
    const res = await fetch("/api/positions");
    const positions = await res.json();
    this.renderPositionsTable(positions);
  }

  renderPositionsTable(positions) {
    const tbody = document.getElementById("positions-table-body");
    if (!tbody) return;

    if (positions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:#94a3b8; padding:20px;">No open positions currently active.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    positions.forEach((p) => {
      const tr = document.createElement("tr");
      const isBuy = p.direction === "BUY";
      const pnl = p.pnl;
      tr.innerHTML = `
        <td><strong>#${p.ticket}</strong></td>
        <td><strong>${p.symbol}</strong></td>
        <td><span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}">${p.direction}</span></td>
        <td>${p.volume}</td>
        <td>${p.entry_price}</td>
        <td>${p.current_price}</td>
        <td style="color:#ef4444;">${p.stop_loss || '-'}</td>
        <td style="color:#10b981;">${p.take_profit || '-'}</td>
        <td style="font-weight:700; color:${pnl >= 0 ? '#10b981' : '#ef4444'};">
          ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}
        </td>
        <td>
          <button class="btn btn-sm btn-danger" onclick="window.app.closePosition('${p.ticket}')">Close</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  async closePosition(ticket) {
    if (confirm(`Close position #${ticket} now?`)) {
      const res = await fetch(`/api/positions/close/${ticket}`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        this.showToast(`Position #${ticket} closed. Realized PnL: $${data.realized_pnl}`, "info");
        this.fetchPositions();
      }
    }
  }

  async fetchPropFirm() {
    try {
      const res = await fetch("/api/prop-firm");
      const data = await res.json();
      const curr = data.connected_currency || "USD";

      const setTxt = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
      };

      setTxt("prop-profile-name", data.profile_name);
      setTxt("prop-connected-broker-name", data.connected_broker || "Paper Simulator");
      setTxt("prop-live-equity", this.formatCurrency(data.current_equity, curr));
      setTxt("prop-base-size", this.formatCurrency(data.starting_balance, curr));

      setTxt("prop-daily-loss-rem", this.formatCurrency(data.daily_drawdown_remaining, curr));
      setTxt("prop-daily-loss-sub", `5% Limit: ${this.formatCurrency(data.daily_loss_limit, curr)}`);

      setTxt("prop-overall-loss-rem", this.formatCurrency(data.overall_drawdown_remaining, curr));
      setTxt("prop-overall-loss-sub", `10% Limit: ${this.formatCurrency(data.overall_drawdown_limit, curr)}`);

      setTxt("prop-profit-progress", `${data.profit_progress_percent}%`);
      setTxt("prop-profit-sub", `Target: ${this.formatCurrency(data.profit_target_amount, curr)} (${data.rules?.profit_target_step1_percent || 10}%)`);

      setTxt("prop-trading-days", `${data.trading_days_completed} / ${data.minimum_trading_days} Days`);
      setTxt("prop-rule-max-lot", `${data.rules?.max_lot_size || 10.0} Lots`);
      setTxt("prop-rule-weekend", data.rules?.weekend_holding_allowed ? "ALLOWED" : "FORBIDDEN");
      setTxt("prop-rule-dd-type", data.rules?.drawdown_type === "equity_based" ? "Equity-Based" : "Balance-Based");

      const badge = document.getElementById("prop-compliance-badge");
      if (badge) {
        if (data.is_breached) {
          badge.className = "badge badge-bearish";
          badge.innerText = "BREACHED";
        } else {
          badge.className = "badge badge-bullish";
          badge.innerText = "COMPLIANT";
        }
      }

      const breachAlert = document.getElementById("prop-breach-banner");
      if (breachAlert) {
        if (data.is_breached) {
          breachAlert.style.display = "block";
          breachAlert.innerText = `CRITICAL: ${data.breach_reason}. Trading is locked!`;
        } else {
          breachAlert.style.display = "none";
        }
      }

      const profSelect = document.getElementById("select-prop-profile");
      if (profSelect && data.profile_name) profSelect.value = data.profile_name;
      const tierSelect = document.getElementById("select-prop-tier");
      if (tierSelect && data.starting_balance) tierSelect.value = String(parseInt(data.starting_balance));

    } catch (e) {
      console.error("Failed to load prop firm metrics:", e);
    }
  }

  async syncPropFirmWithAccount() {
    this.showToast("Synchronizing Prop Firm Challenge with connected account...", "info");
    try {
      const res = await fetch("/api/prop-firm/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const data = await res.json();
      this.showToast(data.message, "success");
      await this.fetchPropFirm();
    } catch (e) {
      this.showToast("Failed to sync challenge tier: " + e.message, "danger");
    }
  }

  async changePropProfile(profile) {
    const tier = parseFloat(document.getElementById("select-prop-tier").value) || 10000;
    try {
      await fetch("/api/prop-firm/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_name: profile, starting_balance: tier })
      });
      this.showToast(`Prop firm profile set to ${profile}`, "info");
      await this.fetchPropFirm();
    } catch (e) {
      console.error(e);
    }
  }

  async changePropTier(tier) {
    const profile = document.getElementById("select-prop-profile").value;
    try {
      await fetch("/api/prop-firm/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_name: profile, starting_balance: parseFloat(tier) })
      });
      this.showToast(`Challenge size set to $${Number(tier).toLocaleString()}`, "info");
      await this.fetchPropFirm();
    } catch (e) {
      console.error(e);
    }
  }

  async fetchCalendar() {
    try {
      const res = await fetch("/api/economic-calendar");
      const data = await res.json();
      this.allCalendarEvents = data.events || [];

      // Update Blackout buffer controls if config provided
      if (data.config) {
        const preEl = document.getElementById("cal-pre-buffer");
        const postEl = document.getElementById("cal-post-buffer");
        const highEl = document.getElementById("cal-block-high");
        const medEl = document.getElementById("cal-block-med");

        if (preEl) preEl.value = data.config.pre_news_buffer_minutes;
        if (postEl) postEl.value = data.config.post_news_buffer_minutes;
        if (highEl) highEl.checked = data.config.block_high_impact;
        if (medEl) medEl.checked = data.config.block_medium_impact;
      }

      this.renderCalendarTable();
    } catch (e) {
      console.error("Failed to load economic calendar:", e);
    }
  }

  renderCalendarTable() {
    const tbody = document.getElementById("calendar-table-body");
    if (!tbody) return;

    let filtered = [...this.allCalendarEvents];

    // Filter by currency
    if (this.calendarCurrencyFilter && this.calendarCurrencyFilter !== "ALL") {
      filtered = filtered.filter((e) => e.currency === this.calendarCurrencyFilter);
    }

    // Filter by impact
    if (this.calendarImpactFilter === "HIGH") {
      filtered = filtered.filter((e) => e.impact === "HIGH");
    } else if (this.calendarImpactFilter === "MEDIUM") {
      filtered = filtered.filter((e) => e.impact === "HIGH" || e.impact === "MEDIUM");
    }

    // Filter by search query
    if (this.calendarSearchQuery) {
      filtered = filtered.filter((e) => 
        e.title.toLowerCase().includes(this.calendarSearchQuery) ||
        e.currency.toLowerCase().includes(this.calendarSearchQuery)
      );
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;">No economic events match the current filter (${this.calendarCurrencyFilter} / ${this.calendarImpactFilter}).</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    filtered.forEach((ev) => {
      const tr = document.createElement("tr");

      // Impact badge
      let impactHtml = "";
      if (ev.impact === "HIGH") {
        impactHtml = `<span style="display:inline-flex; align-items:center; gap:4px; font-weight:800; color:#ef4444;"><span style="width:10px; height:10px; background:#ef4444; border-radius:2px; display:inline-block;"></span> HIGH</span>`;
      } else if (ev.impact === "MEDIUM") {
        impactHtml = `<span style="display:inline-flex; align-items:center; gap:4px; font-weight:700; color:#f59e0b;"><span style="width:10px; height:10px; background:#f59e0b; border-radius:2px; display:inline-block;"></span> MED</span>`;
      } else if (ev.impact === "LOW") {
        impactHtml = `<span style="display:inline-flex; align-items:center; gap:4px; color:#94a3b8;"><span style="width:10px; height:10px; background:#eab308; border-radius:2px; display:inline-block;"></span> LOW</span>`;
      } else {
        impactHtml = `<span style="display:inline-flex; align-items:center; gap:4px; color:#64748b;"><span style="width:10px; height:10px; background:#64748b; border-radius:2px; display:inline-block;"></span> HOL</span>`;
      }

      // Status badge
      let statusHtml = "";
      if (ev.status === "ACTIVE_BLACKOUT") {
        statusHtml = `<span class="badge" style="background:#dc2626; color:#ffffff; font-weight:800; border:1px solid #ef4444;">🔴 BLACKOUT ACTIVE</span>`;
      } else if (ev.status === "UPCOMING") {
        statusHtml = `<span class="badge" style="background:#1e293b; color:#38bdf8; border:1px solid #0284c7;">${ev.time_display}</span>`;
      } else {
        statusHtml = `<span class="badge" style="background:#1e293b; color:#64748b; border:1px solid #334155;">${ev.time_display}</span>`;
      }

      tr.innerHTML = `
        <td style="font-size:0.82rem; white-space:nowrap;">
          <div style="font-weight:800; color:#38bdf8; font-size:0.9rem;">${ev.time_ist || ev.time_utc} IST</div>
          <div style="font-weight:600; color:#f8fafc; font-size:0.76rem;">${ev.date_ist || ev.date_formatted}</div>
          <div style="color:#64748b; font-size:0.7rem;">${ev.time_utc} UTC (${ev.time_local_est} ET)</div>
        </td>
        <td>
          <span class="badge" style="background:#1e293b; color:#f8fafc; font-weight:800; border:1px solid #475569; padding:2px 6px;">
            ${ev.currency}
          </span>
        </td>
        <td style="text-align:center;">
          ${impactHtml}
        </td>
        <td>
          <a href="${ev.url}" target="_blank" style="color:#f8fafc; font-weight:600; text-decoration:none; display:inline-flex; align-items:center; gap:4px;" title="View on Forex Factory">
            ${ev.title}
            <span style="font-size:0.7rem; color:#64748b;">↗</span>
          </a>
        </td>
        <td>
          ${statusHtml}
        </td>
        <td style="text-align:right; font-weight:700; color:#38bdf8; font-size:0.85rem;">
          ${ev.forecast}
        </td>
        <td style="text-align:right; color:#94a3b8; font-size:0.85rem;">
          ${ev.previous}
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  filterCalendarCurrency(currency) {
    this.calendarCurrencyFilter = currency;
    document.querySelectorAll(".cal-curr-btn").forEach((btn) => {
      if (btn.getAttribute("data-currency") === currency) {
        btn.className = "btn btn-sm btn-primary cal-curr-btn active";
      } else {
        btn.className = "btn btn-sm btn-secondary cal-curr-btn";
      }
    });
    this.renderCalendarTable();
  }

  filterCalendarImpact(impact) {
    this.calendarImpactFilter = impact;
    document.querySelectorAll(".cal-imp-btn").forEach((btn) => {
      btn.className = "btn btn-sm btn-secondary cal-imp-btn";
    });
    if (impact === "ALL") {
      const b = document.getElementById("btn-imp-all");
      if (b) b.className = "btn btn-sm btn-primary cal-imp-btn active";
    } else if (impact === "MEDIUM") {
      const b = document.getElementById("btn-imp-med");
      if (b) b.className = "btn btn-sm btn-primary cal-imp-btn active";
    } else if (impact === "HIGH") {
      const b = document.getElementById("btn-imp-high");
      if (b) b.className = "btn btn-sm btn-primary cal-imp-btn active";
    }
    this.renderCalendarTable();
  }

  searchCalendarEvents(query) {
    this.calendarSearchQuery = (query || "").trim().toLowerCase();
    this.renderCalendarTable();
  }

  async syncForexFactoryNews() {
    this.showToast("Fetching live news from Forex Factory...", "info");
    try {
      const res = await fetch("/api/economic-calendar/refresh", { method: "POST" });
      const data = await res.json();
      this.showToast(data.message, "success");
      await this.fetchCalendar();
    } catch (e) {
      this.showToast("Failed to refresh Forex Factory feed: " + e.message, "danger");
    }
  }

  async saveCalendarConfig() {
    const pre = parseInt(document.getElementById("cal-pre-buffer").value) || 30;
    const post = parseInt(document.getElementById("cal-post-buffer").value) || 30;
    const blockHigh = document.getElementById("cal-block-high").checked;
    const blockMed = document.getElementById("cal-block-med").checked;

    try {
      const res = await fetch("/api/economic-calendar/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pre_news_buffer_minutes: pre,
          post_news_buffer_minutes: post,
          block_high_impact: blockHigh,
          block_medium_impact: blockMed
        })
      });
      const data = await res.json();
      this.showToast("Forex Factory news blackout parameters updated!", "success");
      await this.fetchCalendar();
    } catch (e) {
      this.showToast("Failed to update blackout parameters: " + e.message, "danger");
    }
  }

  async fetchJournal() {
    const res = await fetch("/api/journal");
    const entries = await res.json();
    const container = document.getElementById("journal-entries-container");
    if (!container) return;

    if (entries.length === 0) {
      container.innerHTML = `<div style="text-align:center; color:#94a3b8; padding:30px;">No trades logged yet. Closed positions are automatically recorded here.</div>`;
      return;
    }

    container.innerHTML = "";
    entries.forEach((j) => {
      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "10px";
      const isWin = j.net_profit > 0;

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
          <div>
            <strong>#${j.ticket}</strong> - <span style="font-weight:700;">${j.symbol}</span> (${j.direction})
            <span class="badge" style="background:#1e293b; color:#38bdf8; margin-left:6px;">${j.strategy_name}</span>
          </div>
          <div style="font-size:1.05rem; font-weight:700; color:${isWin ? '#10b981' : '#ef4444'};">
            ${isWin ? '+' : ''}$${j.net_profit.toFixed(2)} (${j.risk_reward_achieved}R)
          </div>
        </div>
        <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:6px;">
          Entry: ${j.entry_price} | Exit: ${j.exit_price} | Lots: ${j.lots} | Closed: ${j.exit_time}
        </div>
        <div style="font-size:0.82rem; color:#cbd5e1;">
          <strong>Entry Rationale:</strong> ${j.entry_reason} | <strong>Exit:</strong> ${j.exit_reason}
        </div>
      `;
      container.appendChild(card);
    });
  }

  async fetchAnalytics() {
    const res = await fetch("/api/analytics");
    const data = await res.json();
    document.getElementById("analytics-total-trades").innerText = data.total_trades;
    document.getElementById("analytics-win-rate").innerText = `${data.win_rate}%`;
    document.getElementById("analytics-total-pnl").innerText = `$${data.total_profit.toFixed(2)}`;
  }

  async fetchAIAnalysis() {
    const symbol = document.getElementById("ai-analysis-symbol") ? document.getElementById("ai-analysis-symbol").value : "EURUSD";
    const tf = document.getElementById("ai-analysis-tf") ? document.getElementById("ai-analysis-tf").value : "15M";

    const res = await fetch(`/api/market-data/analysis/${symbol}/${tf}`);
    const data = await res.json();
    const container = document.getElementById("ai-analysis-results-card");
    if (!container) return;

    container.innerHTML = `
      <div style="margin-bottom:16px;">
        <h3 style="font-size:1.1rem; color:#38bdf8; margin-bottom:6px;">Market Structure Bias: ${data.trend}</h3>
        <p style="color:#94a3b8; font-size:0.85rem;">Analysis calculated over ${data.bar_count} candles on ${symbol} (${tf}).</p>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-bottom:16px;">
        <div class="card">
          <h4 style="font-size:0.85rem; color:#94a3b8; margin-bottom:6px;">Break of Structure (BOS)</h4>
          <div style="font-size:1.1rem; font-weight:700;">${data.boss.length} Detected</div>
          <div style="font-size:0.75rem; color:#94a3b8;">${data.boss.length ? data.boss[data.boss.length - 1].type : 'None'}</div>
        </div>
        <div class="card">
          <h4 style="font-size:0.85rem; color:#94a3b8; margin-bottom:6px;">Change of Character (CHOCH)</h4>
          <div style="font-size:1.1rem; font-weight:700;">${data.chochs.length} Detected</div>
          <div style="font-size:0.75rem; color:#94a3b8;">${data.chochs.length ? data.chochs[data.chochs.length - 1].type : 'None'}</div>
        </div>
        <div class="card">
          <h4 style="font-size:0.85rem; color:#94a3b8; margin-bottom:6px;">Fair Value Gaps (FVG)</h4>
          <div style="font-size:1.1rem; font-weight:700;">${data.fvgs.length} Imbalances</div>
          <div style="font-size:0.75rem; color:#94a3b8;">Unmitigated zones available</div>
        </div>
        <div class="card">
          <h4 style="font-size:0.85rem; color:#94a3b8; margin-bottom:6px;">Order Blocks (OB)</h4>
          <div style="font-size:1.1rem; font-weight:700;">${data.order_blocks.length} Institutional Zones</div>
          <div style="font-size:0.75rem; color:#94a3b8;">Displacement validated</div>
        </div>
      </div>
    `;
  }

  async populateBacktestStrategies() {
    const select = document.getElementById("bt-strategy");
    if (!select) return;
    try {
      const res = await fetch("/api/strategies", {
        headers: this.getAuthHeaders()
      });
      const strategies = await res.json();
      select.innerHTML = "";
      strategies.forEach((strat) => {
        const opt = document.createElement("option");
        opt.value = strat.id;
        const prefix = strat.user_id && strat.user_id !== "SYSTEM" ? "🔒 [Private] " : "🏛️ ";
        opt.innerText = `${prefix}${strat.name} (${strat.strategy_type})`;
        select.appendChild(opt);
      });
    } catch (e) {
      console.warn("Failed to load backtest strategies:", e);
    }
  }

  async runBacktest() {
    const symbol = document.getElementById("bt-symbol").value;
    const timeframe = document.getElementById("bt-timeframe").value;
    const balance = parseFloat(document.getElementById("bt-balance").value) || 10000;
    const risk = parseFloat(document.getElementById("bt-risk").value) || 1.0;
    const stratId = document.getElementById("bt-strategy") ? document.getElementById("bt-strategy").value : null;
    const barsCount = parseInt(document.getElementById("bt-bars-count") ? document.getElementById("bt-bars-count").value : 500) || 500;

    const btn = document.getElementById("btn-run-backtest");
    btn.innerText = "Simulating History...";
    btn.disabled = true;

    try {
      const res = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          timeframe,
          starting_balance: balance,
          risk_percent: risk,
          strategy_id: stratId,
          bars_count: barsCount
        })
      });
      const data = await res.json();
      this.renderBacktestResults(data);
    } catch (e) {
      alert("Backtest failed: " + e.message);
    } finally {
      btn.innerText = "Run Historical Simulation";
      btn.disabled = false;
    }
  }

  renderBacktestResults(data) {
    if (data.error && !data.summary) {
      alert("Backtest Notice: " + data.error);
      return;
    }
    const s = data.summary || {
      total_trades: 0, win_rate: 0, profit_factor: 0, net_profit: 0, return_percent: 0,
      max_drawdown_percent: 0, max_drawdown_amount: 0, avg_risk_reward: 0, max_consecutive_wins: 0, max_consecutive_losses: 0
    };
    document.getElementById("bt-results-panel").style.display = "block";
    document.getElementById("bt-total-trades").innerText = s.total_trades;
    document.getElementById("bt-win-rate").innerText = `${s.win_rate}%`;
    document.getElementById("bt-profit-factor").innerText = s.profit_factor;
    document.getElementById("bt-net-profit").innerText = `${s.net_profit >= 0 ? '+' : ''}$${Number(s.net_profit).toFixed(2)} (${s.return_percent}%)`;
    document.getElementById("bt-max-dd").innerText = `${s.max_drawdown_percent}% ($${Number(s.max_drawdown_amount).toFixed(2)})`;
    document.getElementById("bt-avg-rr").innerText = `${s.avg_risk_reward}:1`;
    document.getElementById("bt-consec-wins").innerText = s.max_consecutive_wins;
    document.getElementById("bt-consec-losses").innerText = s.max_consecutive_losses;

    // Render trades list
    const tbody = document.getElementById("bt-trades-table-body");
    if (tbody) {
      tbody.innerHTML = "";
      if (!data.trades || data.trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#94a3b8; padding:20px;">No simulated trades triggered with these exact rule combinations. Try selecting another strategy or increasing historical depth.</td></tr>`;
      } else {
        data.trades.slice(-30).forEach((t) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>#${t.trade_num}</td>
            <td><span class="badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.direction}</span></td>
            <td>${t.entry_time}</td>
            <td>${t.entry_price}</td>
            <td>${t.exit_price}</td>
            <td>${t.lots}</td>
            <td style="font-weight:700; color:${t.net_pnl > 0 ? '#10b981' : '#ef4444'};">${t.net_pnl > 0 ? '+' : ''}$${Number(t.net_pnl).toFixed(2)}</td>
            <td>${t.exit_reason}</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }
  }

  async fetchNotifications() {
    const res = await fetch("/api/notifications");
    const notifs = await res.json();
    const container = document.getElementById("notifications-feed-container");
    if (!container) return;

    container.innerHTML = "";
    notifs.forEach((n) => {
      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "8px";
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <span style="font-weight:700; color:#38bdf8;">${n.title}</span>
          <span style="font-size:0.75rem; color:#94a3b8;">${n.timestamp}</span>
        </div>
        <p style="font-size:0.83rem; color:#cbd5e1;">${n.message}</p>
      `;
      container.appendChild(card);
    });
  }

  async fetchAuditLogs() {
    const res = await fetch("/api/audit-logs");
    const logs = await res.json();
    const tbody = document.getElementById("audit-logs-body");
    if (!tbody) return;

    tbody.innerHTML = "";
    logs.forEach((l) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${l.timestamp}</td>
        <td><strong>${l.event_type}</strong></td>
        <td><span class="badge ${l.severity === 'CRITICAL' ? 'badge-bearish' : 'badge-pending'}">${l.severity}</span></td>
        <td>${l.message}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  async fetchBrokerConfig() {
    try {
      const res = await fetch("/api/broker/config");
      const data = await res.json();
      const b = data.active_broker || {};

      this.activeCurrency = b.currency || "USD";
      this.accountBalance = b.balance || 0;

      const providerEl = document.getElementById("active-broker-provider");
      if (providerEl) providerEl.innerText = b.broker || "Paper Simulator";

      const balEl = document.getElementById("active-broker-balance");
      if (balEl) balEl.innerText = this.formatCurrency(b.balance || 0);

      const eqEl = document.getElementById("active-broker-equity");
      if (eqEl) eqEl.innerText = this.formatCurrency(b.equity || 0);

      const freeEl = document.getElementById("active-broker-free-margin");
      if (freeEl) freeEl.innerText = this.formatCurrency(b.free_margin ?? b.balance ?? 0);

      const topLabel = document.getElementById("top-broker-label");
      if (topLabel) topLabel.innerText = `Broker: ${b.broker || 'Paper'}`;

      const topBal = document.getElementById("top-balance");
      const topEq = document.getElementById("top-equity");
      if (topBal) topBal.innerText = this.formatCurrency(b.balance || 0);
      if (topEq) topEq.innerText = this.formatCurrency(b.equity || 0);

      const badgeEl = document.getElementById("broker-status-badge");
      if (badgeEl) {
        if (b.is_connected) {
          badgeEl.className = "badge badge-bullish";
          badgeEl.innerText = "ONLINE & CONNECTED";
        } else {
          badgeEl.className = "badge badge-bearish";
          badgeEl.innerText = "DISCONNECTED";
        }
      }

      // Pre-fill inputs if available
      if (data.credentials) {
        if (data.credentials.login && document.getElementById("mt5-login")) {
          document.getElementById("mt5-login").value = data.credentials.login;
        }
        if (data.credentials.server && document.getElementById("mt5-server")) {
          document.getElementById("mt5-server").value = data.credentials.server;
        }
        if (data.credentials.api_key && document.getElementById("binance-api-key")) {
          document.getElementById("binance-api-key").value = data.credentials.api_key;
        }
      }
    } catch (e) {
      console.error("Failed to fetch broker config:", e);
    }
    this.checkMT5BridgeStatus();
  }

  async checkMT5BridgeStatus() {
    const label = document.getElementById("mt5-bridge-status-label");
    const webrequestUrl = document.getElementById("mt5-bridge-webrequest-url");
    if (webrequestUrl) {
      webrequestUrl.innerText = window.location.origin;
    }
    if (!label) return;
    try {
      const res = await fetch("/api/bridge/status");
      const data = await res.json();
      if (data.active && data.account) {
        label.innerHTML = `<span style="color:#10b981;">🟢 Live Connected (Acc #${data.account.login || "N/A"} - $${Number(data.account.balance || 0).toLocaleString()})</span>`;
      } else {
        label.innerHTML = `<span style="color:#f59e0b;">⏳ Waiting for MT5 EA ping...</span>`;
      }
    } catch (e) {
      label.innerText = "Offline";
    }
  }

  async connectMT5Account() {
    this.showToast("Checking live MT5 Bridge connection...", "info");
    try {
      const res = await fetch("/api/broker/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          broker: "mt5",
          credentials: {}
        })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message, "success");
        await this.fetchBrokerConfig();
        await this.refreshDashboard();
        this.checkMT5BridgeStatus();
      } else {
        await this.checkMT5BridgeStatus();
        alert(data.message || "Failed to connect to MT5.");
      }
    } catch (e) {
      alert("Connection error: " + e.message);
    }
  }

  async connectBinanceAccount() {
    const apiKey = document.getElementById("binance-api-key").value;
    const apiSecret = document.getElementById("binance-api-secret").value;
    const testnet = document.getElementById("binance-testnet").checked;

    if (!apiKey || !apiSecret) {
      alert("Please enter both Binance API Key and API Secret.");
      return;
    }

    this.showToast("Verifying Binance API connection...", "info");
    try {
      const res = await fetch("/api/broker/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          broker: "binance",
          credentials: { api_key: apiKey, api_secret: apiSecret, testnet }
        })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message, "success");
        await this.fetchBrokerConfig();
        await this.refreshDashboard();
      } else {
        alert(data.message || "Failed to connect to Binance.");
      }
    } catch (e) {
      alert("Connection error: " + e.message);
    }
  }

  async connectCTraderAccount() {
    const clientId = document.getElementById("ctrader-client-id").value;
    const clientSecret = document.getElementById("ctrader-client-secret").value;
    const accountId = document.getElementById("ctrader-account-id").value;

    if (!clientId || !clientSecret || !accountId) {
      alert("Please provide cTrader Client ID, Secret, and Account ID.");
      return;
    }

    try {
      const res = await fetch("/api/broker/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          broker: "ctrader",
          credentials: { client_id: clientId, client_secret: clientSecret, account_id: accountId }
        })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message, "success");
        await this.fetchBrokerConfig();
        await this.refreshDashboard();
      } else {
        alert(data.message || "cTrader connection failed.");
      }
    } catch (e) {
      alert("Error: " + e.message);
    }
  }

  async switchToPaperBroker() {
    if (confirm("Switch back to the Risk-Free Paper Trading Simulator?")) {
      const res = await fetch("/api/broker/disconnect", { method: "POST" });
      const data = await res.json();
      this.showToast("Switched back to Paper Trading Simulator.", "info");
      await this.fetchBrokerConfig();
      await this.refreshDashboard();
    }
  }

  async configurePaperBalance() {
    const balance = parseFloat(document.getElementById("paper-initial-balance").value) || 10000;
    const res = await fetch("/api/broker/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        broker: "paper",
        credentials: { initial_balance: balance }
      })
    });
    const data = await res.json();
    this.showToast(`Paper Trading balance updated to $${balance.toLocaleString()}`, "success");
    await this.fetchBrokerConfig();
    await this.refreshDashboard();
  }

  setOrderType(type) {
    this.selectedOrderType = type;
    const mktBtn = document.getElementById("tab-order-market");
    const lmtBtn = document.getElementById("tab-order-limit");
    const priceGroup = document.getElementById("group-order-price");

    if (type === "MARKET") {
      if (mktBtn) mktBtn.className = "btn btn-sm btn-primary";
      if (lmtBtn) lmtBtn.className = "btn btn-sm btn-secondary";
      if (priceGroup) priceGroup.style.display = "none";
    } else {
      if (mktBtn) mktBtn.className = "btn btn-sm btn-secondary";
      if (lmtBtn) lmtBtn.className = "btn btn-sm btn-primary";
      if (priceGroup) priceGroup.style.display = "block";
    }
    this.updateSubmitButtonText();
  }

  setTradeDirection(direction) {
    this.selectedDirection = direction;
    const sellBtn = document.getElementById("btn-select-sell");
    const buyBtn = document.getElementById("btn-select-buy");
    const submitBtn = document.getElementById("btn-submit-order");

    if (direction === "BUY") {
      if (buyBtn) buyBtn.style.border = "2px solid #ffffff";
      if (sellBtn) sellBtn.style.border = "none";
      if (submitBtn) {
        submitBtn.className = "btn btn-success";
      }
    } else {
      if (sellBtn) sellBtn.style.border = "2px solid #ffffff";
      if (buyBtn) buyBtn.style.border = "none";
      if (submitBtn) {
        submitBtn.className = "btn btn-danger";
      }
    }
    this.updateSubmitButtonText();
    this.calculateOrderRiskPreview();
  }

  adjustLotSize(amount) {
    const input = document.getElementById("order-volume");
    if (input) {
      input.value = amount.toFixed(2);
      this.calculateOrderRiskPreview();
      this.updateSubmitButtonText();
    }
  }

  updateSubmitButtonText(quote) {
    const submitBtn = document.getElementById("btn-submit-order");
    const volInput = document.getElementById("order-volume");
    if (!submitBtn) return;

    const vol = volInput ? volInput.value : "0.10";
    const dir = this.selectedDirection;
    const type = this.selectedOrderType;

    let priceStr = "";
    if (quote) {
      priceStr = ` @ ${dir === 'BUY' ? quote.ask : quote.bid}`;
    }

    submitBtn.innerText = `🚀 PLACE ${dir} ORDER (${vol} Lots)${priceStr}`;
  }

  calculateOrderRiskPreview() {
    const volInput = document.getElementById("order-volume");
    const slInput = document.getElementById("order-sl");
    const tpInput = document.getElementById("order-tp");

    const vol = parseFloat(volInput ? volInput.value : 0.1) || 0.1;
    const sl = parseFloat(slInput ? slInput.value : 0) || 0;
    const tp = parseFloat(tpInput ? tpInput.value : 0) || 0;

    const previewRiskEl = document.getElementById("ticket-risk-preview");
    const previewSlEl = document.getElementById("preview-sl-val");
    const previewTpEl = document.getElementById("preview-tp-val");
    const previewRrEl = document.getElementById("preview-rr-ratio");

    // Standard $10/pip on 1 lot EURUSD approx
    const pipValue = vol * 10.0;
    if (sl > 0) {
      const pips = Math.abs(1.0850 - sl) * 10000;
      const estLoss = pips * pipValue;
      const riskPercent = (estLoss / (this.accountBalance || 10000)) * 100;
      if (previewSlEl) previewSlEl.innerText = `-${this.formatCurrency(estLoss)}`;
      if (previewRiskEl) previewRiskEl.innerText = `Risk: ~${this.formatCurrency(estLoss)} (${riskPercent.toFixed(1)}%)`;
    } else {
      if (previewSlEl) previewSlEl.innerText = `-${this.formatCurrency(0)}`;
      if (previewRiskEl) previewRiskEl.innerText = `Risk: ~${this.formatCurrency(0)} (0.0%)`;
    }

    if (tp > 0) {
      const pips = Math.abs(tp - 1.0850) * 10000;
      const estGain = pips * pipValue;
      if (previewTpEl) previewTpEl.innerText = `+${this.formatCurrency(estGain)}`;
    } else {
      if (previewTpEl) previewTpEl.innerText = `+${this.formatCurrency(0)}`;
    }

    if (sl > 0 && tp > 0) {
      const slDist = Math.abs(1.0850 - sl);
      const tpDist = Math.abs(tp - 1.0850);
      const rr = slDist > 0 ? (tpDist / slDist).toFixed(1) : "2.0";
      if (previewRrEl) previewRrEl.innerText = `1 : ${rr} R:R`;
    }
  }

  async submitManualTrade() {
    const symbol = this.activeSymbol;
    const direction = this.selectedDirection;
    const order_type = this.selectedOrderType;
    const volume = parseFloat(document.getElementById("order-volume").value) || 0.01;
    const sl = parseFloat(document.getElementById("order-sl").value) || null;
    const tp = parseFloat(document.getElementById("order-tp").value) || null;
    const price = order_type === "LIMIT" ? (parseFloat(document.getElementById("order-price").value) || null) : null;

    const submitBtn = document.getElementById("btn-submit-order");
    submitBtn.innerText = "Executing Order at Broker...";
    submitBtn.disabled = true;

    try {
      const res = await fetch("/api/trade/place", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          direction,
          order_type,
          volume,
          price,
          stop_loss: sl,
          take_profit: tp,
          comment: `Manual ${order_type}`
        })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(`Order Executed! Ticket #${data.ticket} for ${volume} lots ${symbol}`, "success");
        await this.fetchPositions();
        await this.refreshDashboard();
      } else {
        const errMsg = data.error || "Order was rejected by broker risk engine.";
        if (errMsg.toLowerCase().includes("autotrading") || errMsg.toLowerCase().includes("disabled by client") || errMsg.toLowerCase().includes("algo trading")) {
          alert(
            "⚠️ ACTION REQUIRED IN METATRADER 5:\n\n" +
            "MetaTrader 5 blocked this trade with: 'AutoTrading disabled by client'.\n\n" +
            "How to enable buying and selling right now:\n" +
            "1. Open your MetaTrader 5 desktop application window.\n" +
            "2. In the top toolbar, click the 'Algo Trading' button so it turns GREEN (play icon).\n" +
            "3. Go to Tools ➜ Options ➜ Expert Advisors tab and check 'Allow Algo Trading'.\n\n" +
            "Once Algo Trading is green in MT5, click Place Order again to execute immediately!"
          );
        } else {
          alert(errMsg);
        }
      }
    } catch (e) {
      alert("Execution error: " + e.message);
    } finally {
      submitBtn.disabled = false;
      this.updateSubmitButtonText();
    }
  }

  async triggerAIScanForSymbol() {
    const container = document.getElementById("chart-symbol-signals-container");
    if (container) container.innerText = "Evaluating user strategy rules on " + this.activeSymbol + "...";

    try {
      const res = await fetch("/api/signals/scan", { method: "POST" });
      const data = await res.json();
      const symbolSignals = (data.signals || []).filter(s => s.signal && s.signal.symbol === this.activeSymbol);

      if (symbolSignals.length > 0) {
        const sig = symbolSignals[0].signal;
        container.innerHTML = `
          <div style="background:#182234; padding:12px; border-radius:6px; border-left:4px solid #10b981; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <span class="badge ${sig.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}">${sig.direction}</span>
              <strong style="margin-left:8px;">${sig.strategy_name}</strong>
              <span style="color:#94a3b8; font-size:0.8rem; margin-left:6px;">Entry: ${sig.entry_price} | SL: ${sig.stop_loss} | TP: ${sig.take_profit}</span>
            </div>
            <button class="btn btn-sm btn-success" onclick="window.app.prefillOrderFromSignal(${JSON.stringify(sig).replace(/"/g, '&quot;')})">
              Apply to Order Ticket
            </button>
          </div>
        `;
      } else {
        container.innerHTML = `<span style="color:#94a3b8;">Scanned market: No setups currently meet 100% of strategy rules for ${this.activeSymbol}.</span>`;
      }
    } catch (e) {
      container.innerText = "Scan failed: " + e.message;
    }
  }

  prefillOrderFromSignal(sig) {
    this.setTradeDirection(sig.direction);
    document.getElementById("order-volume").value = sig.position_size_lots || 0.10;
    document.getElementById("order-sl").value = sig.stop_loss;
    document.getElementById("order-tp").value = sig.take_profit;
    this.calculateOrderRiskPreview();
    this.showToast(`Applied ${sig.direction} setup parameters to order ticket!`, "info");
  }

  showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "toast";
    if (type === "success") toast.style.borderLeftColor = "#10b981";
    if (type === "danger") toast.style.borderLeftColor = "#ef4444";
    if (type === "warning") toast.style.borderLeftColor = "#f59e0b";

    toast.innerText = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  getAuthHeaders(customHeaders = {}) {
    const headers = { ...customHeaders };
    if (this.authToken) {
      headers["Authorization"] = `Bearer ${this.authToken}`;
    }
    return headers;
  }

  async checkCurrentUser() {
    if (!this.authToken) {
      this.currentUser = null;
      return false;
    }
    try {
      const res = await fetch("/api/auth/me", {
        headers: this.getAuthHeaders()
      });
      const data = await res.json();
      if (data.authenticated && data.user) {
        this.currentUser = data.user;
        this.updateAuthUI();
        return true;
      } else {
        this.currentUser = null;
        localStorage.removeItem("quant_auth_token");
        this.authToken = null;
        return false;
      }
    } catch (e) {
      console.warn("Failed checking user auth status:", e);
      this.currentUser = null;
      return false;
    }
  }

  openAuthModal() {
    if (this.currentUser) {
      this.updateAuthUI();
      this.showToast(`Logged in as @${this.currentUser.username} (${this.currentUser.email})`, "info");
    } else {
      this.showAuthPortal();
    }
  }

  updateAuthUI() {
    const btnOpenAuth = document.getElementById("btn-open-auth-modal");
    const userBadge = document.getElementById("user-profile-badge");
    const topUsername = document.getElementById("top-username");

    if (this.currentUser && this.currentUser.username) {
      if (btnOpenAuth) btnOpenAuth.style.setProperty("display", "none", "important");
      if (userBadge) userBadge.style.setProperty("display", "inline-flex", "important");
      if (topUsername) topUsername.innerText = this.currentUser.username;
    } else {
      if (btnOpenAuth) btnOpenAuth.style.setProperty("display", "inline-flex", "important");
      if (userBadge) userBadge.style.setProperty("display", "none", "important");
    }
  }

  showAuthPortal() {
    const authPortal = document.getElementById("auth-portal-screen");
    const sidebar = document.getElementById("app-sidebar");
    const mainWrapper = document.getElementById("app-main-wrapper");

    if (sidebar) sidebar.style.display = "none";
    if (mainWrapper) mainWrapper.style.display = "none";
    if (authPortal) authPortal.style.display = "flex";
    this.switchAuthMode("LOGIN_CREDENTIALS");
  }

  switchAuthMode(mode) {
    this.authMode = mode;
    this.clearAuthAlert();

    const formLogin = document.getElementById("auth-form-login");
    const formLoginOtp = document.getElementById("auth-form-login-otp");
    const formSignup = document.getElementById("auth-form-signup");
    const formSignupConfirm = document.getElementById("auth-form-signup-confirm");
    const formForgot = document.getElementById("auth-form-forgot-password");
    const formReset = document.getElementById("auth-form-reset-password");
    const tabBar = document.getElementById("auth-tab-bar");
    const tabLoginBtn = document.getElementById("auth-btn-tab-login");
    const tabSignupBtn = document.getElementById("auth-btn-tab-signup");

    // Hide all forms first
    if (formLogin) formLogin.style.display = "none";
    if (formLoginOtp) formLoginOtp.style.display = "none";
    if (formSignup) formSignup.style.display = "none";
    if (formSignupConfirm) formSignupConfirm.style.display = "none";
    if (formForgot) formForgot.style.display = "none";
    if (formReset) formReset.style.display = "none";

    if (mode === "LOGIN_CREDENTIALS") {
      if (tabBar) tabBar.style.display = "flex";
      if (tabLoginBtn) { tabLoginBtn.style.background = "#0284c7"; tabLoginBtn.style.color = "#fff"; }
      if (tabSignupBtn) { tabSignupBtn.style.background = "transparent"; tabSignupBtn.style.color = "#94a3b8"; }
      if (formLogin) formLogin.style.display = "block";
    } else if (mode === "LOGIN_2FA") {
      if (tabBar) tabBar.style.display = "none";
      if (formLoginOtp) formLoginOtp.style.display = "block";
      const otpInput = document.getElementById("login-input-otp");
      if (otpInput) { otpInput.value = ""; setTimeout(() => otpInput.focus(), 100); }
    } else if (mode === "SIGNUP_FORM") {
      if (tabBar) tabBar.style.display = "flex";
      if (tabSignupBtn) { tabSignupBtn.style.background = "#0284c7"; tabSignupBtn.style.color = "#fff"; }
      if (tabLoginBtn) { tabLoginBtn.style.background = "transparent"; tabLoginBtn.style.color = "#94a3b8"; }
      if (formSignup) formSignup.style.display = "block";
    } else if (mode === "SIGNUP_CONFIRM") {
      if (tabBar) tabBar.style.display = "none";
      if (formSignupConfirm) formSignupConfirm.style.display = "block";
      const otpInput = document.getElementById("signup-confirm-input-otp");
      if (otpInput) { otpInput.value = ""; setTimeout(() => otpInput.focus(), 100); }
    } else if (mode === "FORGOT_PASSWORD") {
      if (tabBar) tabBar.style.display = "none";
      if (formForgot) formForgot.style.display = "block";
      const identInput = document.getElementById("forgot-input-ident");
      if (identInput) { identInput.value = ""; setTimeout(() => identInput.focus(), 100); }
    } else if (mode === "RESET_PASSWORD") {
      if (tabBar) tabBar.style.display = "none";
      if (formReset) formReset.style.display = "block";
      const otpInput = document.getElementById("reset-input-otp");
      if (otpInput) { otpInput.value = ""; setTimeout(() => otpInput.focus(), 100); }
    }
  }

  showAuthAlert(message, type = "error") {
    const box = document.getElementById("auth-portal-alert");
    if (!box) return;
    box.style.display = "block";
    box.innerText = message;
    if (type === "success") {
      box.style.background = "#064e3b";
      box.style.color = "#a7f3d0";
      box.style.border = "1px solid #059669";
    } else if (type === "info") {
      box.style.background = "#0c4a6e";
      box.style.color = "#bae6fd";
      box.style.border = "1px solid #0284c7";
    } else {
      box.style.background = "#7f1d1d";
      box.style.color = "#fecaca";
      box.style.border = "1px solid #ef4444";
    }
  }

  clearAuthAlert() {
    const box = document.getElementById("auth-portal-alert");
    if (box) box.style.display = "none";
  }

  async submitLoginCredentials() {
    const identInput = document.getElementById("login-input-ident");
    const passInput = document.getElementById("login-input-password");
    const submitBtn = document.getElementById("btn-submit-login-cred");

    const username = identInput ? identInput.value.trim() : "";
    const password = passInput ? passInput.value : "";

    if (!username || !password) {
      this.showAuthAlert("Please provide both username/email and password.");
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = "Verifying Credentials..."; }

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, direct_login: true })
      });
      const data = await res.json();

      if (res.ok && data.success && data.step === "LOGGED_IN") {
        this.authToken = data.token;
        if (data.token) {
          localStorage.setItem("quant_auth_token", data.token);
        }
        this.currentUser = data.user;
        this.updateAuthUI();
        this.showToast(`Welcome back @${data.user.username}! Terminal unlocked.`, "success");
        await this.initTerminalWorkspace();
        return;
      } else if (res.ok && data.success && data.step === "OTP_REQUIRED") {
        this.currentLoginSessionToken = data.session_token;

        const emailLabel = document.getElementById("login-otp-email-label");
        if (emailLabel) emailLabel.innerText = data.email_masked || "your email";

        this.switchAuthMode("LOGIN_2FA");
        this.showAuthAlert("Verification code sent to your email! Please enter the 6-digit OTP.", "info");
      } else if (data.requires_confirmation) {
        this.currentSignupEmail = data.email;
        const confirmEmailLabel = document.getElementById("signup-confirm-email-label");
        if (confirmEmailLabel) confirmEmailLabel.innerText = data.email;
        this.switchAuthMode("SIGNUP_CONFIRM");
        this.showAuthAlert("Your account is not confirmed yet. A new verification OTP was sent to your email.", "info");
      } else {
        this.showAuthAlert(data.error || data.message || "Invalid credentials.");
      }
    } catch (e) {
      this.showAuthAlert("Connection error: " + e.message);
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = "Sign In & Unlock Terminal 🔐"; }
    }
  }

  async submitLogin2FA() {
    const otpInput = document.getElementById("login-input-otp");
    const submitBtn = document.getElementById("btn-submit-login-otp");
    const otp = otpInput ? otpInput.value.trim() : "";

    if (!otp || otp.length !== 6) {
      this.showAuthAlert("Please enter the complete 6-digit numeric verification code.");
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = "Verifying Code..."; }

    try {
      const res = await fetch("/api/auth/verify-login-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_token: this.currentLoginSessionToken,
          otp_code: otp
        })
      });
      const data = await res.json();

      if (res.ok && data.success && data.token) {
        localStorage.setItem("quant_auth_token", data.token);
        this.authToken = data.token;
        this.currentUser = data.user;
        this.updateAuthUI();
        this.showToast(`Welcome back @${data.user.username}! Terminal unlocked.`, "success");
        await this.initTerminalWorkspace();
        this.updateAuthUI();
      } else {
        this.showAuthAlert(data.error || data.message || "Invalid or expired verification code.");
      }
    } catch (e) {
      this.showAuthAlert("Network error verifying code: " + e.message);
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = "Verify & Unlock Terminal 🚀"; }
    }
  }

  async resendLoginOtp() {
    if (!this.currentLoginSessionToken) return;
    this.showAuthAlert("Resending verification code...", "info");
    try {
      const res = await fetch("/api/auth/resend-login-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_token: this.currentLoginSessionToken })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showAuthAlert("A new verification code has been dispatched to your email.", "info");
      } else {
        this.showAuthAlert(data.error || "Could not resend code. Please try signing in again.");
      }
    } catch (e) {
      this.showAuthAlert("Error resending code: " + e.message);
    }
  }

  async submitSignup() {
    const userInput = document.getElementById("signup-input-username");
    const emailInput = document.getElementById("signup-input-email");
    const passInput = document.getElementById("signup-input-password");
    const confirmInput = document.getElementById("signup-input-confirm");
    const submitBtn = document.getElementById("btn-submit-signup");

    const username = userInput ? userInput.value.trim() : "";
    const email = emailInput ? emailInput.value.trim() : "";
    const password = passInput ? passInput.value : "";
    const confirm = confirmInput ? confirmInput.value : "";

    if (!username || !email || !password) {
      this.showAuthAlert("Please fill in all registration fields.");
      return;
    }

    if (password !== confirm) {
      this.showAuthAlert("Passwords do not match. Please re-enter.");
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = "Creating Account & Sending OTP..."; }

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        if (data.token) {
          this.authToken = data.token;
          localStorage.setItem("quant_auth_token", data.token);
          this.currentUser = { id: data.user_id, username: data.username, email: data.email };
          this.updateAuthUI();
          this.showToast("Account created & activated! Terminal unlocked.", "success");
          await this.initTerminalWorkspace();
          return;
        }

        this.currentSignupEmail = data.email || email;

        const emailLabel = document.getElementById("signup-confirm-email-label");
        if (emailLabel) emailLabel.innerText = this.currentSignupEmail;

        this.switchAuthMode("SIGNUP_CONFIRM");
        this.showAuthAlert("Account registered! A 6-digit confirmation code was sent to your email.", "info");
      } else {
        this.showAuthAlert(data.error || data.message || "Registration failed.");
      }
    } catch (e) {
      this.showAuthAlert("Network error during registration: " + e.message);
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = "Register & Send Confirmation OTP ✉️"; }
    }
  }

  async submitSignupConfirmation() {
    const otpInput = document.getElementById("signup-confirm-input-otp");
    const submitBtn = document.getElementById("btn-submit-signup-confirm");
    const otp = otpInput ? otpInput.value.trim() : "";

    if (!otp || otp.length !== 6) {
      this.showAuthAlert("Please enter the complete 6-digit confirmation code.");
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = "Confirming Account..."; }

    try {
      const res = await fetch("/api/auth/confirm-signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: this.currentSignupEmail,
          otp_code: otp
        })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.switchAuthMode("LOGIN_CREDENTIALS");
        this.showAuthAlert("Email confirmed and account activated! Please sign in with your credentials.", "success");
        const identInput = document.getElementById("login-input-ident");
        if (identInput) identInput.value = this.currentSignupEmail;
      } else {
        this.showAuthAlert(data.error || data.message || "Invalid or expired confirmation code.");
      }
    } catch (e) {
      this.showAuthAlert("Network error confirming account: " + e.message);
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = "Confirm Email & Activate Account ✅"; }
    }
  }

  async resendSignupOtp() {
    if (!this.currentSignupEmail) return;
    this.showAuthAlert("Resending activation code...", "info");
    try {
      const res = await fetch("/api/auth/resend-signup-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: this.currentSignupEmail })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showAuthAlert("A new activation code has been sent to your email.", "info");
      } else {
        this.showAuthAlert(data.error || "Could not resend code.");
      }
    } catch (e) {
      this.showAuthAlert("Error resending code: " + e.message);
    }
  }

  async submitForgotPassword() {
    const identInput = document.getElementById("forgot-input-ident");
    const submitBtn = document.getElementById("btn-submit-forgot");
    const ident = identInput ? identInput.value.trim() : "";

    if (!ident) {
      this.showAuthAlert("Please provide your email address or username.");
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = "Sending Reset Code..."; }

    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: ident })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.currentResetSessionToken = data.reset_token;
        this.currentResetEmail = ident;

        const emailLabel = document.getElementById("reset-otp-email-label");
        if (emailLabel) emailLabel.innerText = data.email_masked || ident;

        this.switchAuthMode("RESET_PASSWORD");
        this.showAuthAlert("Password reset code dispatched! Please check your email for the 6-digit OTP.", "info");
      } else {
        this.showAuthAlert(data.error || data.message || "Failed to initiate password reset.");
      }
    } catch (e) {
      this.showAuthAlert("Network error: " + e.message);
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = "Send Password Reset Code ✉️"; }
    }
  }

  async submitResetPassword() {
    const otpInput = document.getElementById("reset-input-otp");
    const newPassInput = document.getElementById("reset-input-new-pass");
    const confirmPassInput = document.getElementById("reset-input-confirm-pass");
    const submitBtn = document.getElementById("btn-submit-reset");

    const otp = otpInput ? otpInput.value.trim() : "";
    const newPass = newPassInput ? newPassInput.value : "";
    const confirmPass = confirmPassInput ? confirmPassInput.value : "";

    if (!otp || otp.length !== 6) {
      this.showAuthAlert("Please enter the complete 6-digit verification code.");
      return;
    }

    if (!newPass || newPass.length < 6) {
      this.showAuthAlert("New password must be at least 6 characters long.");
      return;
    }

    if (newPass !== confirmPass) {
      this.showAuthAlert("Passwords do not match. Please re-enter.");
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = "Updating Password..."; }

    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reset_token: this.currentResetSessionToken,
          otp_code: otp,
          new_password: newPass
        })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.currentResetSessionToken = null;
        this.currentResetEmail = null;
        this.switchAuthMode("LOGIN_CREDENTIALS");
        this.showAuthAlert("Password updated successfully! Please sign in with your new password.", "success");
      } else {
        this.showAuthAlert(data.error || data.message || "Failed to reset password.");
      }
    } catch (e) {
      this.showAuthAlert("Network error: " + e.message);
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = "Update Password & Log In ✅"; }
    }
  }

  async resendResetOtp() {
    if (!this.currentResetSessionToken) return;
    this.showAuthAlert("Resending reset code...", "info");
    try {
      const res = await fetch("/api/auth/resend-reset-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset_token: this.currentResetSessionToken })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showAuthAlert("A new password reset code has been sent to your email.", "info");
      } else {
        this.showAuthAlert(data.error || "Could not resend code.");
      }
    } catch (e) {
      this.showAuthAlert("Error resending code: " + e.message);
    }
  }

  toggleEmailConfig() {
    const drawer = document.getElementById("auth-email-config-drawer");
    if (!drawer) return;
    const isHidden = drawer.style.display === "none";
    drawer.style.display = isHidden ? "block" : "none";
    if (isHidden) {
      this.checkEmailSettingsStatus();
    }
  }

  async checkEmailSettingsStatus() {
    const badge = document.getElementById("cfg-email-status-badge");
    try {
      const res = await fetch("/api/auth/email-settings-status");
      const data = await res.json();
      if (badge) {
        if (data.configured) {
          const provs = Object.keys(data.providers).filter(k => data.providers[k]).join(", ");
          badge.innerHTML = `<span style="color:#10b981;">✓ Connected (${provs.toUpperCase()})</span>`;
        } else {
          badge.innerHTML = `<span style="color:#f59e0b;">⚠ No live sender configured</span>`;
        }
      }
    } catch (e) {
      if (badge) badge.innerText = "Status: offline";
    }
  }

  async saveEmailConfig() {
    const resendInput = document.getElementById("cfg-input-resend-key");
    const brevoInput = document.getElementById("cfg-input-brevo-key");
    const badge = document.getElementById("cfg-email-status-badge");

    const resendKey = resendInput ? resendInput.value.trim() : "";
    const brevoKey = brevoInput ? brevoInput.value.trim() : "";

    if (!resendKey && !brevoKey) {
      this.showAuthAlert("Please enter a Resend API Key or Brevo API Key to save.");
      return;
    }

    if (badge) badge.innerText = "Saving...";

    try {
      const res = await fetch("/api/auth/save-email-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resend_api_key: resendKey,
          brevo_api_key: brevoKey
        })
      });

      let data = {};
      try {
        data = await res.json();
      } catch (err) {
        if (!res.ok) {
          throw new Error("Server returned error " + res.status + ". Please restart the bot terminal ('python run_bot.py') to load the updated routes.");
        }
      }

      if (res.ok && data.success) {
        if (badge) badge.innerHTML = `<span style="color:#10b981;">✓ Key saved & active!</span>`;
        this.showAuthAlert("Email settings saved successfully! OTPs will now be sent to your email.", "success");
        if (resendInput) resendInput.value = "";
        if (brevoInput) brevoInput.value = "";
      } else {
        if (badge) badge.innerHTML = `<span style="color:#ef4444;">Failed to save</span>`;
        this.showAuthAlert(data.error || data.message || "Failed to save email settings.");
      }
    } catch (e) {
      this.showAuthAlert("Connection error saving settings: " + e.message);
    }
  }

  async testEmailConfig() {
    const emailInput = document.getElementById("cfg-input-test-email");
    const testMsg = document.getElementById("cfg-test-email-msg");
    const btn = document.getElementById("btn-test-email");
    const email = emailInput ? emailInput.value.trim() : "";

    if (!email) {
      if (testMsg) {
        testMsg.style.display = "block";
        testMsg.style.color = "#ef4444";
        testMsg.innerText = "Please enter an email address to send a test message to.";
      }
      return;
    }

    if (btn) btn.disabled = true;
    if (testMsg) {
      testMsg.style.display = "block";
      testMsg.style.color = "#38bdf8";
      testMsg.innerText = "Sending test email...";
    }

    try {
      const res = await fetch("/api/auth/test-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email })
      });
      const data = await res.json();
      if (testMsg) {
        if (res.ok && data.success) {
          testMsg.style.color = "#10b981";
          testMsg.innerHTML = "✓ Test email sent successfully! Please check your inbox / spam folder.";
        } else {
          testMsg.style.color = "#ef4444";
          testMsg.innerHTML = "✗ " + (data.error || data.message || "Failed to send test email.");
        }
      }
    } catch (e) {
      if (testMsg) {
        testMsg.style.color = "#ef4444";
        testMsg.innerText = "Request failed: " + e.message;
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async logoutUser() {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        headers: this.getAuthHeaders()
      });
    } catch (e) {
      console.warn("Logout error:", e);
    }
    this.currentUser = null;
    this.authToken = null;
    this.terminalInitialized = false;
    localStorage.removeItem("quant_auth_token");

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    this.updateAuthUI();
    this.showAuthPortal();
    this.showAuthAlert("You have logged out. Please sign in to access your terminal.", "info");
  }
}

window.addEventListener("DOMContentLoaded", () => {
  window.app = new SmartBotApp();
});
