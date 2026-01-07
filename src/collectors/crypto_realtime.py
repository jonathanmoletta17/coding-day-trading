"""
@category: production
@impact: moderate
@description: Real-time streaming de candlesticks via Binance WebSocket API
"""
import asyncio
import json
import logging
import threading
import websockets
from typing import Optional, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceKlineStream:
    """
    Stream real-time de candlesticks via Binance WebSocket API.
    Mantém último candle em formação atualizado em tempo real.
    
    Example:
        >>> stream = BinanceKlineStream()
        >>> stream.start("BTCUSDT", "1m")
        >>> latest = stream.get_latest_kline()
        >>> print(latest)
        {'time': 1767520000, 'open': 91500.0, 'high': 91550.0, ...}
    """
    
    def __init__(self):
        self.latest_kline: Optional[Dict] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
    def start(self, symbol: str, interval: str = "1m"):
        """
        Inicia stream em thread separada
        
        Args:
            symbol: Par de trading (ex: BTCUSDT, ETHUSDT)
            interval: Timeframe (1m, 5m, 15m, 1h, etc)
        """
        if self.running:
            logger.warning("Stream já está rodando")
            return
            
        self.running = True
        self.thread = threading.Thread(
            target=self._run_event_loop,
            args=(symbol, interval),
            daemon=True
        )
        self.thread.start()
        logger.info(f"🟢 Stream iniciado: {symbol} @ {interval}")
        
    def stop(self):
        """Para o stream WebSocket"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("🔴 Stream parado")
        
    def get_latest_kline(self) -> Optional[Dict]:
        """
        Retorna último candle recebido do WebSocket
        
        Returns:
            Dict com keys: time, open, high, low, close, volume, is_closed
            None se ainda não recebeu nenhum dado
        """
        return self.latest_kline
        
    def is_running(self) -> bool:
        """Verifica se stream está ativo"""
        return self.running
        
    def _run_event_loop(self, symbol: str, interval: str):
        """Roda asyncio event loop em thread dedicada"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._ws_handler(symbol, interval))
        except Exception as e:
            logger.error(f"Erro fatal no event loop: {e}")
        finally:
            self.loop.close()
            
    async def _ws_handler(self, symbol: str, interval: str):
        """Handler WebSocket assíncrono"""
        # Normaliza símbolo (remove - e / e adiciona usdt se necessário)
        clean_symbol = symbol.lower().replace("-", "").replace("/", "")
        if not clean_symbol.endswith("usdt") and not clean_symbol.endswith("busd"):
            clean_symbol += "usdt"
            
        # URL WebSocket: wss://stream.binance.com:9443/ws/<symbol>@kline_<interval>
        url = f"wss://stream.binance.com:9443/ws/{clean_symbol}@kline_{interval}"
        
        while self.running:
            try:
                async with websockets.connect(url) as ws:
                    logger.info(f"📡 Conectado ao WebSocket: {url}")
                    
                    while self.running:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            data = json.loads(message)
                            self._process_kline(data)
                        except asyncio.TimeoutError:
                            # Timeout normal, apenas continua
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("Conexão WebSocket fechada, reconectando...")
                            break
                            
            except Exception as e:
                logger.error(f"Erro no WebSocket: {e}")
                if self.running:
                    await asyncio.sleep(2)  # Espera antes de reconectar
                    
    def _process_kline(self, data: dict):
        """
        Processa mensagem de kline do WebSocket
        
        Args:
            data: JSON recebido do Binance WebSocket
        """
        try:
            k = data['k']
            self.latest_kline = {
                'time': int(k['t']) // 1000,  # Converte ms para segundos (Unix timestamp)
                'open': float(k['o']),
                'high': float(k['h']),
                'low': float(k['l']),
                'close': float(k['c']),
                'volume': float(k['v']),
                'is_closed': k['x']  # True se candle fechou completamente
            }
            
            # Log apenas quando candle fecha (menos verboso)
            if self.latest_kline['is_closed']:
                logger.info(
                    f"✅ Candle fechado @ {datetime.fromtimestamp(self.latest_kline['time'])}: "
                    f"O:{self.latest_kline['open']:.2f} C:{self.latest_kline['close']:.2f} "
                    f"V:{self.latest_kline['volume']:.2f}"
                )
                
        except KeyError as e:
            logger.error(f"Formato de mensagem inválido (faltando key {e}): {data}")
        except Exception as e:
            logger.error(f"Erro ao processar kline: {e}")


if __name__ == "__main__":
    # Teste standalone
    import time
    
    stream = BinanceKlineStream()
    stream.start("BTCUSDT", "1m")
    
    print("Streaming por 30 segundos...")
    for i in range(30):
        time.sleep(1)
        latest = stream.get_latest_kline()
        if latest:
            print(f"[{i+1}s] Close: {latest['close']:.2f} | Volume: {latest['volume']:.2f}")
    
    stream.stop()
    print("Stream finalizado")
