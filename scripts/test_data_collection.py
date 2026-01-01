import MetaTrader5 as mt5
import pandas as pd
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()

def run_test_collection():
    print("=== TESTE DE COLETA DE DADOS REAIS (MT5) ===")
    
    # 1. Conexão
    mt5_path = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    if not mt5.initialize(path=mt5_path):
        print(f"❌ Falha ao inicializar MT5: {mt5.last_error()}")
        return
    
    # Login (opcional se já logado, mas bom garantir)
    try:
        login = int(os.getenv("MT5_LOGIN"))
        password = os.getenv("MT5_PASSWORD")
        server = os.getenv("MT5_SERVER")
        if mt5.login(login, password=password, server=server):
            print(f"✅ Login realizado na conta {login}")
        else:
            print(f"⚠️ Falha no login: {mt5.last_error()}")
    except:
        pass

    # 2. Seleção de Ativo
    symbol = "EURUSD"
    selected = mt5.symbol_select(symbol, True)
    if not selected:
        print(f"❌ Falha ao selecionar {symbol}")
        mt5.shutdown()
        return

    print(f"✅ Símbolo {symbol} selecionado")

    # 3. Coleta de Candles (Histórico Recente)
    print("\n--- Teste 1: Coleta de Histórico (Candles) ---")
    candles = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 100)
    if candles is not None and len(candles) > 0:
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"✅ {len(candles)} candles coletados com sucesso.")
        print(f"   Último candle: {df.iloc[-1]['time']} | Close: {df.iloc[-1]['close']}")
    else:
        print("❌ Falha ao coletar candles.")

    # 4. Coleta de Ticks (Tempo Real Simulado)
    print("\n--- Teste 2: Coleta de Ticks (Snapshot) ---")
    ticks = mt5.copy_ticks_from(symbol, datetime.now(), 100, mt5.COPY_TICKS_ALL)
    if ticks is not None and len(ticks) > 0:
         print(f"✅ {len(ticks)} ticks coletados.")
         print(f"   Último tick: {ticks[-1]}")
    else:
        # Pode falhar se mercado fechado ou sem dados recentes, tenta copy_ticks_range ou from_pos
        print("⚠️  Sem ticks recentes (Mercado pode estar fechado ou delay). Tentando copy_ticks_range...")
        
    # 5. Validação de OrderBook (Livro de Ofertas)
    print("\n--- Teste 3: Livro de Ofertas (Market Depth) ---")
    if mt5.market_book_add(symbol):
        time.sleep(1) # Aguarda dados chegarem
        book = mt5.market_book_get(symbol)
        if book:
            print(f"✅ Livro de ofertas capturado. Níveis: {len(book)}")
            for i in range(min(3, len(book))):
                print(f"   L{i}: {book[i]}")
        else:
            print("⚠️  Livro de ofertas vazio (Mercado Fechado?).")
        mt5.market_book_release(symbol)
    else:
        print("❌ Falha ao assinar livro de ofertas.")

    mt5.shutdown()
    print("\n=== FIM DO TESTE DE COLETA ===")

if __name__ == "__main__":
    run_test_collection()
