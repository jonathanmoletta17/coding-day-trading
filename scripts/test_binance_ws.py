import time
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.collectors.crypto_market_data import BinanceCollector

def test_binance_ws():
    print("Iniciando teste do Binance WebSocket...")
    collector = BinanceCollector()
    symbol = "BTCUSDT"
    
    print(f"Iniciando stream para {symbol}...")
    collector.start_stream(symbol)
    
    # Wait for connection
    time.sleep(2)
    
    print("Coletando dados por 10 segundos...")
    for i in range(10):
        snapshot = collector.get_orderbook_snapshot(symbol)
        if snapshot:
            best_bid = snapshot['bids'][0][0]
            best_ask = snapshot['asks'][0][0]
            spread = best_ask - best_bid
            print(f"[{i+1}/10] Bid: {best_bid:.2f} | Ask: {best_ask:.2f} | Spread: {spread:.2f}")
        else:
            print(f"[{i+1}/10] Aguardando dados...")
        time.sleep(1)
        
    print("Parando stream...")
    collector.stop_stream()
    print("Teste concluído.")

if __name__ == "__main__":
    test_binance_ws()
