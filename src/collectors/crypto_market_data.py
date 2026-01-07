"""
@category: production
@impact: critical
@description: Binance market data collector - WebSocket real-time e REST API histórico
"""
import asyncio
import json
import numpy as np
import logging
from datetime import datetime
import requests
from typing import Optional, Dict
import threading
import websockets
from src.database.db_handler import DatabaseHandler

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BinanceCollector:
    """
    Coletor de dados de Criptomoedas via Binance API (REST + WebSocket).
    Focado em fornecer Snapshots de Order Book compatíveis com a estrutura do projeto.
    """
    
    BASE_URL = "https://api.binance.com/api/v3"
    WS_URL = "wss://stream.binance.com:9443/ws"
    
    def __init__(self):
        self.session = requests.Session()
        self.latest_snapshot = None
        self.running = False
        self.thread = None
        self.loop = None
        self.db = DatabaseHandler()

    def start_stream(self, symbol: str):
        """Inicia a thread de WebSocket para receber dados em tempo real."""
        if self.running:
            return

        self.running = True
        # Normalização do símbolo
        clean_symbol = symbol.lower().replace("-", "").replace("/", "")
        if not clean_symbol.endswith("usdt") and not clean_symbol.endswith("busd") and not clean_symbol.endswith("btc"):
             clean_symbol += "usdt"
        
        self.thread = threading.Thread(target=self._run_websocket, args=(clean_symbol,), daemon=True)
        self.thread.start()
        logging.info(f"WebSocket iniciado para {clean_symbol}")

    def stop_stream(self):
        """Para a thread de WebSocket."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        logging.info("WebSocket parado.")

    def _run_websocket(self, symbol: str):
        """Método interno para rodar o loop asyncio do WebSocket."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._ws_handler(symbol))
        self.loop.close()

    async def _ws_handler(self, symbol: str):
        """Handler assíncrono para conexão WebSocket."""
        # Endpoint para Partial Book Depth (Top 20 levels, 100ms update)
        stream_url = f"{self.WS_URL}/{symbol}@depth20@100ms"
        
        while self.running:
            try:
                async with websockets.connect(stream_url) as ws:
                    logging.info(f"Conectado ao stream: {stream_url}")
                    while self.running:
                        message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        data = json.loads(message)
                        self._process_stream_data(data, symbol)
            except asyncio.TimeoutError:
                continue # Apenas reconecta/continua se não receber dados
            except Exception as e:
                logging.error(f"Erro no WebSocket: {e}")
                await asyncio.sleep(1) # Espera antes de reconectar

    def _process_stream_data(self, data, symbol):
        """Processa a mensagem JSON do WebSocket e atualiza o snapshot local."""
        try:
            bids = np.array(data['bids'], dtype=np.float64)
            asks = np.array(data['asks'], dtype=np.float64)
            ts = datetime.now().timestamp()
            
            self.latest_snapshot = {
                "bids": bids,
                "asks": asks,
                "timestamp": ts
            }
            
            # Persistência Assíncrona (via Queue)
            self.db.insert_snapshot(symbol, bids, asks, ts)
            
        except Exception as e:
            logging.error(f"Erro ao processar dados do stream: {e}")

    def get_orderbook_snapshot(self, symbol: str, depth: int = 20) -> Optional[Dict[str, np.ndarray]]:
        """
        Obtém um snapshot do livro de ofertas.
        Se o WebSocket estiver rodando e tiver dados, retorna o cache local.
        Caso contrário, faz fallback para REST API.
        """
        # Prioridade para dados do WebSocket (menor latência)
        if self.running and self.latest_snapshot:
            return self.latest_snapshot

        # Fallback para REST API
        return self._get_rest_snapshot(symbol, depth)

    def _get_rest_snapshot(self, symbol: str, depth: int = 20) -> Optional[Dict[str, np.ndarray]]:
        """
        Obtém um snapshot do livro de ofertas via REST API (mais simples que WSS para snapshot único).
        Endpoint: GET /api/v3/depth
        """
        # Normalização do Símbolo (Binance usa maiúsculas sem separador, ex: BTCUSDT)
        clean_symbol = symbol.upper().replace("-", "").replace("/", "")
        if not clean_symbol.endswith("USDT") and not clean_symbol.endswith("BUSD") and not clean_symbol.endswith("BTC"):
             # Assume USDT se não especificado
             clean_symbol += "USDT"
             
        url = f"{self.BASE_URL}/depth"
        params = {
            "symbol": clean_symbol,
            "limit": depth
        }
        
        try:
            response = self.session.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse Bids e Asks
                # Binance retorna strings, precisamos converter para float
                bids = np.array(data['bids'], dtype=np.float64)
                asks = np.array(data['asks'], dtype=np.float64)
                
                # Timestamp (Binance manda em ms, converter para segundos)
                # Se não vier lastUpdateId, usamos hora local
                ts = datetime.now().timestamp()
                
                return {
                    "bids": bids,
                    "asks": asks,
                    "timestamp": ts
                }
            else:
                logging.error(f"Erro Binance API {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Erro na conexão com Binance: {e}")
            return None
    
    def get_historical_klines(self, symbol: str, interval: str = "1h", limit: int = 500):
        """
        Obtém dados históricos de candlestick (OHLCV) via REST API.
        Endpoint: GET /api/v3/klines
        
        Args:
            symbol: Par a buscar (ex: BTCUSDT)
            interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d, etc.)
            limit: Quantidade de candles (max 1000)
        
        Returns:
            DataFrame com colunas ['time', 'open', 'high', 'low', 'close', 'volume']
            ou None em caso de erro
        """
        import pandas as pd
        
        # Normalização do símbolo
        clean_symbol = symbol.upper().replace("-", "").replace("/", "")
        if not clean_symbol.endswith("USDT") and not clean_symbol.endswith("BUSD") and not clean_symbol.endswith("BTC"):
            clean_symbol += "USDT"
        
        url = f"{self.BASE_URL}/klines"
        params = {
            "symbol": clean_symbol,
            "interval": interval,
            "limit": min(limit, 1000)  # Binance limit
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Binance retorna: [timestamp, open, high, low, close, volume, close_time, ...]
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])
                
                # Seleciona e formata colunas necessárias
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
                
                # Converte timestamp (ms) para Unix timestamp (s - inteiro)
                df['time'] = (df['timestamp'].astype('int64') // 1000).astype(int)
                
                # Converte preços e volume para float
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                
                # Remove coluna timestamp original e reordena
                df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
                
                logging.info(f"Obtidos {len(df)} candles de {clean_symbol} ({interval})")
                return df
            else:
                logging.error(f"Erro Binance Klines API {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Erro ao buscar klines: {e}")
            return None


if __name__ == "__main__":
    # Teste rápido
    collector = BinanceCollector()
    sym = "BTCUSDT"
    print(f"Testando coleta para {sym}...")
    
    snapshot = collector.get_orderbook_snapshot(sym)
    if snapshot:
        print(f"Snapshot recebido!")
        print(f"Top Bid: {snapshot['bids'][0]}")
        print(f"Top Ask: {snapshot['asks'][0]}")
        print(f"Spread: {snapshot['asks'][0][0] - snapshot['bids'][0][0]:.2f}")
    else:
        print("Falha ao obter snapshot.")
