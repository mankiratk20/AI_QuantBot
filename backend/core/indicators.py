"""
Technical Indicators Calculation Module.
Calculates Moving Averages (EMA, SMA), RSI, MACD, ATR, Bollinger Bands,
and Swing Highs/Lows for institutional analysis.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    # Wilder's smoothing
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    fast_ema = calculate_ema(series, fast)
    slow_ema = calculate_ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high']
    low = df['low']
    close = df['close']
    
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr.bfill()

def calculate_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> Dict[str, pd.Series]:
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower
    }

def identify_swing_points(df: pd.DataFrame, left_bars: int = 3, right_bars: int = 3) -> List[Dict[str, Any]]:
    """
    Identifies fractal Swing Highs (SH) and Swing Lows (SL).
    A Swing High has lower highs on left and right sides.
    A Swing Low has higher lows on left and right sides.
    """
    swings = []
    n = len(df)
    if n < left_bars + right_bars + 1:
        return swings

    for i in range(left_bars, n - right_bars):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        
        is_swing_high = True
        for j in range(1, left_bars + 1):
            if df['high'].iloc[i - j] >= current_high:
                is_swing_high = False
                break
        if is_swing_high:
            for j in range(1, right_bars + 1):
                if df['high'].iloc[i + j] > current_high:
                    is_swing_high = False
                    break
                    
        is_swing_low = True
        for j in range(1, left_bars + 1):
            if df['low'].iloc[i - j] <= current_low:
                is_swing_low = False
                break
        if is_swing_low:
            for j in range(1, right_bars + 1):
                if df['low'].iloc[i + j] < current_low:
                    is_swing_low = False
                    break
                    
        timestamp = str(df['timestamp'].iloc[i])
        if is_swing_high:
            swings.append({
                "type": "SWING_HIGH",
                "index": i,
                "timestamp": timestamp,
                "price": float(current_high)
            })
        if is_swing_low:
            swings.append({
                "type": "SWING_LOW",
                "index": i,
                "timestamp": timestamp,
                "price": float(current_low)
            })
            
    return swings
