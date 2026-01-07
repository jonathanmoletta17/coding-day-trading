"""
@category: production
@impact: moderate
@description: Trade logger - Persiste decisões do agent e contexto em SQLite
"""
import sqlite3
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TradeLogger:
    """
    The 'Neural Vault' recorder.
    Persists high-fidelity snapshots of the Agent's thought process,
    market context, and microstructure metrics for future meta-learning.
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Resolve to root/data/trading_memory.db
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.db_path = os.path.join(base_dir, "data", "trading_memory.db")
        else:
            self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create the schema if not exists."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Table: Agent Decisions (The 'Brain' Log)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT,
                    price REAL,
                    decision TEXT,
                    confluence_score REAL,
                    atr_14 REAL,
                    rsi_14 REAL,
                    book_imbalance REAL,
                    ctr_ratio REAL,
                    velocity REAL,
                    decision_json TEXT,  -- Full dump for deep analysis
                    outcome_pl REAL DEFAULT NULL -- Filled later by trade closure
                )
        Records a single decision event.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Extract Core Features (Flattening for SQL query speed)
            asset = payload.get("asset", {})
            tech = asset.get("technicals", {})
            ob = asset.get("order_book", {})
            
            symbol = asset.get("symbol", "UNKNOWN")
            price = asset.get("price", 0.0)
            decision = decision_dict.get("decision", "HOLD")
            score = decision_dict.get("confidence", 0.0)
            
            # Microstructure defaults
            ctr = micro_metrics.ctr if micro_metrics else 0.0
            vel = micro_metrics.velocity if micro_metrics else 0.0
            
            valid_json = json.dumps(decision_dict)
            
            cursor.execute('''
                INSERT INTO decision_log (
                    symbol, price, decision, confluence_score,
                    atr_14, rsi_14, book_imbalance, 
                    ctr_ratio, velocity, decision_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)