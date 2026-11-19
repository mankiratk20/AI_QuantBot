/**
 * Smart Trading Bot - Visual Strategy Builder Engine.
 * Allows users to add, edit, configure, and save custom trading strategies with nested AND/OR logic.
 */

class StrategyBuilderUI {
  constructor() {
    this.strategies = [];
    this.currentEditingStrategy = null;
    this.conditionsList = [];
    this.init();
  }

  async init() {
    await this.fetchStrategies();
    this.renderStrategyList();
    this.bindEvents();
  }

  async fetchStrategies() {
    try {
      const headers = window.app && window.app.getAuthHeaders ? window.app.getAuthHeaders() : {};
      const res = await fetch("/api/strategies", { headers });
      this.strategies = await res.json();
    } catch (e) {
      console.error("Failed to load strategies:", e);
    }
  }

  bindEvents() {
    const newBtn = document.getElementById("btn-new-strategy");
    if (newBtn) {
      newBtn.addEventListener("click", () => this.createNewStrategyForm());
    }

    const saveBtn = document.getElementById("btn-save-strategy");
    if (saveBtn) {
      saveBtn.addEventListener("click", () => this.saveCurrentStrategy());
    }

    const addCondBtn = document.getElementById("btn-add-condition");
    if (addCondBtn) {
      addCondBtn.addEventListener("click", () => this.addConditionRow());
    }
  }

