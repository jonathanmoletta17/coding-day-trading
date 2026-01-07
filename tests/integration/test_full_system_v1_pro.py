"""
@category: test
@impact: moderate
@description: Testes de integração do Master Agent V1-Pro com microstructure analyzer
"""
import sys
import os
import json
import unittest
import time
import sqlite3

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.agents.master_agent import MasterAgent

class TestFullSystemV1Pro(unittest.TestCase):
    def setUp(self):
        # Use a temporary DB for testing
        self.test_db = "test_memory.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
            
        self.agent = MasterAgent()
        # Override logger to use test DB
        self.agent.logger_db.db_path = self.test_db
        self.agent.logger_db._init_db()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_ideal_entry_flow(self):
        """
        Scenario: Perfect conditions.
        Expectation: BUY Signal + Logged to DB.
        """
        print("\n--- [E2E] Testing Ideal Entry Flow ---")
        
        # 1. Setup Context
        data = {
            "context": {"stability": "HIGH"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 100000.0,
                "order_book": {"imbalance": 3.0}, # Bullish OB
                "technicals": {"rsi_14": 30} # Oversold
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}] 
        }
        
        # 2. Execution
        res_json = self.agent.decide(data)
        res = json.loads(res_json)
        
        # 3. Validation - Decision
        print(f"Decision: {res['decision']} | Score: {res['confidence']:.2f}")
        self.assertEqual(res["decision"], "BUY")
        self.assertGreater(res["confidence"], 0.9)
        
        # 4. Validation - Database (Neural Vault)
        conn = sqlite3.connect(self.test_db)
        row = conn.cursor().execute("SELECT symbol, decision, confluence_score FROM decision_log").fetchone()
        conn.close()
        
        print(f"DB Record: {row}")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "BTCUSDT")
        self.assertEqual(row[1], "BUY")

    def test_spoofing_defense_flow(self):
        """
        Scenario: Perfect conditions BUT with Spoofing Attack.
        Expectation: ENTRY BLOCKED (HOLD) + Logged to DB with Alert.
        """
        print("\n--- [E2E] Testing Spoofing Defense Flow ---")
        
        # 1. Inject Spoofing (High Cancels)
        self.agent.micro_analyzer.cancellations = [(time.time(), 50000.0)]
        self.agent.micro_analyzer.executions = [(time.time(), 100.0)] # CTR = 500
        self.agent.micro_analyzer.updates = [time.time()] * 10
        
        # 2. Setup Context (Same as Ideal)
        data = {
            "context": {"stability": "HIGH"},
            "asset": {
                "symbol": "BTCUSDT",
                "price": 100000.0,
                "order_book": {"imbalance": 3.0},
                "technicals": {"rsi_14": 30}
            },
            "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}] 
        }
        
        # 3. Execution
        res_json = self.agent.decide(data)
        res = json.loads(res_json)
        
        # 4. Validation
        print(f"Decision: {res['decision']} | Reason: {res['thought_process']}")
        self.assertEqual(res["decision"], "HOLD")
        self.assertIn("SPOOFING", res["thought_process"].upper())
        
        # 5. DB Check
        conn = sqlite3.connect(self.test_db)
        row = conn.cursor().execute("SELECT decision, ctr_ratio FROM decision_log").fetchone()
        conn.close()
        print(f"DB Record: {row}")
        self.assertEqual(row[0], "HOLD")
        self.assertGreater(row[1], 10.0)

if __name__ == "__main__":
    unittest.main()
