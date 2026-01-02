"""
@category: tool
@impact: low
@description: Diagnóstico: Valida stream de ticks
"""

import MetaTrader5 as mt5
import time
import pandas as pd
from datetime import datetime

def check_tick_data(symbol="PETR4"):
    print(f"=== VERIFICAÇÃO DE DADOS DE TICK: {symbol} ===")
    
    if not mt5.initialize():
        print("❌ Falha ao inicializar MT5")
        return

    # Seleciona o símbolo no Market Watch
    if not mt5.symbol_select(symbol, True):
        print(f"❌ Falha ao selecionar símbolo {symbol}. Tentando adicionar...")
        # Tenta adicionar, as vezes precisa estar visível
    
    # Verifica se o símbolo existe
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"❌ Símbolo {symbol} não encontrado. Tente WIN$ ou WINZ24 ou WDO$ se for futuros, ou PETR4 se for ações.")
        print("   Liste alguns símbolos disponíveis para ajudar:")
        symbols = mt5.symbols_get()
        if symbols:
            print(f"   Exemplos: {[s.name for s in symbols[:5]]}")
        mt5.shutdown()
        return

    print(f"✅ Símbolo {symbol} encontrado.")
    print(f"   Descrição: {info.description}")
    print(f"   Caminho: {info.path}")
    
    print("\nLendo último tick...")
    tick = mt5.symbol_info_tick(symbol)
    
    if tick is None:
        print("❌ Falha ao obter tick. O mercado está aberto?")
    else:
        print(f"✅ Tick recebido às {datetime.fromtimestamp(tick.time)}")
        print(f"   Last: {tick.last}")
        print(f"   Bid:  {tick.bid}")
        print(f"   Ask:  {tick.ask}")
        print(f"   Volume: {tick.volume}")
        print(f"   Flags: {tick.flags}")

    print("\nMonitorando por 10 segundos (Mudanças de preço)...")
    start_time = time.time()
    last_price = tick.last if tick else 0
    
    try:
        while time.time() - start_time < 10:
            tick = mt5.symbol_info_tick(symbol)
            if tick and tick.last != last_price:
                print(f"   >> Novo preço: {tick.last} (Bid: {tick.bid} / Ask: {tick.ask})")
                last_price = tick.last
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    mt5.shutdown()

if __name__ == "__main__":
    # Pode pedir input do usuário ou testar um padrão
    symbol_to_test = input("Digite o ativo para testar (padrão PETR4): ").strip()
    if not symbol_to_test:
        symbol_to_test = "PETR4"
    check_tick_data(symbol_to_test)