  renderStrategyList() {
    const container = document.getElementById("strategy-list-container");
    if (!container) return;

    container.innerHTML = "";
    if (!Array.isArray(this.strategies) || this.strategies.length === 0) {
      container.innerHTML = `<div style="text-align:center; color:#94a3b8; padding:30px;">No strategies available. Create one to get started.</div>`;
      return;
    }

    this.strategies.forEach((strat) => {
      const isSystem = !strat.user_id || strat.user_id === "SYSTEM";
      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "14px";
      card.style.borderLeft = isSystem ? "4px solid #475569" : "4px solid #10b981";

      const badgeHtml = isSystem
        ? `<span class="badge" style="background:#1e293b; color:#94a3b8; margin-left:8px;" title="Institutional Benchmark Strategy">🏛️ Institutional Preset</span>`
        : `<span class="badge" style="background:#064e3b; color:#34d399; margin-left:8px;" title="Encrypted & Private to your account">🔒 Personal & Private</span>`;

      const deleteBtnHtml = (!isSystem)
        ? `<button class="btn btn-sm btn-danger" style="margin-left:6px;" onclick="window.stratBuilder.deleteStrategy('${strat.id}')" title="Delete private strategy">Delete</button>`
        : '';

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
          <div>
            <span style="font-weight:700; font-size:1.05rem; color:#f8fafc;">${strat.name}</span>
            <span class="badge" style="background:#1e293b; color:#38bdf8; margin-left:8px;">${strat.strategy_type}</span>
            ${badgeHtml}
          </div>
          <div>
            <button class="btn btn-sm ${strat.is_active ? 'btn-success' : 'btn-secondary'}" onclick="window.stratBuilder.toggleActive('${strat.id}', ${!strat.is_active})">
              ${strat.is_active ? 'Active' : 'Disabled'}
            </button>
            <button class="btn btn-sm btn-primary" style="margin-left:6px;" onclick="window.stratBuilder.editStrategy('${strat.id}')">
              Edit
            </button>
            ${deleteBtnHtml}
          </div>
        </div>
        <p style="font-size:0.83rem; color:#94a3b8; margin-bottom:12px;">${strat.description || "User defined algorithmic rule-set."}</p>
        <div style="display:flex; gap:16px; font-size:0.78rem; color:#cbd5e1; flex-wrap:wrap;">
          <div><strong>Pairs:</strong> ${strat.instruments.join(", ")}</div>
          <div><strong>Timeframes:</strong> ${strat.timeframes.join(", ")}</div>
          <div><strong>Sessions:</strong> ${strat.sessions.join(", ")}</div>
          <div><strong>Min R:R:</strong> ${strat.risk_settings.min_risk_reward || 2.0}:1</div>
          <div><strong>Risk/Trade:</strong> ${strat.risk_settings.risk_percent || 1.0}%</div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  createNewStrategyForm() {
    this.currentEditingStrategy = {
      id: "strat_" + Math.random().toString(36).substr(2, 8),
      name: "My Custom Strategy",
      description: "Custom user-defined rules",
      strategy_type: "Smart Money Concepts (SMC)",
      instruments: ["EURUSD", "GBPUSD", "XAUUSD"],
      timeframes: ["15M"],
      sessions: ["London", "New York"],
      rules: {
        operator: "AND",
        conditions: [
          { category: "market_structure", field: "trend", operator: "==", value: "BULLISH" },
          { category: "smc", field: "bullish_choch_present", operator: "==", value: true }
        ]
      },
      risk_settings: {
        risk_percent: 1.0,
        min_risk_reward: 2.0,
        max_spread_pips: 2.5,
        max_trades_per_day: 4,
        trailing_sl_enabled: true
      },
      is_active: 1
    };
    this.populateEditor(this.currentEditingStrategy);
  }

  editStrategy(stratId) {
    const s = this.strategies.find((x) => x.id === stratId);
    if (!s) return;
    this.currentEditingStrategy = JSON.parse(JSON.stringify(s));
    this.populateEditor(this.currentEditingStrategy);
  }

  populateEditor(strat) {
    document.getElementById("editor-panel").style.display = "block";
    document.getElementById("strat-name").value = strat.name;
    document.getElementById("strat-type").value = strat.strategy_type;
    document.getElementById("strat-desc").value = strat.description || "";
    document.getElementById("strat-pairs").value = strat.instruments.join(", ");
    document.getElementById("strat-tf").value = strat.timeframes[0] || "15M";
    document.getElementById("strat-rr").value = strat.risk_settings.min_risk_reward || 2.0;
    document.getElementById("strat-risk-pct").value = strat.risk_settings.risk_percent || 1.0;
    document.getElementById("strat-max-spread").value = strat.risk_settings.max_spread_pips || 2.5;

    this.conditionsList = strat.rules.conditions || [];
    this.renderConditionRows();
  }

  renderConditionRows() {
    const container = document.getElementById("conditions-container");
    if (!container) return;
    container.innerHTML = "";

    this.conditionsList.forEach((cond, index) => {
      const row = document.createElement("div");
      row.style.display = "flex";
      row.style.gap = "10px";
      row.style.marginBottom = "8px";
      row.style.alignItems = "center";

      row.innerHTML = `
        <select class="select-control" style="flex:1;" onchange="window.stratBuilder.updateCondition(${index}, 'field', this.value)">
          <option value="trend" ${cond.field === 'trend' ? 'selected' : ''}>Market Trend (BULLISH/BEARISH)</option>
          <option value="bullish_choch_present" ${cond.field === 'bullish_choch_present' ? 'selected' : ''}>Bullish CHOCH Present</option>
          <option value="bearish_choch_present" ${cond.field === 'bearish_choch_present' ? 'selected' : ''}>Bearish CHOCH Present</option>
          <option value="active_bullish_fvg" ${cond.field === 'active_bullish_fvg' ? 'selected' : ''}>Active Bullish FVG Imbalance</option>
          <option value="active_bearish_fvg" ${cond.field === 'active_bearish_fvg' ? 'selected' : ''}>Active Bearish FVG Imbalance</option>
          <option value="bullish_ob_mitigated" ${cond.field === 'bullish_ob_mitigated' ? 'selected' : ''}>Bullish Order Block Mitigated</option>
          <option value="rsi" ${cond.field === 'rsi' ? 'selected' : ''}>RSI Indicator Value</option>
          <option value="ema_20_above_50" ${cond.field === 'ema_20_above_50' ? 'selected' : ''}>EMA 20 > EMA 50</option>
        </select>
        <select class="select-control" style="width:110px;" onchange="window.stratBuilder.updateCondition(${index}, 'operator', this.value)">
          <option value="==" ${cond.operator === '==' ? 'selected' : ''}>EQUALS (==)</option>
          <option value="!=" ${cond.operator === '!=' ? 'selected' : ''}>NOT EQUAL (!=)</option>
          <option value="<=" ${cond.operator === '<=' ? 'selected' : ''}>LESS/EQUAL (<=)</option>
          <option value=">=" ${cond.operator === '>=' ? 'selected' : ''}>GREATER/EQUAL (>=)</option>
        </select>
        <input class="input-control" style="width:140px;" type="text" value="${cond.value}" 
               onchange="window.stratBuilder.updateCondition(${index}, 'value', this.value)" />
        <button class="btn btn-sm btn-danger" onclick="window.stratBuilder.removeCondition(${index})">X</button>
      `;
      container.appendChild(row);
    });
  }

  addConditionRow() {
    this.conditionsList.push({
      category: "indicator",
      field: "rsi",
      operator: "<=",
      value: 65
    });
    this.renderConditionRows();
  }

  updateCondition(index, key, val) {
    if (this.conditionsList[index]) {
      if (val === "true") val = true;
      if (val === "false") val = false;
      if (!isNaN(val) && val !== "") val = parseFloat(val);
      this.conditionsList[index][key] = val;
    }
  }

  removeCondition(index) {
    this.conditionsList.splice(index, 1);
    this.renderConditionRows();
  }

  async saveCurrentStrategy() {
    if (!this.currentEditingStrategy) {
      this.currentEditingStrategy = {
        id: "strat_" + Math.random().toString(36).substr(2, 8),
        is_active: 1
      };
    }

    const nameInput = document.getElementById("strat-name");
    const typeSelect = document.getElementById("strat-type");
    const descInput = document.getElementById("strat-desc");
    const pairsInput = document.getElementById("strat-pairs");
    const tfSelect = document.getElementById("strat-tf");
    const rrInput = document.getElementById("strat-rr");
    const riskInput = document.getElementById("strat-risk-pct");
    const spreadInput = document.getElementById("strat-max-spread");

    this.currentEditingStrategy.name = nameInput ? nameInput.value.trim() : "Custom Strategy";
    this.currentEditingStrategy.strategy_type = typeSelect ? typeSelect.value : "Price Action";
    this.currentEditingStrategy.description = descInput ? descInput.value.trim() : "";
    this.currentEditingStrategy.instruments = pairsInput && pairsInput.value.trim() 
      ? pairsInput.value.split(",").map(s => s.trim().toUpperCase()).filter(Boolean)
      : ["EURUSD"];
    this.currentEditingStrategy.timeframes = [tfSelect ? tfSelect.value : "15M"];
    this.currentEditingStrategy.risk_settings = {
      min_risk_reward: parseFloat(rrInput ? rrInput.value : 2.0) || 2.0,
      risk_percent: parseFloat(riskInput ? riskInput.value : 1.0) || 1.0,
      max_spread_pips: parseFloat(spreadInput ? spreadInput.value : 2.5) || 2.5,
      max_trades_per_day: 4,
      trailing_sl_enabled: true
    };
    this.currentEditingStrategy.rules = {
      operator: "AND",
      conditions: this.conditionsList || []
    };

    try {
      const headers = window.app && window.app.getAuthHeaders 
        ? window.app.getAuthHeaders({ "Content-Type": "application/json" }) 
        : { "Content-Type": "application/json" };

      const res = await fetch("/api/strategies", {
        method: "POST",
        headers,
        body: JSON.stringify(this.currentEditingStrategy)
      });
      const data = await res.json();
      if (data.success) {
        if (window.app && window.app.showToast) {
          window.app.showToast(`Strategy '${this.currentEditingStrategy.name}' saved privately!`, "success");
        } else {
          alert("Strategy saved successfully!");
        }
        document.getElementById("editor-panel").style.display = "none";
        await this.fetchStrategies();
        this.renderStrategyList();
        if (window.app && window.app.populateBacktestStrategies) {
          window.app.populateBacktestStrategies();
        }
      } else {
        alert("Failed to save strategy: " + (data.error || "Unknown server error"));
      }
    } catch (e) {
      alert("Error saving strategy: " + e.message);
    }
  }

  async toggleActive(stratId, is_active) {
    try {
      const headers = window.app && window.app.getAuthHeaders 
        ? window.app.getAuthHeaders({ "Content-Type": "application/json" }) 
        : { "Content-Type": "application/json" };

      const res = await fetch(`/api/strategies/${stratId}/toggle`, {
        method: "POST",
        headers,
        body: JSON.stringify({ is_active })
      });
      const data = await res.json();
      if (data.error) {
        alert(data.error);
      }
      await this.fetchStrategies();
      this.renderStrategyList();
    } catch (e) {
      console.error(e);
    }
  }

  async deleteStrategy(stratId) {
    if (!confirm("Are you sure you want to permanently delete this private strategy?")) return;
    try {
      const headers = window.app && window.app.getAuthHeaders 
        ? window.app.getAuthHeaders() 
        : {};

      const res = await fetch(`/api/strategies/${stratId}`, {
        method: "DELETE",
        headers
      });
      const data = await res.json();
      if (data.success) {
        if (window.app && window.app.showToast) {
          window.app.showToast("Private strategy deleted.", "info");
        }
        await this.fetchStrategies();
        this.renderStrategyList();
        if (window.app && window.app.populateBacktestStrategies) {
          window.app.populateBacktestStrategies();
        }
      } else {
        alert("Failed to delete strategy: " + (data.error || "Permission denied"));
      }
    } catch (e) {
      alert("Error deleting strategy: " + e.message);
    }
  }
}
