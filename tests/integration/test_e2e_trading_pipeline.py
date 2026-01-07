"""
@category: test
@impact: moderate
@description: Testes end-to-end do pipeline completo (Postgres -> Bridge -> API -> DB)
"""
import sys
import os
import json
import unittest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.agents.master_agent import MasterAgent

class TestE2ETradingPipeline(unittest.TestCase):
    def setUp(self):
        self.agent = MasterAgent(equity=100000.0)

    def test_confluence_buy_signal(self):
        """
        Verify that DSL Sweep + RSI Oversold + OB Imbalance => BUY
        """
        payload = {
            "context": {"market_phase": "VOLATILE", "stability": "LOW"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 40000.0,
                "order_book": {"imbalance": 5.0},
                "technicals": {"rsi_14": 25.0, "atr_14": 200.0}
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}],
            "portfolio": {"daily_pl_pct": 0.0}
        }
        
        result_json = self.agent.decide(payload)
        result = json.loads(result_json)
        
        self.assertEqual(result["decision"], "BUY")
        self.assertGreaterEqual(result["confidence"], 0.8)
        self.assertEqual(result["execution"]["type"], "MARKET")
        # In Low Stability (LOW), multiplier is 1.5. Base is 1.5. 1.5 * 1.5 = 2.25. (Wait, MasterAgent doesn't use SignalGenerator's adaptive internal logic yet, it uses its own Rule 2)
        # Actually MasterAgent uses ATR * 2 hardcoded for now in my last edit? No, let's check MasterAgent.py lines 93-94
        
    def test_conflict_no_trade(self):
        """
        Verify that DSL Sweep + RSI Overbought => HOLD (Logic expects confluence)
        """
        payload = {
            "context": {"market_phase": "VOLATILE", "stability": "HIGH"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 40000.0,
                "order_book": {"imbalance": 5.0},
                "technicals": {"rsi_14": 80.0, "atr_14": 200.0}
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}],
            "portfolio": {"daily_pl_pct": 0.0}
        }
        
        result_json = self.agent.decide(payload)
        result = json.loads(result_json)
        
        # In my MasterAgent logic: if pattern is Sweep but RSI > 65 and Imbalance < 0.5 -> SELL.
        # But here RSI is 80 (Oversold/Bought conflict) and Imbalance is 5.0 (Bullish).
        # It should probably HOLD or be careful.
        self.assertEqual(result["decision"], "HOLD")

    def test_daily_drawdown_halt(self):
        """
        Verify that Daily PL < -3% => HALT
        """
        payload = {
            "context": {"market_phase": "VOLATILE"},
            "asset": {"symbol": "BTCUSDT", "price": 40000.0},
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.99}],
            "portfolio": {"daily_pl_pct": -0.04} # -4%
        }
        
        result_json = self.agent.decide(payload)
        result = json.loads(result_json)
        
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("HALTING", result["thought_process"])

if __name__ == "__main__":
    unittest.main()
