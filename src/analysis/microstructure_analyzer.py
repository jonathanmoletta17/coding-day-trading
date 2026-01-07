"""
@category: production
@impact: critical
@description: Microstructure analyzer V1-Pro - Detecta spoofing, velocity tracking e absorption patterns
"""
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple
import time

@dataclass
class MicrostructureMetrics:
    obi: float = 0.0          # Order Book Imbalance (-1 to 1)
    ctr: float = 0.0          # Cancel-to-Trade Ratio
    velocity: float = 0.0     # Updates per second
    is_spoofing: bool = False # Flag for manipulation

class MicrostructureAnalyzer:
    """
    Analyzes high-frequency order book dynamics to detect manipulation
    and measure market intent (Velocity, Imbalance).
    """
    def __init__(self, window_size_sec: float = 1.0):
        self.window_size = window_size_sec
        # Rolling buffers (timestamp, value)
        self.cancellations: List[Tuple[float, float]] = [] # (time, volume)
        self.executions: List[Tuple[float, float]] = []    # (time, volume)
        self.updates: List[float] = []                     # timestamps of book updates
        self.last_clean_time = time.time()

    def update(self, book_snapshot: Dict, trade_event: Dict = None, cancel_event: Dict = None) -> MicrostructureMetrics:
        """
        Ingest real-time data and return calculated metrics.
        """
        now = time.time()
        
        # 1. Record Events
        self.updates.append(now)
        if trade_event:
            self.executions.append((now, trade_event.get('volume', 0)))
        if cancel_event:
            self.cancellations.append((now, cancel_event.get('volume', 0)))
            
        # Cleanup old data
        if now - self.last_clean_time > 5.0:
            self._cleanup_buffers(now)

        # 2. Calculate Metrics
        obi = self._calculate_obi(book_snapshot)
        ctr = self._calculate_ctr(now)
        velocity = self._calculate_velocity(now)
        
        # 3. Detect Spoofing
        # Rule: High CTR (> 10) indicates layering/spoofing
        is_spoofing = ctr > 10.0 and velocity > 5.0 

        return MicrostructureMetrics(
            obi=obi,
            ctr=ctr,
            velocity=velocity,
            is_spoofing=is_spoofing
        )

    def _calculate_obi(self, snapshot: Dict) -> float:
        """
        Calculate Order Book Imbalance at Level 1.
        OBI = (BidVol - AskVol) / (BidVol + AskVol)
        """
        # Handle both MT5 (simple dict) and Crypto (list of lists) formats
        try:
            # Normalize structure
            bids = snapshot.get('bids', [])
            asks = snapshot.get('asks', [])
            
            # Extract volume from L1
            bid_vol = bids[0][1] if isinstance(bids, list) and len(bids) > 0 else snapshot.get('bid_vol', 0)
            ask_vol = asks[0][1] if isinstance(asks, list) and len(asks) > 0 else snapshot.get('ask_vol', 0)
            
            total = bid_vol + ask_vol
            if total == 0: return 0.0
            
            return (bid_vol - ask_vol) / total
        except Exception:
            return 0.0

    def _calculate_ctr(self, current_time: float) -> float:
        """
        Calculate Cancel-to-Trade Ratio in the lookback window.
        """
        # Filter window
        window_start = current_time - self.window_size
        
        cancel_vol = sum(v for t, v in self.cancellations if t >= window_start)
        exec_vol = sum(v for t, v in self.executions if t >= window_start)
        
        if exec_vol == 0:
            return 100.0 if cancel_vol > 0 else 0.0
            
        return cancel_vol / exec_vol

    def _calculate_velocity(self, current_time: float) -> float:
        """
        Calculate book updates per second.
        """
        window_start = current_time - self.window_size
        count = sum(1 for t in self.updates if t >= window_start)
        return float(count)

    def _cleanup_buffers(self, current_time: float):
        """Keep only relevant history to prevent memory leaks"""
        keep_time = current_time - (self.window_size * 2)
        self.cancellations = [x for x in self.cancellations if x[0] > keep_time]
        self.executions = [x for x in self.executions if x[0] > keep_time]
        self.updates = [x for x in self.updates if x > keep_time]
        self.last_clean_time = current_time
