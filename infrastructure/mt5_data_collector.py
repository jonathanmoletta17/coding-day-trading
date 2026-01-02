"""
@category: infrastructure
@impact: critical
@description: Serviço de coleta contínua de dados MT5
"""

"""
MT5 Data Collector - Coleta dados do MT5 via Bridge API e armazena no PostgreSQL
Roda no WSL/Linux e se comunica com o MT5 Bridge Service no Windows
"""

import asyncio
import httpx
import websockets
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import logging
from typing import List, Dict, Any

# Configuração de logging<
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================

class Config:
    # MT5 Bridge API
    MT5_BRIDGE_URL = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
    MT5_BRIDGE_WS = os.getenv("MT5_BRIDGE_WS", "ws://localhost:8000/ws/ticks")
    
    # PostgreSQL
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "55432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "market_data")
    
    @property
    def DATABASE_URL(self):
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Símbolos para coletar
    SYMBOLS_TO_COLLECT = os.getenv("SYMBOLS_TO_COLLECT", "EURUSD,GBPUSD,USDJPY,XAUUSD").split(",")
    
    # Timeframes para histórico
    TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    
    # Intervalo de coleta (segundos)
    TICK_COLLECT_INTERVAL = int(os.getenv("TICK_COLLECT_INTERVAL", "1"))
    CANDLE_COLLECT_INTERVAL = int(os.getenv("CANDLE_COLLECT_INTERVAL", "60"))

config = Config()

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

engine = create_engine(config.DATABASE_URL)
Session = sessionmaker(bind=engine)

def get_or_create_symbol(session, symbol: str) -> int:
    """Obtém ou cria um símbolo no banco"""
    result = session.execute(
        text("SELECT get_or_create_symbol(:symbol)"),
        {"symbol": symbol}
    )
    return result.scalar()

def insert_tick(session, symbol_id: int, tick_data: Dict[str, Any]):
    """Insere um tick no banco"""
    session.execute(
        text("""
            INSERT INTO ticks (symbol_id, time, bid, ask, last, volume, flags)
            VALUES (:symbol_id, :time, :bid, :ask, :last, :volume, :flags)
        """),
        {
            "symbol_id": symbol_id,
            "time": tick_data['time'],
            "bid": tick_data['bid'],
            "ask": tick_data['ask'],
            "last": tick_data.get('last', 0),
            "volume": tick_data.get('volume', 0),
            "flags": tick_data.get('flags', 0)
        }
    )

def insert_candle(session, symbol_id: int, timeframe: str, candle_data: Dict[str, Any]):
    """Insere uma candle no banco (ON CONFLICT DO NOTHING para evitar duplicatas)"""
    session.execute(
        text("""
            INSERT INTO candles (symbol_id, timeframe, time, open, high, low, close, tick_volume, spread, real_volume)
            VALUES (:symbol_id, :timeframe, :time, :open, :high, :low, :close, :tick_volume, :spread, :real_volume)
            ON CONFLICT (symbol_id, timeframe, time) DO NOTHING
        """),
        {
            "symbol_id": symbol_id,
            "timeframe": timeframe,
            "time": candle_data['time'],
            "open": candle_data['open'],
            "high": candle_data['high'],
            "low": candle_data['low'],
            "close": candle_data['close'],
            "tick_volume": candle_data['tick_volume'],
            "spread": candle_data.get('spread', 0),
            "real_volume": candle_data.get('real_volume', 0)
        }
    )

# =============================================================================
# MT5 BRIDGE API CLIENT
# =============================================================================

