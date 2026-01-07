"""
@category: production
@impact: moderate
@description: Multi-benchmark analysis para comparação de estratégias em diferentes cenários
"""
import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.analysis.financial_backtester import FinancialBacktester

def run_benchmarks():
    assets = [
        {"symbol": "BTCUSDT", "source": "BINANCE", "tf": "1h"},
        {"symbol": "ETHUSDT", "source": "BINANCE", "tf": "1h"},
        {"symbol": "SOLUSDT", "source": "BINANCE", "tf": "1h"},
        {"symbol": "PETR4", "source": "MT5", "tf": "M15"},
    ]
    
    reports = []
    
    print("\n🚀 INICIANDO BATERIA DE BENCHMARKS FINANCEIROS\n")
    
    for asset in assets:
        tester = FinancialBacktester(initial_equity=100000.0)
        tester.run(asset['symbol'], timeframe=asset['tf'], candles=720, source=asset['source'])
        
        if tester.history:
            df = pd.DataFrame(tester.history)
            reports.append({
                "Ativo": asset['symbol'],
                "Retorno %": (tester.equity/100000.0 - 1)*100,
                "Trades": len(df),
                "Win Rate %": (df['pnl'] > 0).mean() * 100,
                "Profit Factor": abs(df[df['pnl']>0]['pnl'].sum() / df[df['pnl']<0]['pnl'].sum()) if any(df['pnl']<0) else 10.0
            })

    if reports:
        final_df = pd.DataFrame(reports)
        print("\n📊 RELATÓRIO CONSOLIDADO DE PERFORMANCE")
        print(final_df.to_string(index=False))
        
        # Save to markdown for artifact
        with open("/home/workbench/projects/coding-day-trading/benchmark_results.md", "w") as f:
            f.write("# 📈 Resultados de Benchmark Financeiro\n\n")
            f.write(final_df.to_markdown(index=False))
            f.write(f"\n\n**Data da Análise**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    run_benchmarks()
