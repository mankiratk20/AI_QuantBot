"""
AI Trade Explanation and Confluence Scoring Module.
Generates comprehensive, professional quantitative explanations for trade setups
strictly based on the user's configured rules, verified market structure,
and transparent confluence scoring methodology.
"""

from typing import Dict, Any, List

def calculate_confluence_score(
    satisfied_conditions: List[Dict[str, Any]],
    not_satisfied_conditions: List[Dict[str, Any]],
    market_state: Dict[str, Any],
    has_higher_timeframe_alignment: bool = True
) -> float:
    """
    Methodology for Confidence / Confluence Score (0.0 to 100.0%):
    - Base weight: 40% allocated across required user strategy conditions (100% of required must pass)
    - Market Structure Weight: 25% (Clean trend alignment, clear BOS/CHOCH)
    - Institutional Footprint Weight: 20% (Unmitigated FVG or Clean Order Block)
    - Candlestick Rejection Weight: 10% (Engulfing or Pin bar confirmation)
    - Multi-timeframe confirmation Weight: 5% (Higher timeframe directional agreement)
    """
    total_required = len(satisfied_conditions) + len(not_satisfied_conditions)
    if total_required == 0 or len(not_satisfied_conditions) > 0:
        return 0.0

    score = 40.0  # All required user conditions passed

    # Structure check
    if market_state.get("trend") in ["BULLISH", "BEARISH"]:
        score += 15.0
    if len(market_state.get("boss", [])) > 0 or len(market_state.get("chochs", [])) > 0:
        score += 10.0

    # SMC Imbalance / OB check
    if len(market_state.get("fvgs", [])) > 0:
        score += 10.0
    if len(market_state.get("order_blocks", [])) > 0:
        score += 10.0

    # Candlestick pattern
    if len(market_state.get("candlestick_patterns", [])) > 0:
        score += 10.0

    # HTF Alignment
    if has_higher_timeframe_alignment:
        score += 5.0

    return min(95.0, score)  # Cap at 95% to maintain risk realism (never claim 100% certainty)

def generate_trade_explanation(
    symbol: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    timeframe: str,
    strategy_name: str,
    satisfied_conditions: List[Dict[str, Any]],
    not_satisfied_conditions: List[Dict[str, Any]],
    market_state: Dict[str, Any],
    confluence_score: float
) -> Dict[str, Any]:
    """
    Produces structured textual and componentized analysis of the trade signal.
    """
    trend = market_state.get("trend", "NEUTRAL")
    sl_dist = abs(entry_price - stop_loss)
    tp_dist = abs(take_profit - entry_price)
    rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0

    # Construct structural thesis narrative
    structure_narrative = (
        f"The {timeframe} market structure for {symbol} displays a confirmed {trend} bias. "
    )

    chochs = market_state.get("chochs", [])
    if chochs:
        structure_narrative += f"A key {chochs[-1]['type']} was printed, indicating a valid institutional shift in market delivery. "

    fvgs = market_state.get("fvgs", [])
    if fvgs:
        active_fvg = fvgs[-1]
        structure_narrative += (
            f"An active {active_fvg['type']} is resting between {active_fvg['bottom']:.5f} and {active_fvg['top']:.5f}, "
            "providing fair value pricing for optimal trade entry. "
        )

    obs = market_state.get("order_blocks", [])
    if obs:
        active_ob = obs[-1]
        structure_narrative += (
            f"An institutional {active_ob['type']} spans from {active_ob['bottom']:.5f} to {active_ob['top']:.5f}, "
            "acting as strong structural protection for the invalidation level. "
        )

    patterns = market_state.get("candlestick_patterns", [])
    if patterns:
        structure_narrative += f"Candlestick price action confirms entry via {patterns[-1]['pattern']}. "

    # Rule compliance summary
    satisfied_desc = [
        f"{c['field']} {c['operator']} {c['expected']} (Actual: {c['actual']})"
        for c in satisfied_conditions
    ]
    not_satisfied_desc = [
        f"{c['field']} {c['operator']} {c['expected']} (Actual: {c['actual']})"
        for c in not_satisfied_conditions
    ]

    methodology_text = (
        f"Confluence score of {confluence_score:.1f}% is calculated deterministically: "
        f"40% base weight for 100% compliance with user-defined rules in '{strategy_name}', "
        f"plus structural confluence ({trend} trend, BOS/CHOCH), liquidity/FVG mitigation, "
        f"and candlestick confirmation. Score is strictly capped at 95% to preserve institutional risk discipline."
    )

    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward_ratio": rr_ratio,
        "timeframe": timeframe,
        "strategy_name": strategy_name,
        "confidence_score": confluence_score,
        "confidence_methodology": methodology_text,
        "market_structure_narrative": structure_narrative,
        "conditions_satisfied": satisfied_desc,
        "conditions_not_satisfied": not_satisfied_desc,
        "is_executable": len(not_satisfied_conditions) == 0
    }
