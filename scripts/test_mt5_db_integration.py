import sys
import os
import time
import logging
import numpy as np
from datetime import datetime

# Adiciona diretório raiz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.collectors.mt5_market_data import MT5MarketCollector
from src.database.db_handler import DatabaseHandler

# Configurar Log
logging.basicConfig(level=logging.INFO)

def test_mt5_integration():
    print("=== Teste de Integração MT5 -> TimescaleDB ===")
    
    # 1. Inicializar Coletor
    print("[1/3] Inicializando Coletor MT5...")
    try:
        collector = MT5MarketCollector()
        if not collector.connected:
            print("AVISO: MT5 não conectado. O teste tentará usar dados mockados ou falhará se MT5 for obrigatório.")
            # Em ambiente de teste noturno, podemos não ter conexão. 
            # Se falhar aqui, não conseguimos testar a inserção real vinda do MT5.
            # Mas podemos testar a inserção direta no DBHandler simulando o collector.
    except Exception as e:
        print(f"Erro ao init collector: {e}")
        return

    # 2. Simular Coleta (já que B3 está fechada)
    # Se o MT5 estiver aberto, ele pode retornar snapshot vazio ou último estado.
    # Vamos tentar pegar dados de um ativo comum.
    symbol = "PETR4"
    print(f"[2/3] Tentando obter snapshot de {symbol}...")
    
    # Nota: Se o mercado estiver fechado, get_orderbook_snapshot pode retornar None ou arrays vazios.
    # Se retornar None, vamos forçar uma inserção manual para validar o DB.
    snapshot = collector.get_orderbook_snapshot(symbol)
    
    if snapshot:
        print(f"Snapshot obtido via MT5! Bids: {len(snapshot['bids'])}, Asks: {len(snapshot['asks'])}")
    else:
        print("MT5 não retornou dados (Mercado Fechado?). Simulando dados para teste de DB...")
        # Simula dados
        bids = np.array([[30.00, 100], [29.99, 500]], dtype=np.float64)
        asks = np.array([[30.01, 200], [30.02, 300]], dtype=np.float64)
        ts = datetime.now().timestamp()
        
        # Inserção manual via DB Handler (bypassando collector se ele falhou)
        collector.db.insert_snapshot(symbol, bids, asks, ts)
        print("Dados simulados enviados para fila do DB.")

    # 3. Aguardar Persistência
    print("[3/3] Aguardando Worker do DB processar...")
    time.sleep(5) # Espera worker thread processar a fila
    
    collector.disconnect()
    # collector.db.close() # DBHandler é Singleton e roda em daemon, mas podemos fechar se quiser
    
    print("Teste finalizado. Verifique os logs ou o banco de dados.")

if __name__ == "__main__":
    test_mt5_integration()
