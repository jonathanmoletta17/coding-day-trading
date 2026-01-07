"""
@category: production
@impact: critical
@description: Master Agent - Decision engine que sintetiza DSL, technical indicators e order book para decisões de trade
"""

import json
import logging
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.analysis.microstructure_analyzer import MicrostructureAnalyzer
from src.data.trade_logger import TradeLogger

logger = logging.getLogger(__name__)

class MasterAgent:
    """
    Lead Quantitative Trader logic.
    Synthesizes signals and enforces risk management protocols.
    """
    
    def __init__(self, equity: float = 100000.0, max_risk_pct: float = 0.01):
        self.equity = equity
        self.max_risk_pct = max_risk_pct
        self.daily_halt_threshold = -0.03 # -3% daily drawdown
        self.micro_analyzer = MicrostructureAnalyzer()
        self.logger_db = TradeLogger()

    def decide(self, data: Dict[str, Any]) -> str:
        """
        Main entry point for decision making. Returns a JSON string as specified by protocol.
        """
        # 1. Preliminary Data Extraction
        context = data.get("context", {})
        asset = data.get("asset", {})
        legacy_signals = data.get("legacy_signals", [])
        portfolio = data.get("portfolio", {})
        
        # 2. Daily PL Check (Rule 3)
        daily_pl = portfolio.get("daily_pl_pct", 0.0)
        if daily_pl <= self.daily_halt_threshold:
            return self._format_output(
                "CRITICAL: Daily drawdown threshold hit. HALTING all trading.",
                "HOLD", 0, 0, 0, 0, 1.0
            )

        # 3. Decision Logic - Synthesis (Rule 1)
        # Check for Legacy Core signals with high confidence (> 0.9)
        best_legacy = None
        for sig in legacy_signals:
            if sig.get("confidence", 0) >= 0.9:
                best_legacy = sig
                break
        
        # 4. Technical Confluence
        rsi = asset.get("technicals", {}).get("rsi_14", 50)
        macd = asset.get("technicals", {}).get("macd_hist", 0)
        imbalance = asset.get("order_book", {}).get("imbalance", 1.0)
        
        
        # 3. Microstructure Validation (Absorption & Spoofing)
        # We need to simulate the 'update' call here with available snapshot data
        # In a real loop, this would be updated tick-by-tick
        micro_metrics = self.micro_analyzer.update(asset.get("order_book", {}))
        is_spoofing = micro_metrics.is_spoofing
        is_absorbed = self._detect_absorption(asset)
        
        # 4. Multi-Factor Confluence Scoring (Rule 1 - Refined)
        score, confluence_data = self._calculate_confluence_score(asset, legacy_signals)
        
        decision = "HOLD"
        reasoning = []
        
        # Execution Threshold
        if is_spoofing:
            reasoning.append(f"ENTRY BLOCKED: High-frequency Spoofing detected (CTR={micro_metrics.ctr:.1f}).")
        elif score >= 0.85 and not is_absorbed:
            # Determine Direction based on primary signal and OB
            primary_sig = confluence_data.get("primary_signal", {})
            pattern = primary_sig.get("pattern", "")
            
            # Simple directional mapping
            if pattern == "LIQUIDITY_SWEEP":
                # Confluence logic (already factored into score)
                if rsi < 35 and imbalance > 1.0:
                    decision = "BUY"
                    reasoning.append(f"V1-Pro: Strong Confluence Score ({score:.2f}).")
                elif rsi > 65 and imbalance < 1.0:
                    decision = "SELL"
                    reasoning.append(f"V1-Pro: Strong Confluence Score ({score:.2f}).")
            else:
                 reasoning.append(f"Score ({score:.2f}) met but pattern logic missing. Holding.")
        elif is_absorbed:
            reasoning.append("ENTRY BLOCKED: Institutional Absorption detected.")
        else:
            reasoning.append(f"Confluence Score ({score:.2f}) insufficient for entry.")
            
        # 5. Price and ATR Context
        price = asset.get("price", 0)
        symbol = asset.get("symbol", "")
        atr = asset.get("technicals", {}).get("atr_14")
        if atr is None:
            atr = 100.0 if "BTC" in symbol else 0.5

        # 6. Risk Management (Rule 2 - Refined)
        # Dynamic Risk based on Stability
        stability = context.get("stability", "MEDIUM")
        stability_multiplier = {"HIGH": 1.0, "MEDIUM": 0.8, "LOW": 0.5}.get(stability, 0.7)
        max_risk_amt = self.equity * self.max_risk_pct * stability_multiplier
        
        # Calculate SL/TP
        if decision == "BUY":
            stop_loss = price - (atr * 2)
            take_profit = price + (atr * 4)
            risk_per_unit = price - stop_loss
            units = int(max_risk_amt / risk_per_unit) if risk_per_unit > 0 else 0
        elif decision == "SELL":
            stop_loss = price + (atr * 2)
            take_profit = price - (atr * 4)
            risk_per_unit = stop_loss - price
            units = int(max_risk_amt / risk_per_unit) if risk_per_unit > 0 else 0
        else:
            stop_loss = take_profit = units = 0

        # 7. Execution Type (Maker vs Taker)
        exec_type = "LIMIT"
        if imbalance > 3.0 or imbalance < 0.33:
            exec_type = "MARKET" # Taker to ensure entry on high imbalance
            reasoning.append(f"Execution: High imbalance ({imbalance}) triggered MARKET entry.")

        result_json = self._format_output(
            " | ".join(reasoning) if reasoning else "No significant patterns or confluence detected.",
            decision, units, price, take_profit, stop_loss, score, exec_type
        )
        
        # 8. Neural Vault Logging (Phase 5)
        # We parse it back briefly just to pass dict to logger (or optimize later)
        try:
            res_dict = json.loads(result_json)
            self.logger_db.log_decision(data, res_dict, micro_metrics)
        except Exception as e:
            logger.warning(f"Logging failed: {e}")
            
        return result_json

    def _detect_absorption(self, asset: Dict[str, Any]) -> bool:
        """
        Detects ifinstitutional institutional orders are 'absorbing' aggressive market pressure.
        Patterns: High volume near price wall with no displacement.
        """
        # Simplified for V1-Pro: High imbalance with static price
        imbalance = asset.get("order_book", {}).get("imbalance", 1.0)
        # In a real tape analyzer we would check execution velocity
        # For this version, we flag as potential absorption if imbalance is extreme (> 10.0 or < 0.1)
        # suggesting a 'wall' is being tested but not broken yet.
        return imbalance > 10.0 or imbalance < 0.1

    def _calculate_confluence_score(self, asset: Dict[str, Any], legacy_signals: List[Dict[str, Any]]) -> tuple:
        """
        Calculates a weighted score based on 3 axes: DSL, Technicals, and Order Book.
        Weights: DSL (0.5), Technical (0.3), Order Book (0.2)
        """
        # 1. DSL Score (0.5)
        dsl_score = 0.0
        primary_sig = {}
        if legacy_signals:
            # Take the highest confidence signal
            best = max(legacy_signals, key=lambda x: x.get("confidence", 0))
            dsl_score = best.get("confidence", 0) * 0.5
            primary_sig = best
            
        # 2. Technical Score (0.3)
        tech_score = 0.0
        rsi = asset.get("technicals", {}).get("rsi_14", 50)
        # Check for oversold/overbought support
        if rsi < 35 or rsi > 65:
            tech_score = 0.3 # Strong technical support for the pattern
        elif rsi < 45 or rsi > 55:
            tech_score = 0.15 # Weak technical support
            
        # 3. Order Book Score (0.2)
        ob_score = 0.0
        imbalance = asset.get("order_book", {}).get("imbalance", 1.0)
        # Direct directional alignment check
        if imbalance > 2.0 or imbalance < 0.5:
             ob_score = 0.2
        elif imbalance > 1.5 or imbalance < 0.66:
             ob_score = 0.1
             
        total_score = dsl_score + tech_score + ob_score
        return total_score, {"primary_signal": primary_sig}

    def _format_output(self, thought, decision, units, price, tp, sl, conf, exec_type="LIMIT") -> str:
        res = {
            "thought_process": thought,
            "decision": decision,
            "sizing": {
                "units": units,
                "leverage": 1.0
            },
            "execution": {
                "type": exec_type,
                "price": price,
                "take_profit": tp,
                "stop_loss": sl
            },
            "confidence": conf
        }
        return json.dumps(res, indent=2)

if __name__ == "__main__":
    # Test Payload
    test_data = {
      "context": {"market_phase": "VOLATILE", "global_risk_level": "LOW"},
      "asset": {
        "symbol": "BTCUSDT",
        "price": 50000.00,
        "order_book": {"bid_depth": 500000, "ask_depth": 100000, "imbalance": 5.0},
        "technicals": {"rsi_14": 30, "macd_hist": 0.05}
      },
      "legacy_signals": [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.95}],
      "portfolio": {"exposure_net": 0, "daily_pl_pct": 0.0}
    }
    agent = MasterAgent()
    print(agent.decide(test_data))
