"""
@category: test
@impact: moderate
@description: Testes unitários do signal generator com adaptive thresholds
"""
import sys
import os
import unittest
from dataclasses import dataclass
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.analysis.signal_generator import SignalGenerator, SignalSide
from src.microstructure.context_metrics import ContextV01Snapshot

@dataclass
class MockOccurrence:
    pattern: str
    emit: dict
    end_ts: int
    stream_key: tuple

class TestAdaptiveSignals(unittest.TestCase):
    def setUp(self):
        self.gen = SignalGenerator(base_atr_multiplier=1.5)
        self.price = 50000.0
        self.atr = 100.0
        self.occ = MockOccurrence(
            pattern="MultiLevelErosion",
            emit={"side": "BUY"},
            end_ts=1609459200,
            stream_key=("binance", "BTCUSDT", "1m")
        )

    def test_high_stability_multiplier(self):
        ctx = ContextV01Snapshot(
            stability="HIGH", liquidity="HIGH", activity="LOW",
            do_not_operate=False, window_start_ms=0, window_end_ms=0,
            source_path="test", output_sha256=None
        )
        signals = self.gen.generate_signals([self.occ], ctx, self.price, self.atr)
        
        # Base 1.5 * HIGH (0.8) = 1.2
        # SL for SELL: Price + (ATR * 1.2) = 50000 + (100 * 1.2) = 50120
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].stop_loss, 50120.0)
        self.assertAlmostEqual(signals[0].context_snapshot["multiplier_applied"], 1.2)

    def test_low_stability_multiplier(self):
        ctx = ContextV01Snapshot(
            stability="LOW", liquidity="LOW", activity="HIGH",
            do_not_operate=False, window_start_ms=0, window_end_ms=0,
            source_path="test", output_sha256=None
        )
        signals = self.gen.generate_signals([self.occ], ctx, self.price, self.atr)
        
        # Base 1.5 * LOW (1.5) = 2.25
        # SL for SELL: Price + (ATR * 2.25) = 50000 + (100 * 2.25) = 50225
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].stop_loss, 50225.0)
        self.assertEqual(signals[0].context_snapshot["multiplier_applied"], 2.25)

if __name__ == "__main__":
    unittest.main()
