"""
Detector de Liquidity Sweep + Displacement (SMC Pattern)

Conceito:
1. Liquidity Sweep: Preço toca/rompe high/low de N candles anteriores
2. Displacement: Retorno rápido (>X%) na direção oposta em Y candles

Objetivo: Identificar quando mercado está ATIVO (padrão presente) vs INATIVO
NÃO prevê direção, NÃO executa trades, NÃO otimiza parâmetros
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DB_URL)

# =============================================================================
# PARÂMETROS FIXOS (não otimizar)
# =============================================================================

LOOKBACK_CANDLES = 20        # Quantos candles olhar para trás para encontrar high/low
DISPLACEMENT_THRESHOLD = 0.3  # % mínimo de movimento para considerar displacement (em relação ao range)
DISPLACEMENT_CANDLES = 5      # Quantos candles para displacement acontecer
MIN_SWEEP_PENETRATION = 0.02  # % mínimo de penetração do high/low (2 pips)

# =============================================================================
# FUNÇÕES DE DETECÇÃO
# =============================================================================

def detect_liquidity_sweeps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta liquidity sweeps (varreduras de liquidez)
    
    Critérios objetivos:
    1. High atual > high dos últimos N candles (sweep de compra)
    2. Low atual < low dos últimos N candles (sweep de venda)
    3. Penetração mínima de X%
    """
    
    # Calcular rolling high/low
    df['rolling_high'] = df['high'].shift(1).rolling(window=LOOKBACK_CANDLES).max()
    df['rolling_low'] = df['low'].shift(1).rolling(window=LOOKBACK_CANDLES).min()
    
    # Detectar sweeps
    # Buy-side sweep: preço rompe acima do high anterior
    df['sweep_high'] = (df['high'] > df['rolling_high']) & \
                       ((df['high'] - df['rolling_high']) / df['rolling_high'] >= MIN_SWEEP_PENETRATION/100)
    
    # Sell-side sweep: preço rompe abaixo do low anterior
    df['sweep_low'] = (df['low'] < df['rolling_low']) & \
                      ((df['rolling_low'] - df['low']) / df['rolling_low'] >= MIN_SWEEP_PENETRATION/100)
    
    return df

