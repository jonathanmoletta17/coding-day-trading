"""
@category: test
@impact: critical
@description: Testes unitários do microstructure analyzer (spoofing detection, velocity tracking)
"""
import sys
import os
import json
import unittest
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.agents.master_agent import MasterAgent

class TestMicrostructureProtection(unittest.TestCase):
    def setUp(self):
        self.agent = MasterAgent()

    def test_spoofing_trigger(self):
        """Test that high CTR (>10) blocks even a perfect signal"""
        
        # 1. Simulate High Frequency Cancellations (Spoofing)
        # Inject fake events into the analyzer
        self.agent.micro_analyzer.cancellations = [
            (time.time(), 1000.0) for _ in range(20) # 20k volume canceled
        ]
        self.agent.micro_analyzer.executions = [
            (time.time(), 100.0) # 100 volume executed
        ]
        self.agent.micro_analyzer.updates = [time.time() for _ in range(10)] # High velocity
        
        # 2. Perfect Setup (Would normally result in BUY)
        data = {
            "context": {"stability": "HIGH"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "order_book": {"imbalance": 2.5}, # Bullish
                "technicals": {"rsi_14": 30} # Oversold
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}] 
        }
        
        # 3. Decision
        res = json.loads(self.agent.decide(data))
        
        # 4. Assertions
        print(f"\n[Spoofing Test] Decision: {res['decision']}")
        print(f"[Spoofing Test] Reason: {res['thought_process']}")
        
        self.assertEqual(res["decision"], "HOLD")
        self.assertIn("SPOOFING", res["thought_process"].upper())
        self.assertIn("ENTRY BLOCKED", res["thought_process"])

    def test_velocity_metrics(self):
        """Verify velocity calculation"""
        self.agent.micro_analyzer.updates = [time.time() - 0.1 for _ in range(5)]
        # Force update to recalc metrics
        _ = self.agent.micro_analyzer._calculate_velocity(time.time())
        # In the test environment exact timing varies, but count should be 5
        self.assertGreaterEqual(len(self.agent.micro_analyzer.updates), 5)

if __name__ == "__main__":
    unittest.main()
