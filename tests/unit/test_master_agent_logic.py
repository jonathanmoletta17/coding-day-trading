"""
@category: test
@impact: critical
@description: Testes unitários da lógica de decisão do Master Agent
"""
import sys
import os
import json
import unittest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.agents.master_agent import MasterAgent

class TestMasterAgentLogic(unittest.TestCase):
    def setUp(self):
        self.agent = MasterAgent()

    def test_neutral_market(self):
        """Test score 0.00 in neutral market (matches user screenshot)"""
        data = {
            "context": {"stability": "MEDIUM"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "order_book": {"imbalance": 1.0}, # Neutral
                "technicals": {"rsi_14": 50, "atr_14": 100.0} # Neutral
            },
            "legacy_signals": [] # No signals
        }
        res = json.loads(self.agent.decide(data))
        self.assertEqual(res["confidence"], 0.0)
        self.assertEqual(res["decision"], "HOLD")
        print(f"\n[Neutral Test] Score: {res['confidence']} -> Decision: {res['decision']}")

    def test_strong_buy_confluence(self):
        """Test score > 0.85 with full confluence"""
        data = {
            "context": {"stability": "HIGH"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "order_book": {"imbalance": 2.5}, # Bullish OB (> 2.0 = +0.2)
                "technicals": {"rsi_14": 30, "atr_14": 100.0} # Oversold (< 35 = +0.3)
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}] # DSL (+0.475)
        }
        # Expected Score: 0.475 + 0.3 + 0.2 = 0.975
        res = json.loads(self.agent.decide(data))
        self.assertGreater(res["confidence"], 0.85)
        self.assertEqual(res["decision"], "BUY")
        print(f"[Buy Test] Score: {res['confidence']:.3f} -> Decision: {res['decision']}")

    def test_absorption_filter(self):
        """Test absorption blocking a trade"""
        data = {
            "context": {"stability": "HIGH"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "order_book": {"imbalance": 12.0}, # Extreme (> 10 = Absorption)
                "technicals": {"rsi_14": 30, "atr_14": 100.0}
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}]
        }
        res = json.loads(self.agent.decide(data))
        # Logic: Score might be high, but Absorption blocks it
        self.assertEqual(res["decision"], "HOLD")
        self.assertIn("Absorption detected", res["thought_process"])
        print(f"[Absorption Test] Decision: {res['decision']} -> Reason: {res['thought_process']}")

if __name__ == "__main__":
    unittest.main()
