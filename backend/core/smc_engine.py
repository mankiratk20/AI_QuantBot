"""
Smart Money Concepts (SMC), ICT Concepts, and Market Structure Analysis Engine.
Detects:
- Trend & Structure (Higher Highs, Higher Lows, Lower Highs, Lower Lows)
- Break of Structure (BOS)
- Change of Character (CHOCH)
- Fair Value Gaps (FVG)
- Order Blocks (OB)
- Liquidity Zones (Buy-side & Sell-side)
- Supply & Demand Zones
- Candlestick Patterns
"""

from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from backend.core.indicators import identify_swing_points, calculate_atr

def detect_market_structure(df: pd.DataFrame, swings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates Swing points to label HH, HL, LH, LL and determine
    market structure bias (BULLISH, BEARISH, RANGING).
    """
    if len(swings) < 4:
        return {
            "trend": "NEUTRAL",
            "bias": "RANGING",
            "labeled_swings": [],
            "boss": [],
            "chochs": []
        }

    highs = [s for s in swings if s["type"] == "SWING_HIGH"]
    lows = [s for s in swings if s["type"] == "SWING_LOW"]

    labeled_swings = []
    # Label Highs
    for i in range(len(highs)):
        h = highs[i]
        label = "HIGH"
        if i > 0:
            if h["price"] > highs[i - 1]["price"]:
                label = "HH"  # Higher High
            else:
                label = "LH"  # Lower High
        labeled_swings.append({**h, "label": label})

    # Label Lows
    for i in range(len(lows)):
        l = lows[i]
        label = "LOW"
        if i > 0:
            if l["price"] > lows[i - 1]["price"]:
                label = "HL"  # Higher Low
            else:
                label = "LL"  # Lower Low
        labeled_swings.append({**l, "label": label})

    labeled_swings.sort(key=lambda x: x["index"])

    # Determine Trend Bias from recent swing points
    recent_swings = labeled_swings[-6:] if len(labeled_swings) >= 6 else labeled_swings
    hh_count = sum(1 for s in recent_swings if s.get("label") == "HH")
    hl_count = sum(1 for s in recent_swings if s.get("label") == "HL")
    lh_count = sum(1 for s in recent_swings if s.get("label") == "LH")
    ll_count = sum(1 for s in recent_swings if s.get("label") == "LL")

    if (hh_count + hl_count) > (lh_count + ll_count) and len(highs) >= 2 and highs[-1]["price"] >= highs[-2]["price"]:
        trend = "BULLISH"
    elif (lh_count + ll_count) > (hh_count + hl_count) and len(lows) >= 2 and lows[-1]["price"] <= lows[-2]["price"]:
        trend = "BEARISH"
    else:
        trend = "RANGING"

    # Detect Break of Structure (BOS)
    boss = []
    chochs = []
    
    if len(highs) >= 2:
        for i in range(1, len(highs)):
            if highs[i]["price"] > highs[i - 1]["price"]:
                boss.append({
                    "type": "BULLISH_BOS",
                    "price": highs[i - 1]["price"],
                    "broken_at_index": highs[i]["index"],
                    "timestamp": highs[i]["timestamp"]
                })

    if len(lows) >= 2:
        for i in range(1, len(lows)):
            if lows[i]["price"] < lows[i - 1]["price"]:
                boss.append({
                    "type": "BEARISH_BOS",
                    "price": lows[i - 1]["price"],
                    "broken_at_index": lows[i]["index"],
                    "timestamp": lows[i]["timestamp"]
                })

    # Recent CHOCH Detection: Break of prior structural lower high or higher low
    if len(lows) >= 2 and len(highs) >= 2:
        recent_window = df.iloc[-25:] if len(df) >= 25 else df

        # Prior Lower High (break of which triggers Bullish CHOCH)
        prior_lh = None
        for i in range(len(highs) - 1, 0, -1):
            if highs[i]["price"] < highs[i - 1]["price"]:
                prior_lh = highs[i]["price"]
                break

        # Prior Higher Low (break of which triggers Bearish CHOCH)
        prior_hl = None
        for i in range(len(lows) - 1, 0, -1):
            if lows[i]["price"] > lows[i - 1]["price"]:
                prior_hl = lows[i]["price"]
                break

        if prior_lh is not None:
            break_bars = recent_window[recent_window["close"] > prior_lh]
            if not break_bars.empty:
                b_bar = break_bars.iloc[0]
                chochs.append({
                    "type": "BULLISH_CHOCH",
                    "price": float(prior_lh),
                    "timestamp": str(b_bar["timestamp"]),
                    "description": f"Price broke above previous Lower High at {prior_lh:.5f}, confirming bullish character shift."
                })
                trend = "BULLISH"

        if prior_hl is not None:
            break_bars = recent_window[recent_window["close"] < prior_hl]
            if not break_bars.empty:
                b_bar = break_bars.iloc[0]
                chochs.append({
                    "type": "BEARISH_CHOCH",
                    "price": float(prior_hl),
                    "timestamp": str(b_bar["timestamp"]),
                    "description": f"Price broke below previous Higher Low at {prior_hl:.5f}, confirming bearish character shift."
                })
                trend = "BEARISH"

    return {
        "trend": trend,
        "bias": trend,
        "labeled_swings": labeled_swings,
        "boss": boss[-5:],
        "chochs": chochs[-3:]
    }

def detect_fair_value_gaps(df: pd.DataFrame, min_gap_percent: float = 0.02) -> List[Dict[str, Any]]:
    """
    Identifies 3-candle Fair Value Gaps (FVG) / Imbalances.
    - Bullish FVG: Candle 1 High < Candle 3 Low (Gap in Candle 2)
    - Bearish FVG: Candle 1 Low > Candle 3 High (Gap in Candle 2)
    """
    fvgs = []
    n = len(df)
    if n < 3:
        return fvgs

    for i in range(2, n):
        c1 = df.iloc[i - 2]
        c2 = df.iloc[i - 1]
        c3 = df.iloc[i]

        # Bullish FVG
        if c3['low'] > c1['high']:
            gap_size = c3['low'] - c1['high']
            price_mid = (c3['low'] + c1['high']) / 2.0
            if (gap_size / price_mid) * 100.0 >= min_gap_percent:
                # Check if mitigated by current price
                current_low = df['low'].iloc[i:].min()
                is_mitigated = current_low <= c1['high']

                fvgs.append({
                    "type": "BULLISH_FVG",
                    "top": float(c3['low']),
                    "bottom": float(c1['high']),
                    "midpoint": float(price_mid),
                    "size": float(gap_size),
                    "candle_index": i - 1,
                    "timestamp": str(c2['timestamp']),
                    "is_mitigated": bool(is_mitigated)
                })

        # Bearish FVG
        elif c1['low'] > c3['high']:
            gap_size = c1['low'] - c3['high']
            price_mid = (c1['low'] + c3['high']) / 2.0
            if (gap_size / price_mid) * 100.0 >= min_gap_percent:
                current_high = df['high'].iloc[i:].max()
                is_mitigated = current_high >= c1['low']

                fvgs.append({
                    "type": "BEARISH_FVG",
                    "top": float(c1['low']),
                    "bottom": float(c3['high']),
                    "midpoint": float(price_mid),
                    "size": float(gap_size),
                    "candle_index": i - 1,
                    "timestamp": str(c2['timestamp']),
                    "is_mitigated": bool(is_mitigated)
                })

    return fvgs[-10:]

def detect_order_blocks(df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identifies institutional Order Blocks (OB):
    - Bullish OB: The last down candle (bearish) prior to an aggressive upward displacement.
    - Bearish OB: The last up candle (bullish) prior to an aggressive downward displacement.
    """
    order_blocks = []
    atr = calculate_atr(df, 14)

    for i in range(1, len(df) - 3):
        curr_atr = atr.iloc[i] if not np.isnan(atr.iloc[i]) else (df['high'].iloc[i] - df['low'].iloc[i])
        
        # Check for Bullish Order Block (last bearish candle before impulse move)
        c0 = df.iloc[i]
        c1 = df.iloc[i + 1]
        c2 = df.iloc[i + 2]
        c3 = df.iloc[i + 3]

        displacement_up = (c3['close'] - c0['close'])
        if c0['close'] < c0['open'] and displacement_up > (curr_atr * 1.5):
            # Check if price has mitigated (re-entered) this OB
            subsequent_low = df['low'].iloc[i + 1:].min()
            mitigated = subsequent_low <= c0['low']

            order_blocks.append({
                "type": "BULLISH_OB",
                "top": float(c0['high']),
                "bottom": float(c0['low']),
                "entry_level": float(c0['open']),
                "index": i,
                "timestamp": str(c0['timestamp']),
                "is_mitigated": bool(mitigated)
            })

        # Check for Bearish Order Block (last bullish candle before downward impulse)
        displacement_down = (c0['close'] - c3['close'])
        if c0['close'] > c0['open'] and displacement_down > (curr_atr * 1.5):
            subsequent_high = df['high'].iloc[i + 1:].max()
            mitigated = subsequent_high >= c0['high']

            order_blocks.append({
                "type": "BEARISH_OB",
                "top": float(c0['high']),
                "bottom": float(c0['low']),
                "entry_level": float(c0['open']),
                "index": i,
                "timestamp": str(c0['timestamp']),
                "is_mitigated": bool(mitigated)
            })

    return order_blocks[-8:]

def detect_liquidity_zones(swings: List[Dict[str, Any]], tolerance_pct: float = 0.05) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detects Buy-Side Liquidity (BSL) resting above equal highs / swing highs,
    and Sell-Side Liquidity (SSL) resting below equal lows / swing lows.
    """
    highs = [s for s in swings if s["type"] == "SWING_HIGH"]
    lows = [s for s in swings if s["type"] == "SWING_LOW"]

    bsl_zones = []
    ssl_zones = []

    # Detect Equal Highs (EQH)
    for i in range(len(highs) - 1):
        for j in range(i + 1, min(i + 4, len(highs))):
            h1, h2 = highs[i], highs[j]
            diff = abs(h1["price"] - h2["price"])
            avg_p = (h1["price"] + h2["price"]) / 2.0
            if (diff / avg_p) * 100.0 <= tolerance_pct:
                bsl_zones.append({
                    "name": "Equal Highs (EQH)",
                    "type": "BSL",
                    "price": float(max(h1["price"], h2["price"])),
                    "first_index": h1["index"],
                    "second_index": h2["index"],
                    "description": "High concentration of buy stop orders and breakout liquidity."
                })

    # Detect Equal Lows (EQL)
    for i in range(len(lows) - 1):
        for j in range(i + 1, min(i + 4, len(lows))):
            l1, l2 = lows[i], lows[j]
            diff = abs(l1["price"] - l2["price"])
            avg_p = (l1["price"] + l2["price"]) / 2.0
            if (diff / avg_p) * 100.0 <= tolerance_pct:
                ssl_zones.append({
                    "name": "Equal Lows (EQL)",
                    "type": "SSL",
                    "price": float(min(l1["price"], l2["price"])),
                    "first_index": l1["index"],
                    "second_index": l2["index"],
                    "description": "High concentration of sell stop orders and liquidity pools."
                })

    # Add most recent major swing high / low if no equal highs found
    if not bsl_zones and highs:
        bsl_zones.append({
            "name": "Major Swing High Liquidity",
            "type": "BSL",
            "price": float(highs[-1]["price"]),
            "index": highs[-1]["index"],
            "description": "Clean swing high holding buy stop liquidity."
        })
    if not ssl_zones and lows:
        ssl_zones.append({
            "name": "Major Swing Low Liquidity",
            "type": "SSL",
            "price": float(lows[-1]["price"]),
            "index": lows[-1]["index"],
            "description": "Clean swing low holding sell stop liquidity."
        })

    return {
        "bsl": bsl_zones[-4:],
        "ssl": ssl_zones[-4:]
    }

def detect_candlestick_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detects key institutional candlestick formations on the latest bars:
    - Bullish & Bearish Engulfing
    - Hammer / Pin Bar / Shooting Star
    - Morning Star / Evening Star
    - Doji
    """
    patterns = []
    if len(df) < 3:
        return patterns

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    curr_body = abs(curr['close'] - curr['open'])
    curr_range = curr['high'] - curr['low']
    prev_body = abs(prev['close'] - prev['open'])
    prev_range = prev['high'] - prev['low']

    # 1. Bullish Engulfing
    if prev['close'] < prev['open'] and curr['close'] > curr['open']:
        if curr['close'] >= prev['open'] and curr['open'] <= prev['close']:
            patterns.append({
                "pattern": "BULLISH_ENGULFING",
                "bias": "BULLISH",
                "confidence": 0.85,
                "description": "Bullish candle completely engulfs previous bearish candle."
            })

    # 2. Bearish Engulfing
    if prev['close'] > prev['open'] and curr['close'] < curr['open']:
        if curr['close'] <= prev['open'] and curr['open'] >= prev['close']:
            patterns.append({
                "pattern": "BEARISH_ENGULFING",
                "bias": "BEARISH",
                "confidence": 0.85,
                "description": "Bearish candle completely engulfs previous bullish candle."
            })

    # 3. Pin Bar / Hammer (Bullish rejection)
    lower_wick = min(curr['open'], curr['close']) - curr['low']
    upper_wick = curr['high'] - max(curr['open'], curr['close'])
    if curr_range > 0 and lower_wick >= (curr_range * 0.60) and upper_wick <= (curr_range * 0.20):
        patterns.append({
            "pattern": "BULLISH_PIN_BAR",
            "bias": "BULLISH",
            "confidence": 0.80,
            "description": "Long lower shadow showing strong rejection of lower prices."
        })

    # 4. Shooting Star / Inverted Hammer (Bearish rejection)
    if curr_range > 0 and upper_wick >= (curr_range * 0.60) and lower_wick <= (curr_range * 0.20):
        patterns.append({
            "pattern": "BEARISH_SHOOTING_STAR",
            "bias": "BEARISH",
            "confidence": 0.80,
            "description": "Long upper shadow showing rejection of higher prices."
        })

    # 5. Doji (Indecision)
    if curr_range > 0 and curr_body <= (curr_range * 0.10):
        patterns.append({
            "pattern": "DOJI",
            "bias": "NEUTRAL",
            "confidence": 0.65,
            "description": "Narrow candle body reflecting market equilibrium / indecision."
        })

    return patterns

def analyze_market_state(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Comprehensive full-spectrum market structure evaluation.
    """
    swings = identify_swing_points(df, left_bars=3, right_bars=3)
    structure = detect_market_structure(df, swings)
    fvgs = detect_fair_value_gaps(df)
    order_blocks = detect_order_blocks(df, swings)
    liquidity = detect_liquidity_zones(swings)
    patterns = detect_candlestick_patterns(df)
    
    # Calculate key support & resistance horizontal clusters
    sr_levels = []
    if swings:
        prices = [s["price"] for s in swings[-12:]]
        prices.sort()
        # Simple clustering
        clusters = []
        for p in prices:
            placed = False
            for c in clusters:
                if abs(c["mean"] - p) / c["mean"] < 0.003:  # within 0.3%
                    c["points"].append(p)
                    c["mean"] = np.mean(c["points"])
                    placed = True
                    break
            if not placed:
                clusters.append({"mean": p, "points": [p]})
        
        for c in clusters:
            if len(c["points"]) >= 2:
                sr_levels.append({
                    "price": float(round(c["mean"], 5)),
                    "touches": len(c["points"]),
                    "type": "RESISTANCE" if c["mean"] > df["close"].iloc[-1] else "SUPPORT"
                })

    return {
        "trend": structure["trend"],
        "structure_bias": structure["bias"],
        "swings": structure["labeled_swings"][-10:],
        "boss": structure["boss"],
        "chochs": structure["chochs"],
        "fvgs": fvgs,
        "order_blocks": order_blocks,
        "liquidity": liquidity,
        "support_resistance": sr_levels[:6],
        "candlestick_patterns": patterns,
        "last_price": float(df["close"].iloc[-1]),
        "bar_count": len(df)
    }
