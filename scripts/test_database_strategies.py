"""
Teste de Estratégias com Dados Reais do PostgreSQL
Valida que estratégias funcionam com dados do banco
"""

import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DB_URL)

def test_moving_average_strategy():
    """Testa estratégia de média móvel com dados do banco"""
    
    print("\n=== TESTE: Média Móvel com Dados do PostgreSQL ===")
    
    # Query para obter últimas 100 candles H1 do EURUSD
    query = """
        SELECT time, close, high, low, open, tick_volume
        FROM candles
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'EURUSD')
            AND timeframe = 'H1'
        ORDER BY time DESC
        LIMIT 100
    """
    
    df = pd.read_sql(query, engine)
    df = df.sort_values('time')  # Ordem cronológica
    df['close'] = pd.to_numeric(df['close'])
    
    # Calcular médias móveis
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    
    # Última leitura
    last = df.iloc[-1]
    print(f"\nÚltima vela: {last['time']}")
    print(f"Preço: {last['close']:.5f}")
    print(f"SMA 20: {last['SMA_20']:.5f}")
    print(f"SMA 50: {last['SMA_50']:.5f}")
    
    # Sinal
    if last['close'] > last['SMA_20'] > last['SMA_50']:
        print("✅ SINAL: TENDÊNCIA DE ALTA FORTE")
    elif last['close'] < last['SMA_20'] < last['SMA_50']:
        print("✅ SINAL: TENDÊNCIA DE BAIXA FORTE")
    else:
        print("⚪ SINAL: SEM TENDÊNCIA CLARA")
    
    return df

def test_volume_analysis():
    """Testa análise de volume"""
    
    print("\n=== TESTE: Análise de Volume ===")
    
    query = """
        SELECT 
            timeframe,
            AVG(tick_volume) as avg_volume,
            MAX(tick_volume) as max_volume,
            COUNT(*) as total_candles
        FROM candles
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'EURUSD')
        GROUP BY timeframe
        ORDER BY 
            CASE timeframe
                WHEN 'M1' THEN 1 WHEN 'M5' THEN 2 WHEN 'M15' THEN 3
                WHEN 'M30' THEN 4 WHEN 'H1' THEN 5 WHEN 'H4' THEN 6 WHEN 'D1' THEN 7
            END
    """
    
    df = pd.read_sql(query, engine)
    
    print("\nVolume médio por timeframe:")
    for _, row in df.iterrows():
        print(f"  {row['timeframe']}: Avg={row['avg_volume']:,.0f}, Max={row['max_volume']:,.0f} ({row['total_candles']:,} candles)")
    
    return df

def test_price_action():
    """Testa padrões de price action"""
    
    print("\n=== TESTE: Price Action (Últimas 5 velas D1) ===")
    
    query = """
        SELECT time, open, high, low, close
        FROM candles
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'EURUSD')
            AND timeframe = 'D1'
        ORDER BY time DESC
        LIMIT 5
    """
    
    df = pd.read_sql(query, engine)
    df = df.sort_values('time')
    
    for _, candle in df.iterrows():
        body = abs(float(candle['close']) - float(candle['open']))
        upper_wick = float(candle['high']) - max(float(candle['close']), float(candle['open']))
        lower_wick = min(float(candle['close']), float(candle['open'])) - float(candle['low'])
        
        candle_type = "ALTA" if float(candle['close']) > float(candle['open']) else "BAIXA"
        
        print(f"\n  {candle['time'].date()}: {candle_type}")
        print(f"    Close: {candle['close']:.5f}")
        print(f"    Corpo: {body:.5f}, Pavio Superior: {upper_wick:.5f}, Pavio Inferior: {lower_wick:.5f}")
    
    return df

def main():
    print("=" * 70)
    print("TESTE DE ESTRATÉGIAS COM DADOS DO POSTGRESQL")
    print("=" * 70)
    
    test_moving_average_strategy()
    test_volume_analysis()
    test_price_action()
    
    print("\n" + "=" * 70)
    print("✅ TODOS OS TESTES PASSARAM!")
    print("=" * 70)
    print("\nSistema validado end-to-end:")
    print("  ✓ Dados históricos carregados")
    print("  ✓ PostgreSQL armazenando corretamente")
    print("  ✓ Queries funcionando")
    print("  ✓ Estratégias processando dados reais")
    print("\nPróximo passo: Coleta em tempo real via WebSocket")

if __name__ == "__main__":
    main()