class MT5BridgeClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def health_check(self) -> Dict:
        """Verifica se API está online"""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    async def get_account_info(self) -> Dict:
        """Obtém informações da conta"""
        response = await self.client.get(f"{self.base_url}/account")
        response.raise_for_status()
        return response.json()
    
    async def get_tick(self, symbol: str) -> Dict:
        """Obtém último tick de um símbolo"""
        response = await self.client.get(f"{self.base_url}/tick/{symbol}")
        response.raise_for_status()
        return response.json()
    
    async def get_candles(self, symbol: str, timeframe: str = "H1", count: int = 100) -> List[Dict]:
        """Obtém candles históricos"""
        response = await self.client.get(
            f"{self.base_url}/candles/{symbol}",
            params={"timeframe": timeframe, "count": count}
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Fecha conexão HTTP"""
        await self.client.aclose()

# =============================================================================
# DATA COLLECTORS
# =============================================================================

async def collect_tick_data(client: MT5BridgeClient, symbol: str):
    """Coleta tick de um símbolo e armazena no banco"""
    try:
        tick = await client.get_tick(symbol)
        
        with Session() as session:
            symbol_id = get_or_create_symbol(session, symbol)
            insert_tick(session, symbol_id, tick)
            session.commit()
            
        logger.debug(f"[TICK] {symbol}: Bid={tick['bid']}, Ask={tick['ask']}")
        
    except Exception as e:
        logger.error(f"Erro ao coletar tick de {symbol}: {e}")

async def collect_historical_candles(client: MT5BridgeClient, symbol: str, timeframe: str, count: int = 1000):
    """Coleta candles históricas e armazena no banco"""
    try:
        candles = await client.get_candles(symbol, timeframe, count)
        
        with Session() as session:
            symbol_id = get_or_create_symbol(session, symbol)
            
            for candle in candles:
                insert_candle(session, symbol_id, timeframe, candle)
            
            session.commit()
            
        logger.info(f"[CANDLES] {symbol} {timeframe}: {len(candles)} velas coletadas")
        
    except Exception as e:
        logger.error(f"Erro ao coletar candles de {symbol} {timeframe}: {e}")

async def continuous_tick_collector():
    """Coletor contínuo de ticks"""
    client = MT5BridgeClient(config.MT5_BRIDGE_URL)
    
    logger.info(f"Iniciando coleta de ticks para: {', '.join(config.SYMBOLS_TO_COLLECT)}")
    
    try:
        while True:
            tasks = [
                collect_tick_data(client, symbol)
                for symbol in config.SYMBOLS_TO_COLLECT
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(config.TICK_COLLECT_INTERVAL)
            
    except Exception as e:
        logger.error(f"Erro no coletor de ticks: {e}")
    finally:
        await client.close()

async def continuous_candle_collector():
    """Coletor contínuo de candles (atualiza a cada minuto)"""
    client = MT5BridgeClient(config.MT5_BRIDGE_URL)
    
    logger.info(f"Iniciando coleta de candles para: {', '.join(config.SYMBOLS_TO_COLLECT)}")
    
    try:
        while True:
            for symbol in config.SYMBOLS_TO_COLLECT:
                for timeframe in config.TIMEFRAMES:
                    # Coleta apenas as últimas 10 velas para atualização
                    await collect_historical_candles(client, symbol, timeframe, count=10)
            
            await asyncio.sleep(config.CANDLE_COLLECT_INTERVAL)
            
    except Exception as e:
        logger.error(f"Erro no coletor de candles: {e}")
    finally:
        await client.close()

async def websocket_tick_collector():
    """Coletor via WebSocket (mais eficiente para tempo real)"""
    logger.info(f"Conectando ao WebSocket: {config.MT5_BRIDGE_WS}")
    
    try:
        async with websockets.connect(config.MT5_BRIDGE_WS) as websocket:
            # Subscreve aos símbolos
            for symbol in config.SYMBOLS_TO_COLLECT:
                await websocket.send(json.dumps({
                    "action": "subscribe",
                    "symbol": symbol
                }))
                logger.info(f"Subscrito ao símbolo: {symbol}")
            
            # Recebe e processa ticks
            async for message in websocket:
                data = json.loads(message)
                
                if data.get('type') == 'tick':
                    symbol = data['symbol']
                    
                    with Session() as session:
                        symbol_id = get_or_create_symbol(session, symbol)
                        insert_tick(session, symbol_id, {
                            'time': data['time'],
                            'bid': data['bid'],
                            'ask': data['ask'],
                            'last': data.get('last', 0),
                            'volume': data.get('volume', 0),
                            'flags': 0
                        })
                        session.commit()
                    
                    logger.debug(f"[WS TICK] {symbol}: Bid={data['bid']}, Ask={data['ask']}")
                
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")

# =============================================================================
# INITIAL DATA LOAD
# =============================================================================

async def initial_historical_load():
    """Carrega dados históricos iniciais (executar uma vez no início)"""
    client = MT5BridgeClient(config.MT5_BRIDGE_URL)
    
    logger.info("=" * 70)
    logger.info("CARGA INICIAL DE DADOS HISTÓRICOS")
    logger.info("=" * 70)
    
    try:
        # Verifica conexão
        health = await client.health_check()
        logger.info(f"MT5 Bridge Status: {health['status']}")
        
        # Coleta dados históricos
        for symbol in config.SYMBOLS_TO_COLLECT:
            logger.info(f"\nColetando histórico de {symbol}...")
            
            for timeframe in config.TIMEFRAMES:
                # Determina quantidade baseada no timeframe
                count_map = {
                    "M1": 1440,   # 1 dia
                    "M5": 2016,   # 1 semana
                    "M15": 672,   # 1 semana
                    "M30": 720,   # 15 dias
                    "H1": 720,    # 30 dias
                    "H4": 500,    # ~80 dias
                    "D1": 365,    # 1 ano
                }
                
                count = count_map.get(timeframe, 100)
                
                await collect_historical_candles(client, symbol, timeframe, count)
                await asyncio.sleep(0.5)  # Evita sobrecarregar API
        
        logger.info("\n" + "=" * 70)
        logger.info("CARGA INICIAL CONCLUÍDA")
        logger.info("=" * 70)
        
    finally:
        await client.close()

# =============================================================================
# STATISTICS
# =============================================================================

async def print_statistics():
    """Imprime estatísticas do banco de dados"""
    with Session() as session:
        # Total de símbolos
        result = session.execute(text("SELECT COUNT(*) FROM symbols"))
        total_symbols = result.scalar()
        
        # Total de ticks
        result = session.execute(text("SELECT COUNT(*) FROM ticks"))
        total_ticks = result.scalar()
        
        # Total de candles
        result = session.execute(text("SELECT COUNT(*) FROM candles"))
        total_candles = result.scalar()
        
        # Último tick por símbolo
        result = session.execute(text("""
            SELECT s.symbol, MAX(t.time) as last_tick
            FROM symbols s
            LEFT JOIN ticks t ON s.id = t.symbol_id
            GROUP BY s.symbol
            ORDER BY s.symbol
        """))
        
        logger.info("\n" + "=" * 70)
        logger.info("ESTATÍSTICAS DO BANCO DE DADOS")
        logger.info("=" * 70)
        logger.info(f"Total de símbolos: {total_symbols}")
        logger.info(f"Total de ticks: {total_ticks:,}")
        logger.info(f"Total de candles: {total_candles:,}")
        logger.info("\nÚltimos ticks por símbolo:")
        
        for row in result:
            logger.info(f"  {row[0]}: {row[1]}")

# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Função principal do collector"""
    logger.info("=" * 70)
    logger.info("MT5 DATA COLLECTOR - Iniciando...")
    logger.info("=" * 70)
    
    # Verifica conexão com banco
    try:
        with Session() as session:
            session.execute(text("SELECT 1"))
        logger.info("[✓] Conexão com PostgreSQL estabelecida")
    except Exception as e:
        logger.error(f"[✗] Falha na conexão com PostgreSQL: {e}")
        return
    
    # Verifica conexão com MT5 Bridge
    try:
        client = MT5BridgeClient(config.MT5_BRIDGE_URL)
        health = await client.health_check()
        logger.info(f"[✓] MT5 Bridge API: {health['status']}")
        await client.close()
    except Exception as e:
        logger.error(f"[✗] MT5 Bridge API não está acessível: {e}")
        logger.error(f"[!] Certifique-se de que mt5_bridge_service.py está rodando no Windows")
        return
    
    # Menu de opções
    print("\n" + "=" * 70)
    print("OPÇÕES:")
    print("  1. Carga inicial de dados históricos (executar uma vez)")
    print("  2. Iniciar coleta contínua de ticks (HTTP polling)")
    print("  3. Iniciar coleta contínua via WebSocket (recomendado)")
    print("  4. Iniciar coleta de candles")
    print("  5. Todos (histórico + tempo real)")
    print("  6. Mostrar estatísticas")
    print("=" * 70)
    
    choice = input("\nEscolha uma opção (1-6): ").strip()
    
    if choice == "1":
        await initial_historical_load()
        await print_statistics()
    
    elif choice == "2":
        await continuous_tick_collector()
    
    elif choice == "3":
        await websocket_tick_collector()
    
    elif choice == "4":
        await continuous_candle_collector()
    
    elif choice == "5":
        # Executa tudo em paralelo
        await initial_historical_load()
        
        tasks = [
            websocket_tick_collector(),
            continuous_candle_collector()
        ]
        
        await asyncio.gather(*tasks)
    
    elif choice == " 6":
        await print_statistics()
    
    else:
        logger.error("Opção inválida!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[!] Coletor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"\n[✗] Erro fatal: {e}")
        import traceback
        traceback.print_exc()
