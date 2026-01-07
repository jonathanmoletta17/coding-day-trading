"""
@category: production
@impact: critical
@description: Signal generator com adaptive thresholds baseados em contexto DSL
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from decimal import Decimal

class SignalSide(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NONE = "NONE"

@dataclass(frozen=True)
class TradeSignal:
    timestamp: int  # Unix ms
    symbol: str
    side: SignalSide
    price: float
    stop_loss: float
    take_profit: float
    source_pattern: str
    strength: float  # 0.0 to 1.0
    context_snapshot: Dict[str, Any]

class SignalGenerator:
    """
    High-performance signal generator that translates DSL patterns into trade signals.
    """
    
    def __init__(self, base_atr_multiplier: float = 1.5):
        self.base_atr_multiplier = base_atr_multiplier

    def _get_adaptive_multiplier(self, stability: str) -> float:
        """
        Adjusts the ATR multiplier based on market stability.
        High Stability -> Tighter stops (lower multiplier)
        Low Stability -> Wider stops (higher multiplier)
        """
        mapping = {
            "HIGH": 0.8,
            "MEDIUM": 1.0,
            "LOW": 1.5,
            "EXTREME": 2.0
        }
        factor = mapping.get(stability.upper(), 1.0)
        return self.base_atr_multiplier * factor

    def generate_signals(
        self, 
        occurrences: List[Any], 
        context: Any, 
        current_price: float, 
        atr: float
    ) -> List[TradeSignal]:
        """
        Processes DSL occurrences and returns actionable trade signals.
        """
        signals = []
        
        # Guard: Context veto
        if hasattr(context, 'do_not_operate') and context.do_not_operate:
            return []

        # Calculate adaptive multiplier once per batch
        stability = getattr(context, 'stability', 'MEDIUM')
        adaptive_mult = self._get_adaptive_multiplier(stability)

        for occ in occurrences:
            signal = self._process_occurrence(occ, context, current_price, atr, adaptive_mult)
            if signal and signal.side != SignalSide.NONE:
                signals.append(signal)
        
        return signals

    def _process_occurrence(
        self, 
        occ: Any, 
        context: Any, 
        current_price: float, 
        atr: float,
        multiplier: float
    ) -> Optional[TradeSignal]:
        pattern_name = occ.pattern
        side = SignalSide.NONE
        sl = 0.0
        tp = 0.0
        strength = 0.5
        
        # 1. Multi-Level Erosion (Liquidity Sweep)
        if pattern_name == "MultiLevelErosion":
            sweep_side = occ.emit.get("side")
            
            if sweep_side == "BUY": # Sweep high (aggressive buying cleared liquidity)
                side = SignalSide.SELL
                sl = current_price + (atr * multiplier)
                tp = current_price - (atr * multiplier * 2) # 1:2 RR
                strength = 0.8
            elif sweep_side == "SELL": # Sweep low
                side = SignalSide.BUY
                sl = current_price - (atr * multiplier)
                tp = current_price + (atr * multiplier * 2)
                strength = 0.8

        # 2. Depletion Exhaustion
        elif pattern_name == "DepletionSequence":
            side_depl = occ.emit.get("side")
            if side_depl == "BUY":
                side = SignalSide.SELL
                sl = current_price + (atr * multiplier)
                tp = current_price - (atr * multiplier * 1.5)
                strength = 0.6
            elif side_depl == "SELL":
                side = SignalSide.BUY
                sl = current_price - (atr * multiplier)
                tp = current_price + (atr * multiplier * 1.5)
                strength = 0.6

        if side != SignalSide.NONE:
            return TradeSignal(
                timestamp=occ.end_ts,
                symbol=occ.stream_key[1],
                side=side,
                price=current_price,
                stop_loss=sl,
                take_profit=tp,
                source_pattern=pattern_name,
                strength=strength,
                context_snapshot={
                    "stability": getattr(context, "stability", "UNKNOWN"),
                    "liquidity": getattr(context, "liquidity", "UNKNOWN"),
                    "activity": getattr(context, "activity", "UNKNOWN"),
                    "multiplier_applied": multiplier
                }
            )
        
        return None
