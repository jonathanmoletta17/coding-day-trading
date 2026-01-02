"""
@category: experiment
@impact: low
@description: Teste de carga pontual
"""

import MetaTrader5 as mt5
import time
import os
import pandas as pd
import numpy as np
from datetime import datetime

def initialize_mt5():
    path_file = "scripts/mt5_validation/mt5_path.txt"
    if os.path.exists(path_file):
        with open(path_file, "r") as f:
            path = f.read().strip()
            if mt5.initialize(path=path):
                return True
    return mt5.initialize()

def stress_test(symbol="EURUSD", duration=30):
    print(f"=== STRESS TEST MT5: {symbol} ({duration}s) ===")
    
    if not initialize_mt5():
        print("❌ Falha ao inicializar MT5")
        return

    if not mt5.symbol_select(symbol, True):
        print(f"❌ Símbolo {symbol} não disponível")
        mt5.shutdown()
        return

    if not mt5.market_book_add(symbol):
        print("❌ Falha ao assinar Book")
        mt5.shutdown()
        return

    print("🚀 Iniciando coleta de alta frequência...")
    
    start_time = time.time()
    tick_count = 0
    book_count = 0
    errors = 0
    
    latencies = []
    depths = []
    
    last_tick_time = 0
    
    try:
        while time.time() - start_time < duration:
            # 1. Coleta Tick
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                # Verifica se é um tick novo
                if tick.time_msc != last_tick_time:
                    tick_count += 1
                    last_tick_time = tick.time_msc
                    
                    # Calcula latência (Hora PC - Hora Tick)
                    # Nota: Relógios podem estar dessincronizados, então olhamos a consistência
                    now_msc = time.time() * 1000
                    latency = now_msc - tick.time_msc
                    latencies.append(latency)

            # 2. Coleta Book
            book = mt5.market_book_get(symbol)
            if book:
                book_count += 1
                depths.append(len(book))
            else:
                errors += 1
            
            # Pequeno sleep para não travar a CPU (simulando loop real)
            # Em HFT real seria busy-wait, mas em Python o GIL atrapalha
            time.sleep(0.01) 

    except KeyboardInterrupt:
        print("🛑 Teste interrompido pelo usuário")

    end_time = time.time()
    total_time = end_time - start_time

    print("\n=== RESULTADOS ===")
    print(f"⏱️  Duração Real: {total_time:.2f}s")
    print(f"📊 Ticks Capturados: {tick_count} ({tick_count/total_time:.2f} ticks/s)")
    print(f"📚 Snapshots de Book: {book_count} ({book_count/total_time:.2f} snaps/s)")
    print(f"❌ Erros de Leitura: {errors}")
    
    if latencies:
        print(f"⚡ Latência Média (PC vs Broker): {np.mean(latencies):.2f}ms")
        print(f"⚡ Latência Máxima: {np.max(latencies):.2f}ms")
        print(f"⚡ Latência Mínima: {np.min(latencies):.2f}ms")
    
    if depths:
        print(f"📉 Profundidade Média do Book: {np.mean(depths):.1f} níveis")
        print(f"📉 Profundidade Máxima: {np.max(depths)} níveis")
        
    # Análise de Limitações
    print("\n=== ANÁLISE DE LIMITAÇÕES ===")
    if book_count/total_time > 50:
        print("✅ Throughput EXCELENTE. Python aguenta o fluxo.")
    elif book_count/total_time > 10:
        print("✅ Throughput BOM. Suficiente para visualização humana.")
    else:
        print("⚠️ Throughput BAIXO. Pode haver lag na visualização.")

    if np.mean(depths) < 5:
        print("⚠️ ALERTA: Profundidade do book é muito baixa (poucos níveis). Heatmap ficará pobre.")
    else:
        print("✅ Profundidade OK para Heatmap.")

    mt5.market_book_release(symbol)
    mt5.shutdown()

if __name__ == "__main__":
    stress_test("EURUSD", 30)
