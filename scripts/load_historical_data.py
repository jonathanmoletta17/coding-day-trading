#!/usr/bin/env python3
"""
Script automatizado para carga histórica inicial
Coleta dados de múltiplos símbolos e timeframes
"""

import asyncio
import httpx
from sqlalchemy import create_engine, text
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Configuração
BRIDGE_URL = os.getenv("MT5_BRIDGE_URL", "http://172.17.96.1:8000")
DB_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

engine = create_engine(DB_URL)

# Símbolos e timeframes para coletar
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
TIMEFRAMES = {
    "M1": 1440,   # 1 dia
    "M5": 2016,   # 1 semana
    "M15": 1344,  # 2 semanas
    "M30": 720,   # 15 dias
    "H1": 720,    # 30 dias
    "H4": 500,    # ~83 dias
    "D1": 365,    # 1 ano
}

async def get_or_create_symbol(symbol: str) -> int:
    """Obtém ou cria símbolo no banco"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT get_or_create_symbol(:symbol)"),
            {"symbol": symbol}
        )
        conn.commit()
        return result.scalar()

async def collect_candles(client: httpx.AsyncClient, symbol: str, timeframe: str, count: int):
    """Coleta candles e insere no banco"""
    try:
        # Obter dados do MT5
        response = await client.get(
            f"{BRIDGE_URL}/candles/{symbol}",
            params={"timeframe": timeframe, "count": count}
        )
        
        if response.status_code != 200:
            print(f"  [ERRO] {symbol} {timeframe}: HTTP {response.status_code}")
            return 0
        
        candles = response.json()
        
        if not candles:
            print(f"  [WARN] {symbol} {timeframe}: Sem dados")
            return 0
        
        # Inserir no banco
        symbol_id = await get_or_create_symbol(symbol)
        
        inserted = 0
        with engine.connect() as conn:
            for candle in candles:
                try:
                    conn.execute(
                        text("""
                            INSERT INTO candles (symbol_id, timeframe, time, open, high, low, close, tick_volume, spread, real_volume)
                            VALUES (:symbol_id, :timeframe, :time, :open, :high, :low, :close, :tick_volume, :spread, :real_volume)
                            ON CONFLICT (symbol_id, timeframe, time) DO NOTHING
                        """),
                        {
                            "symbol_id": symbol_id,
                            "timeframe": timeframe,
                            "time": candle['time'],
                            "open": candle['open'],
                            "high": candle['high'],
                            "low": candle['low'],
                            "close": candle['close'],
                            "tick_volume": candle['tick_volume'],
                            "spread": candle.get('spread', 0),
                            "real_volume": candle.get('real_volume', 0)
                        }
                    )
                    inserted += 1
                except Exception as e:
                    pass  # Ignora duplicatas
            
            conn.commit()
        
        print(f"  ✓ {symbol} {timeframe}: {inserted}/{len(candles)} candles inseridos")
        return inserted
        
    except Exception as e:
        print(f"  [ERRO] {symbol} {timeframe}: {e}")
        return 0

async def main():
    print("=" * 70)
    print("CARGA HISTÓRICA INICIAL - MT5 DATA")
    print("=" * 70)
    print(f"\nInício: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nSímbos: {', '.join(SYMBOLS)}")
    print(f"Timeframes: {', '.join(TIMEFRAMES.keys())}")
    print(f"Total de combinações: {len(SYMBOLS) * len(TIMEFRAMES)}")
    print("\n" + "=" * 70)
    
    total_inserted = 0
    total_requests = 0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for symbol in SYMBOLS:
            print(f"\n📊 Coletando {symbol}...")
            
            for timeframe, count in TIMEFRAMES.items():
                total_requests += 1
                inserted = await collect_candles(client, symbol, timeframe, count)
                total_inserted += inserted
                await asyncio.sleep(0.2)  # Rate limiting
    
    print("\n" + "=" * 70)
    print("CARGA COMPLETA!")
    print("=" * 70)
    print(f"\nFim: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total de requisições: {total_requests}")
    print(f"Total de candles inseridos: {total_inserted:,}")
    
    # Estatísticas finais
    print("\n" + "=" * 70)
    print("ESTATÍSTICAS DO BANCO")
    print("=" * 70)
    
    with engine.connect() as conn:
        # Total por símbolo
        result = conn.execute(text("""
            SELECT s.symbol, COUNT(c.id) as total
            FROM symbols s
            LEFT JOIN candles c ON s.id = c.symbol_id
            GROUP BY s.symbol
            ORDER BY total DESC
        """))
        
        print("\nCandles por símbolo:")
        for row in result:
            print(f"  {row[0]}: {row[1]:,}")
        
        # Total por timeframe
        result = conn.execute(text("""
            SELECT timeframe, COUNT(*) as total
            FROM candles
            GROUP BY timeframe
            ORDER BY 
                CASE timeframe
                    WHEN 'M1' THEN 1
                    WHEN 'M5' THEN 2
                    WHEN 'M15' THEN 3
                    WHEN 'M30' THEN 4
                    WHEN 'H1' THEN 5
                    WHEN 'H4' THEN 6
                    WHEN 'D1' THEN 7
                END
        """))
        
        print("\nCandles por timeframe:")
        for row in result:
            print(f"  {row[0]}: {row[1]:,}")
    
    print("\n✅ Sistema pronto para análises e estratégias!")

if __name__ == "__main__":
    asyncio.run(main())
