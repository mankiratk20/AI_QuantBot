/**
 * Smart Trading Bot - High-Performance Institutional Chart Engine.
 * Features:
 * - Standalone High-DPI HTML5 Canvas Candlestick & Technical Analysis Renderer (zero CDN dependency)
 * - Automatic dynamic resizing via ResizeObserver and explicit resize()
 * - Multi-timeframe bar display (1M, 5M, 15M, 30M, 1H, 4H, 1D)
 * - Technical Indicators: EMA 20 (Cyan), EMA 50 (Orange)
 * - Smart Money Concepts (SMC) overlays: BOS, CHOCH, FVG zones, Order Blocks, Liquidity levels
 * - Active Positions visualizer: Entry (Blue), Stop Loss (Red), Take Profit (Green)
 * - Interactive Crosshairs with Price & Time callouts and Candle Inspector tooltip
 * - Zoom & Pan support
 */

class TradingChart {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.canvas = null;
    this.ctx = null;
    this.bars = [];
    this.analysis = null;
    this.positions = [];
    this.activeSymbol = "EURUSD";
    this.activeTimeframe = "15M";

    // Viewport & Scale
    this.visibleBarsCount = 60;
    this.offsetRight = 5; // offset from latest bar
    this.zoomLevel = 1.0;

    // Crosshair state
    this.mouseX = -1;
    this.mouseY = -1;
    this.isHovering = false;