def detect_displacement(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta displacement após sweep
    
    Critérios objetivos:
    1. Após sweep high: preço cai X% em Y candles
    2. Após sweep low: preço sobe X% em Y candles
    """
    
    df['displacement_down'] = False
    df['displacement_up'] = False
    df['pattern_bullish'] = False  # Sweep low + displacement up
    df['pattern_bearish'] = False  # Sweep high + displacement down
    
    for i in range(LOOKBACK_CANDLES + DISPLACEMENT_CANDLES, len(df)):
        
        # Verifica se houve sweep high
        if df.iloc[i - DISPLACEMENT_CANDLES]['sweep_high']:
            # Calcula movimento nos próximos candles
            sweep_high = df.iloc[i - DISPLACEMENT_CANDLES]['high']
            recent_low = df.iloc[i - DISPLACEMENT_CANDLES:i]['low'].min()
            
            # Range do sweep
            sweep_range = sweep_high - df.iloc[i - DISPLACEMENT_CANDLES]['low']
            
            # Displacement como % do range
            if sweep_range > 0:
                displacement_pct = (sweep_high - recent_low) / sweep_range
                
                if displacement_pct >= DISPLACEMENT_THRESHOLD:
                    df.iloc[i, df.columns.get_loc('displacement_down')] = True
                    df.iloc[i, df.columns.get_loc('pattern_bearish')] = True
        
        # Verifica se houve sweep low
        if df.iloc[i - DISPLACEMENT_CANDLES]['sweep_low']:
            # Calcula movimento nos próximos candles
            sweep_low = df.iloc[i - DISPLACEMENT_CANDLES]['low']
            recent_high = df.iloc[i - DISPLACEMENT_CANDLES:i]['high'].max()
            
            # Range do sweep
            sweep_range = df.iloc[i - DISPLACEMENT_CANDLES]['high'] - sweep_low
            
            # Displacement como % do range
            if sweep_range > 0:
                displacement_pct = (recent_high - sweep_low) / sweep_range
                
                if displacement_pct >= DISPLACEMENT_THRESHOLD:
                    df.iloc[i, df.columns.get_loc('displacement_up')] = True
                    df.iloc[i, df.columns.get_loc('pattern_bullish')] = True
    
    return df

# =============================================================================
# ANÁLISE E ESTATÍSTICAS
# =============================================================================

def analyze_pattern(symbol: str, timeframe: str):
    """
    Analisa ocorrências do padrão para um símbolo/timeframe
    """
    
    print(f"\n{'='*70}")
    print(f"ANÁLISE: {symbol} - {timeframe}")
    print(f"{'='*70}")
    
    # Carregar dados do PostgreSQL
    query = f"""
        SELECT time, open, high, low, close, tick_volume
        FROM candles
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = '{symbol}')
            AND timeframe = '{timeframe}'
        ORDER BY time ASC
    """
    
    df = pd.read_sql(query, engine)
    
    if len(df) < LOOKBACK_CANDLES + DISPLACEMENT_CANDLES + 10:
        print(f"❌ Dados insuficientes ({len(df)} candles)")
        return None
    
    print(f"\n📊 Dataset: {len(df)} candles")
    print(f"   Início: {df['time'].min()}")
    print(f"   Fim: {df['time'].max()}")
    
    # Converter para numérico
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col])
    
    # Detectar padrões
    df = detect_liquidity_sweeps(df)
    df = detect_displacement(df)
    
    # Estatísticas
    total_sweeps_high = df['sweep_high'].sum()
    total_sweeps_low = df['sweep_low'].sum()
    total_patterns_bullish = df['pattern_bullish'].sum()
    total_patterns_bearish = df['pattern_bearish'].sum()
    
    print(f"\n📈 VARREDURAS DE LIQUIDEZ:")
    print(f"   Sweeps High (buy-side): {total_sweeps_high}")
    print(f"   Sweeps Low (sell-side): {total_sweeps_low}")
    print(f"   Total: {total_sweeps_high + total_sweeps_low}")
    
    print(f"\n🎯 PADRÕES COMPLETOS (Sweep + Displacement):")
    print(f"   Padrões BULLISH (sweep low → displacement up): {total_patterns_bullish}")
    print(f"   Padrões BEARISH (sweep high → displacement down): {total_patterns_bearish}")
    print(f"   Total: {total_patterns_bullish + total_patterns_bearish}")
    
    # Taxa de conversão: sweep → displacement
    if total_sweeps_high > 0:
        conv_bearish = (total_patterns_bearish / total_sweeps_high) * 100
        print(f"\n   Conversão sweep high → bearish: {conv_bearish:.1f}%")
    
    if total_sweeps_low > 0:
        conv_bullish = (total_patterns_bullish / total_sweeps_low) * 100
        print(f"   Conversão sweep low → bullish: {conv_bullish:.1f}%")
    
    # Frequência temporal
    total_dias = (df['time'].max() - df['time'].min()).days
    if total_dias > 0:
        freq_mensal = (total_patterns_bullish + total_patterns_bearish) / (total_dias / 30)
        print(f"\n⏱️  FREQUÊNCIA:")
        print(f"   {freq_mensal:.1f} padrões por mês")
        print(f"   1 padrão a cada {30/freq_mensal:.1f} dias" if freq_mensal > 0 else "   Nenhum padrão detectado")
    
    # Análise de volume nos padrões
    if total_patterns_bullish + total_patterns_bearish > 0:
        avg_volume_patterns = df[df['pattern_bullish'] | df['pattern_bearish']]['tick_volume'].mean()
        avg_volume_total = df['tick_volume'].mean()
        
        print(f"\n📊 VOLUME:")
        print(f"   Média geral: {avg_volume_total:.0f}")
        print(f"   Média em padrões: {avg_volume_patterns:.0f}")
        print(f"   Ratio: {avg_volume_patterns/avg_volume_total:.2f}x")
    
    # Identificar períodos ATIVOS vs INATIVOS
    print(f"\n🔍 ATIVIDADE DO MERCADO:")
    
    # Agrupar por mês
    df['month'] = pd.to_datetime(df['time']).dt.to_period('M')
    monthly = df.groupby('month').agg({
        'pattern_bullish': 'sum',
        'pattern_bearish': 'sum'
    })
    monthly['total_patterns'] = monthly['pattern_bullish'] + monthly['pattern_bearish']
    
    # Top 3 meses mais ativos
    top_months = monthly.nlargest(3, 'total_patterns')
    print(f"\n   Top 3 meses ATIVOS:")
    for month, row in top_months.iterrows():
        print(f"      {month}: {row['total_patterns']:.0f} padrões")
    
    # Top 3 meses menos ativos
    bottom_months = monthly.nsmallest(3, 'total_patterns')
    print(f"\n   Top 3 meses INATIVOS:")
    for month, row in bottom_months.iterrows():
        print(f"      {month}: {row['total_patterns']:.0f} padrões")
    
    return df

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("DETECTOR DE LIQUIDITY SWEEP + DISPLACEMENT (SMC)")
    print("="*70)
    print("\nParâmetros fixos:")
    print(f"  - Lookback: {LOOKBACK_CANDLES} candles")
    print(f"  - Displacement threshold: {DISPLACEMENT_THRESHOLD*100}% do range")
    print(f"  - Displacement window: {DISPLACEMENT_CANDLES} candles")
    print(f"  - Sweep penetration mínima: {MIN_SWEEP_PENETRATION}%")
    
    # Analisar múltiplos timeframes
    symbols = ['EURUSD']
    timeframes = ['H1', 'H4', 'D1']
    
    results = {}
    
    for symbol in symbols:
        for tf in timeframes:
            try:
                df = analyze_pattern(symbol, tf)
                if df is not None:
                    results[f"{symbol}_{tf}"] = df
            except Exception as e:
                print(f"\n❌ Erro em {symbol} {tf}: {e}")
    
    # Resumo final
    print(f"\n{'='*70}")
    print("RESUMO FINAL - ATIVIDADE DO MERCADO")
    print(f"{'='*70}")
    
    for key, df in results.items():
        total = (df['pattern_bullish'].sum() + df['pattern_bearish'].sum())
        status = "🟢 ATIVO" if total > 10 else "🟡 MODERADO" if total > 5 else "🔴 INATIVO"
        print(f"{key}: {total} padrões - {status}")
    
    print(f"\n{'='*7}")
    print("\n💡 INTERPRETAÇÃO:")
    print("   - Períodos com MUITOS padrões: Mercado volátil, muitas reversões")
    print("   - Períodos com POUCOS padrões: Mercado trendeando ou range consolidado")
    print("   - NÃO usar padrões para prever direção")
    print("   - USAR padrões para entender quando mercado está ativo")

if __name__ == "__main__":
    main()
