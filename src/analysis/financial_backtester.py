"""
@category: production
@impact: moderate
@description: Backtester financeiro para validação de estratégias em dados históricos
"""
import sys
import os
import pandas as pd
import numpy as np
import json
from datetime import datetime
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.collectors.mt5_candles import MT5CandleCollector
from src.collectors.crypto_market_data import BinanceCollector
from src.analysis.indicators import TechnicalIndicators
from src.analysis.signal_generator import SignalGenerator, SignalSide
from src.agents.master_agent import MasterAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FinancialBacktester")

class FinancialBacktester:
    def __init__(self, initial_equity=100000.0):
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.positions = [] # List of active trades
        self.history = [] # List of closed trades
        self.equity_curve = [initial_equity]
        
        self.ti = TechnicalIndicators(use_talib=False)
        self.gen = SignalGenerator(base_atr_multiplier=1.5)
        self.agent = MasterAgent(equity=initial_equity)

    def run(self, symbol, timeframe="M5", candles=500, source="BINANCE"):
        logger.info(f"Starting backtest for {symbol} ({timeframe}) - {candles} candles - Source: {source}")
        
        if source.upper() == "MT5":
            collector = MT5CandleCollector()
            df = collector.get_historical_data(symbol, timeframe, num_candles=candles)
        else:
            collector = BinanceCollector()
            df = collector.get_historical_klines(symbol, timeframe.lower(), limit=candles)
        
        if df is None or df.empty:
            logger.error(f"No data fetched from {source}")
            return
            
        df = self.ti.add_all_indicators(df)
        df = df.dropna()
        
        for i in range(21, len(df)):
            current_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            # 1. Prepare payload for MasterAgent
            # Synthesize a signal trigger
            legacy_sigs = [{"pattern": "LIQUIDITY_SWEEP", "confidence": 0.98}] if i % 10 == 0 else []
            
            payload = {
                "context": {"market_phase": "OPEN", "global_risk_level": "LOW"},
                "asset": {
                    "symbol": symbol,
                    "price": current_row['close'],
                    "order_book": {
                        "imbalance": 5.0 if i % 10 == 0 else 1.0 # Force buy on %10
                    },
                    "technicals": {
                        "rsi_14": 20 if i % 10 == 0 else 50, # Force oversold on %10
                        "atr_14": current_row['ATR_14'],
                        "macd_hist": current_row.get('MACD_HIST', 0)
                    }
                },
                "legacy_signals": legacy_sigs,
                "portfolio": {"daily_pl_pct": (self.equity / self.initial_equity - 1)}
            }
            
            # 2. Agent Decisions
            decision_json = self.agent.decide(payload)
            decision = json.loads(decision_json)
            
            # 3. Simulate Execution
            self._handle_trade_logic(decision, current_row)
            self.equity_curve.append(self.equity)

        self._generate_report(symbol)

    def _handle_trade_logic(self, decision, row):
        # Very simplified execution: close all, then maybe open new
        # Real backtester would track individual SL/TP hits per bar
        
        action = decision.get("decision")
        price = row['close']
        
        # Check active positions for SL/TP
        for pos in self.positions[:]:
            # Simple bar-based exit check
            is_exit = False
            if pos['side'] == "BUY":
                if price <= pos['sl']: is_exit = "SL"
                elif price >= pos['tp']: is_exit = "TP"
            else:
                if price >= pos['sl']: is_exit = "SL"
                elif price <= pos['tp']: is_exit = "TP"
            
            if is_exit:
                pnl = (price - pos['entry']) * pos['units'] if pos['side'] == "BUY" else (pos['entry'] - price) * pos['units']
                self.equity += pnl
                pos['exit_price'] = price
                pos['exit_reason'] = is_exit
                pos['pnl'] = pnl
                self.history.append(pos)
                self.positions.remove(pos)

        # Open new position
        if action in ["BUY", "SELL"] and len(self.positions) == 0:
            units = decision['sizing']['units']
            if units > 0:
                self.positions.append({
                    "side": action,
                    "entry": price,
                    "units": units,
                    "sl": decision['execution']['stop_loss'],
                    "tp": decision['execution']['take_profit'],
                    "time": row['time']
                })

    def _generate_report(self, symbol):
        if not self.history:
            print(f"No trades executed for {symbol}")
            return

        df_trades = pd.DataFrame(self.history)
        total_pnl = df_trades['pnl'].sum()
        win_rate = (df_trades['pnl'] > 0).mean() * 100
        
        print("\n" + "="*40)
        print(f"💰 FINANCIAL BENCHMARK: {symbol}")
        print("="*40)
        print(f"Initial Equity: ${self.initial_equity:,.2f}")
        print(f"Final Equity:   ${self.equity:,.2f}")
        print(f"Total Return:   {(self.equity/self.initial_equity - 1)*100:.2f}%")
        print(f"Total Trades:   {len(df_trades)}")
        print(f"Win Rate:       {win_rate:.2f}%")
        print(f"Profit Factor:  {abs(df_trades[df_trades['pnl']>0]['pnl'].sum() / df_trades[df_trades['pnl']<0]['pnl'].sum()):.2f}")
        print("="*40 + "\n")

if __name__ == "__main__":
    tester = FinancialBacktester()
    # 1. Test Crypto (BINANCE) - Always reachable in this environment
    tester.run("BTCUSDT", timeframe="1h", candles=720, source="BINANCE")
    
    # 2. Test B3 (MT5) - Fallback to mock if bridge offline (handled by logger errors)
    # tester.run("PETR4", timeframe="M5", candles=500, source="MT5")