    this.init();
  }

  init() {
    if (!this.container) return;
    this.container.innerHTML = "";
    this.container.style.position = "relative";
    this.container.style.overflow = "hidden";
    this.container.style.width = "100%";
    this.container.style.height = "100%";
    this.container.style.minHeight = "460px";

    // Create Canvas
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");

    // Tooltip overlay element
    this.tooltip = document.createElement("div");
    this.tooltip.style.position = "absolute";
    this.tooltip.style.top = "10px";
    this.tooltip.style.left = "12px";
    this.tooltip.style.padding = "6px 10px";
    this.tooltip.style.background = "rgba(18, 24, 36, 0.85)";
    this.tooltip.style.border = "1px solid #26354d";
    this.tooltip.style.borderRadius = "6px";
    this.tooltip.style.fontSize = "11px";
    this.tooltip.style.color = "#f1f5f9";
    this.tooltip.style.pointerEvents = "none";
    this.tooltip.style.zIndex = "10";
    this.container.appendChild(this.tooltip);

    this.resize();

    // Event Listeners
    window.addEventListener("resize", () => this.resize());
    if (window.ResizeObserver) {
      new ResizeObserver(() => {
        if (this.container && this.container.clientWidth > 0 && this.container.clientHeight > 0) {
          this.resize();
        }
      }).observe(this.container);
    }

    this.bindMouseEvents();
  }

  resize() {
    if (!this.container || !this.canvas) return;
    const rect = this.container.getBoundingClientRect();
    const width = Math.max(rect.width || this.container.clientWidth || 800, 300);
    const height = Math.max(rect.height || this.container.clientHeight || 460, 300);

    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.floor(width * dpr);
    this.canvas.height = Math.floor(height * dpr);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;

    if (this.ctx) {
      if (this.ctx.setTransform) {
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      }
      this.ctx.scale(dpr, dpr);
    }
    this.width = width;
    this.height = height;

    this.draw();
  }

  fitContent() {
    this.visibleBarsCount = 60;
    this.offsetRight = 0;
    this.zoomLevel = 1.0;
    this.resize();
  }

  bindMouseEvents() {
    let isDragging = false;
    let dragStartX = 0;
    let dragStartOffset = 0;

    this.canvas.style.cursor = "crosshair";

    this.canvas.addEventListener("mousedown", (e) => {
      if (e.button === 0) {
        isDragging = true;
        dragStartX = e.clientX;
        dragStartOffset = this.offsetRight;
        this.canvas.style.cursor = "grabbing";
      }
    });

    window.addEventListener("mouseup", () => {
      if (isDragging) {
        isDragging = false;
        if (this.canvas) this.canvas.style.cursor = "crosshair";
      }
    });

    this.canvas.addEventListener("mousemove", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.mouseX = e.clientX - rect.left;
      this.mouseY = e.clientY - rect.top;
      this.isHovering = true;

      if (isDragging && this.bars && this.bars.length > 0) {
        const deltaX = e.clientX - dragStartX;
        const barSpacing = (this.width - 65) / Math.max(this.visibleBarsCount, 1);
        const barsShift = Math.round(deltaX / Math.max(barSpacing, 2));
        const maxOffset = Math.max(0, this.bars.length - this.visibleBarsCount);
        this.offsetRight = Math.max(0, Math.min(maxOffset, dragStartOffset + barsShift));
      }
      this.draw();
    });

    this.canvas.addEventListener("mouseleave", () => {
      if (!isDragging) {
        this.isHovering = false;
        this.mouseX = -1;
        this.mouseY = -1;
        this.draw();
      }
    });

    // Zoom on wheel
    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (e.deltaY < 0) {
        this.visibleBarsCount = Math.max(20, this.visibleBarsCount - 4);
      } else {
        const maxBars = Math.min(180, this.bars && this.bars.length ? this.bars.length : 120);
        this.visibleBarsCount = Math.min(maxBars, this.visibleBarsCount + 4);
      }
      this.draw();
    }, { passive: false });
  }

  loadData(bars) {
    this.bars = bars || [];
    this.draw();
  }

  applySMCAnnotations(analysis) {
    this.analysis = analysis;
    this.draw();
  }

  applyActivePositionLines(positions) {
    this.positions = positions || [];
    this.draw();
  }

  draw() {
    if (!this.ctx || !this.width || !this.height) return;
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    // 1. Background
    ctx.fillStyle = "#0b0e14";
    ctx.fillRect(0, 0, w, h);

    if (!this.bars || this.bars.length === 0) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Loading live market data...", w / 2, h / 2);
      return;
    }

    const priceScaleWidth = 65;
    const timeScaleHeight = 24;
    const chartW = w - priceScaleWidth;
    const chartH = h - timeScaleHeight;

    // Slice visible window with offset support
    const totalBars = this.bars.length;
    const count = Math.min(this.visibleBarsCount, totalBars);
    const endIdx = Math.max(count, totalBars - (this.offsetRight || 0));
    const startIdx = Math.max(0, endIdx - count);
    const visibleBars = this.bars.slice(startIdx, endIdx);

    // Compute Min and Max Prices
    let minP = Infinity;
    let maxP = -Infinity;
    for (const b of visibleBars) {
      if (b.low < minP) minP = b.low;
      if (b.high > maxP) maxP = b.high;
    }

    if (minP === Infinity || maxP === -Infinity) {
      minP = 1.0;
      maxP = 1.1;
    }

    // Add 8% padding to price scale
    const pRange = maxP - minP || 0.0001;
    const pPadding = pRange * 0.08;
    minP -= pPadding;
    maxP += pPadding;
    const priceRange = maxP - minP;

    const priceToY = (price) => chartH - ((price - minP) / priceRange) * chartH;
    const yToPrice = (y) => maxP - (y / chartH) * priceRange;

    const sym = this.activeSymbol || "";
    const isCryptoOrIndex = sym.includes("BTC") || sym.includes("US30") || sym.includes("NAS100");
    const isJPYorGold = sym.includes("JPY") || sym.includes("XAU");
    const digits = isCryptoOrIndex ? 1 : (isJPYorGold ? 2 : 5);

    // 2. Draw Horizontal Price Gridlines
    ctx.strokeStyle = "#161f30";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#64748b";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "left";

    const gridSteps = 6;
    for (let i = 0; i <= gridSteps; i++) {
      const p = minP + (priceRange / gridSteps) * i;
      const y = priceToY(p);

      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartW, y);
      ctx.stroke();

      // Price Label on Right Axis
      ctx.fillText(p.toFixed(digits), chartW + 8, y + 3);
    }

    // Vertical Time Gridlines
    const barSpacing = chartW / count;
    const timeStep = Math.max(1, Math.floor(count / 6));
    ctx.textAlign = "center";

    for (let i = 0; i < count; i += timeStep) {
      const x = i * barSpacing + barSpacing / 2;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, chartH);
      ctx.stroke();

      const timeStr = (visibleBars[i].timestamp || "").split(" ")[1] || "";
      ctx.fillText(timeStr.slice(0, 5), x, h - 8);
    }

    // 3. Draw SMC Overlays (FVG & Order Blocks Shaded Zones)
    if (this.analysis) {
      // Fair Value Gaps (FVG)
      if (this.analysis.fvgs) {
        this.analysis.fvgs.forEach((fvg) => {
          const topY = priceToY(fvg.top);
          const bottomY = priceToY(fvg.bottom);
          const isBull = fvg.type === "BULLISH_FVG";

          ctx.fillStyle = isBull ? "rgba(6, 182, 212, 0.12)" : "rgba(239, 68, 68, 0.12)";
          ctx.fillRect(0, topY, chartW, bottomY - topY);

          ctx.strokeStyle = isBull ? "rgba(6, 182, 212, 0.4)" : "rgba(239, 68, 68, 0.4)";
          ctx.setLineDash([3, 3]);
          ctx.strokeRect(0, topY, chartW, bottomY - topY);
          ctx.setLineDash([]);

          ctx.fillStyle = isBull ? "#06b6d4" : "#ef4444";
          ctx.font = "9px sans-serif";
          ctx.textAlign = "right";
          ctx.fillText(`${isBull ? 'Bullish' : 'Bearish'} FVG`, chartW - 8, (topY + bottomY) / 2 + 3);
        });
      }

      // Order Blocks (OB)
      if (this.analysis.order_blocks) {
        this.analysis.order_blocks.slice(-2).forEach((ob) => {
          const topY = priceToY(ob.top);
          const bottomY = priceToY(ob.bottom);
          const isBull = ob.type === "BULLISH_OB";

          ctx.fillStyle = isBull ? "rgba(168, 85, 247, 0.15)" : "rgba(239, 68, 68, 0.15)";
          ctx.fillRect(0, topY, chartW, bottomY - topY);

          ctx.strokeStyle = isBull ? "#a855f7" : "#ef4444";
          ctx.lineWidth = 1;
          ctx.strokeRect(0, topY, chartW, bottomY - topY);

          ctx.fillStyle = isBull ? "#c084fc" : "#f87171";
          ctx.font = "10px sans-serif";
          ctx.textAlign = "left";
          ctx.fillText(`Institutional ${isBull ? 'Bull' : 'Bear'} OB`, 8, topY + 12);
        });
      }

      // BOS / CHOCH Lines
      if (this.analysis.boss) {
        this.analysis.boss.slice(-3).forEach((bos) => {
          const y = priceToY(bos.price);
          ctx.strokeStyle = bos.type === "BULLISH_BOS" ? "#10b981" : "#ef4444";
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(chartW, y);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = bos.type === "BULLISH_BOS" ? "#10b981" : "#ef4444";
          ctx.font = "bold 9px sans-serif";
          ctx.textAlign = "right";
          ctx.fillText(`BOS ${bos.type === 'BULLISH_BOS' ? '▲' : '▼'}`, chartW - 10, y - 4);
        });
      }

      if (this.analysis.chochs) {
        this.analysis.chochs.slice(-2).forEach((ch) => {
          const y = priceToY(ch.price);
          ctx.strokeStyle = "#f59e0b";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(chartW, y);
          ctx.stroke();

          ctx.fillStyle = "#f59e0b";
          ctx.font = "bold 10px sans-serif";
          ctx.textAlign = "right";
          ctx.fillText("CHOCH (Character Shift)", chartW - 10, y - 5);
        });
      }
    }

    // 4. Draw Candlesticks
    const barWidth = Math.max(3, barSpacing * 0.7);
    let hoveredBar = null;

    for (let i = 0; i < count; i++) {
      const b = visibleBars[i];
      const x = i * barSpacing + barSpacing / 2;
      const openY = priceToY(b.open);
      const closeY = priceToY(b.close);
      const highY = priceToY(b.high);
      const lowY = priceToY(b.low);

      const isBull = b.close >= b.open;
      const color = isBull ? "#10b981" : "#ef4444";

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      ctx.fillStyle = color;
      const bodyY = Math.min(openY, closeY);
      const bodyH = Math.max(2, Math.abs(closeY - openY));
      ctx.fillRect(x - barWidth / 2, bodyY, barWidth, bodyH);

      // Check if mouse is hovering this bar
      if (this.isHovering && Math.abs(this.mouseX - x) <= barSpacing / 2) {
        hoveredBar = b;
      }
    }

    // 5. Draw EMA 20 & EMA 50 Curves
    this.drawEMA(visibleBars, 20, "#38bdf8", priceToY, barSpacing);
    this.drawEMA(visibleBars, 50, "#f59e0b", priceToY, barSpacing);

    // 6. Draw Active Positions Lines (Entry, SL, TP)
    if (this.positions && this.positions.length > 0) {
      this.positions.forEach((pos) => {
        if (pos.symbol === this.activeSymbol) {
          // Entry Line (Blue)
          this.drawTradeLine(ctx, priceToY(pos.entry_price), "#3b82f6", `Entry #${pos.ticket} (${pos.direction})`, chartW);
          // Stop Loss Line (Red)
          if (pos.stop_loss > 0) {
            this.drawTradeLine(ctx, priceToY(pos.stop_loss), "#ef4444", `SL #${pos.ticket}`, chartW);
          }
          // Take Profit Line (Green)
          if (pos.take_profit > 0) {
            this.drawTradeLine(ctx, priceToY(pos.take_profit), "#10b981", `TP #${pos.ticket}`, chartW);
          }
        }
      });
    }

    // 7. Draw Current Live Price Line
    const lastBar = visibleBars[visibleBars.length - 1];
    const liveY = priceToY(lastBar.close);
    ctx.strokeStyle = lastBar.close >= lastBar.open ? "#10b981" : "#ef4444";
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(0, liveY);
    ctx.lineTo(chartW, liveY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Live Price Pill on Axis
    ctx.fillStyle = lastBar.close >= lastBar.open ? "#10b981" : "#ef4444";
    ctx.fillRect(chartW, liveY - 10, priceScaleWidth, 20);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(lastBar.close.toFixed(digits), chartW + 6, liveY + 4);

    // 8. Crosshair Cursor Overlay
    if (this.isHovering && this.mouseX >= 0 && this.mouseX <= chartW && this.mouseY >= 0 && this.mouseY <= chartH) {
      ctx.strokeStyle = "#475569";
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(this.mouseX, 0);
      ctx.lineTo(this.mouseX, chartH);
      ctx.stroke();

      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(0, this.mouseY);
      ctx.lineTo(chartW, this.mouseY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Crosshair Price Tag
      const hoverPrice = yToPrice(this.mouseY);
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(chartW, this.mouseY - 9, priceScaleWidth, 18);
      ctx.strokeStyle = "#38bdf8";
      ctx.strokeRect(chartW, this.mouseY - 9, priceScaleWidth, 18);

      ctx.fillStyle = "#38bdf8";
      ctx.font = "bold 10px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(hoverPrice.toFixed(digits), chartW + 6, this.mouseY + 4);
    }

    // 9. Tooltip Bar Inspector
    const displayBar = hoveredBar || lastBar;
    if (this.tooltip && displayBar) {
      const isUp = displayBar.close >= displayBar.open;
      this.tooltip.innerHTML = `
        <strong>${this.activeSymbol}</strong> (${this.activeTimeframe}) &nbsp;|&nbsp;
        Time: <span style="color:#94a3b8;">${displayBar.timestamp}</span> &nbsp;|&nbsp;
        O: <strong>${displayBar.open}</strong> &nbsp;
        H: <strong>${displayBar.high}</strong> &nbsp;
        L: <strong>${displayBar.low}</strong> &nbsp;
        C: <strong style="color:${isUp ? '#10b981' : '#ef4444'}">${displayBar.close}</strong> &nbsp;
        Vol: <span style="color:#94a3b8;">${displayBar.volume}</span>
      `;
    }
  }

  drawEMA(bars, period, color, priceToY, barSpacing) {
    if (bars.length < period) return;
    const ctx = this.ctx;
    const k = 2 / (period + 1);
    let ema = bars[0].close;

    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();

    let started = false;
    for (let i = 0; i < bars.length; i++) {
      const close = bars[i].close;
      ema = i === 0 ? close : close * k + ema * (1 - k);

      if (i >= period - 1) {
        const x = i * barSpacing + barSpacing / 2;
        const y = priceToY(ema);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
    }
    ctx.stroke();
  }

  drawTradeLine(ctx, y, color, title, chartW) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 2]);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(chartW, y);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = color;
    ctx.font = "bold 9px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(title, 10, y - 4);
  }
}
