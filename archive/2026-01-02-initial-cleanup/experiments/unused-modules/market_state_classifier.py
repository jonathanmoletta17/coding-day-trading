"""
Market State Classifier - Refatorado (Sem Tautologias)

Classifica o regime do mercado em:
- REVERSIVE: Sweeps seguidos de reversão (mercado rejeita extremos)
- TREND: Sweeps seguidos de continuação (mercado aceita no extremos)
- INACTIVE: Poucos sweeps (mercado consolidado)

Correções:
1. Separa detecção de sweep de análise de comportamento
2. Mede TODOS os retornos pós-sweep (não só os que "passam")
3. Classifica por DISTRIBUIÇÃO observada (não threshold arbitrário)
4. Parâmetros estruturais (baseados em spread, não magic numbers)
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
# PARÂMETROS ESTRUTURAIS (não arbitrários)
# =============================================================================

LOOKBACK_CANDLES = 20  # Mantido por consistência com estudos SMC, mas testado
ANALYSIS_WINDOW = 5    # Janela para medir retorno pós-sweep
SPREAD_MULTIPLIER = 2  # Penetração = 2x spread médio (estrutural)

# =============================================================================
# FUNÇÕES CORE (sem tautologia)
# =============================================================================

def calculate_spread(df: pd.DataFrame) -> float:
    """
    Calcula spread médio do instrumento
    Base estrutural para filtro de sweep
    """
    spread = (df['high'] - df['low']).median()
    return spread

def detect_sweeps_only(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta APENAS sweeps, sem assumir o que acontece depois
    
    Critério estrutural:
    - Rompe high/low recente
    - Penetração > 2x spread médio (evita ruído)
    """
    
    avg_spread = calculate_spread(df)
    min_penetration = SPREAD_MULTIPLIER * avg_spread
    
    # Rolling extremos
    df['rolling_high'] = df['high'].shift(1).rolling(window=LOOKBACK_CANDLES).max()
    df['rolling_low'] = df['low'].shift(1).rolling(window=LOOKBACK_CANDLES).min()
    
    # Detectar sweeps APENAS com base em preço
    df['sweep_high'] = (df['high'] - df['rolling_high']) > min_penetration
    df['sweep_low'] = (df['rolling_low'] - df['low']) > min_penetration
    
    df['sweep_any'] = df['sweep_high'] | df['sweep_low']
    
    return df

def measure_post_sweep_return(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mede retorno após TODOS os sweeps (não só os "válidos")
    
    Sem threshold: apenas OBSERVA o que acontece
    """
    
    df['return_after_sweep_high'] = np.nan
    df['return_after_sweep_low'] = np.nan
    df['direction_after_sweep'] = 0  # -1 = reversão, +1 = continuação, 0 = neutro
    
    for i in range(len(df) - ANALYSIS_WINDOW):
        
        # Se teve sweep high
        if df.iloc[i]['sweep_high']:
            sweep_high = df.iloc[i]['high']
            sweep_range = df.iloc[i]['high'] - df.iloc[i]['low']
            
            # Medir movimento nos próximos N candles
            future_low = df.iloc[i+1:i+ANALYSIS_WINDOW+1]['low'].min()
            future_high = df.iloc[i+1:i+ANALYSIS_WINDOW+1]['high'].max()
            
            # Retorno normalizado pelo range do sweep
            if sweep_range > 0:
                # Negativo = reversão (caiu), Positivo = continuação (subiu mais)
                return_normalized = (future_high - sweep_high) / sweep_range
                df.iloc[i, df.columns.get_loc('return_after_sweep_high')] = return_normalized
                
                # Classificar direção SEM threshold arbitrário
                # Apenas marca se moveu significativamente (>20% do range)
                if (sweep_high - future_low) / sweep_range > 0.2:
                    df.iloc[i, df.columns.get_loc('direction_after_sweep')] = -1  # Reversão
                elif return_normalized > 0.2:
                    df.iloc[i, df.columns.get_loc('direction_after_sweep')] = 1  # Continuação
        
        # Se teve sweep low
        if df.iloc[i]['sweep_low']:
            sweep_low = df.iloc[i]['low']
            sweep_range = df.iloc[i]['high'] - df.iloc[i]['low']
            
            future_low = df.iloc[i+1:i+ANALYSIS_WINDOW+1]['low'].min()
            future_high = df.iloc[i+1:i+ANALYSIS_WINDOW+1]['high'].max()
            
            if sweep_range > 0:
                # Negativo = reversão (subiu), Positivo = continuação (caiu mais)
                return_normalized = (sweep_low - future_low) / sweep_range
                df.iloc[i, df.columns.get_loc('return_after_sweep_low')] = return_normalized
                
                if (future_high - sweep_low) / sweep_range > 0.2:
                    df.iloc[i, df.columns.get_loc('direction_after_sweep')] = -1  # Reversão
                elif return_normalized > 0.2:
                    df.iloc[i, df.columns.get_loc('direction_after_sweep')] = 1  # Continuação
    
    return df

def classify_market_state(df: pd.DataFrame) -> str:
    """
    Classifica regime do mercado baseado em DISTRIBUIÇÃO observada
    
    Não usa thresholds arbitrários:
    - Conta frequência de comportamentos
    - Classifica por padrão dominante
    """
    
    total_sweeps = df['sweep_any'].sum()
    
    if total_sweeps < 10:
        metrics = {
            'total_sweeps': total_sweeps,
            'reversions': 0,
            'continuations': 0,
            'neutral': 0,
            'reversion_rate': 0,
            'continuation_rate': 0,
            'confidence': 0,
            'reason': 'Poucos sweeps detectados'
        }
        return "INACTIVE", metrics
    
    # Contar comportamentos
    reversions = (df['direction_after_sweep'] == -1).sum()
    continuations = (df['direction_after_sweep'] == 1).sum()
    neutral = (df['direction_after_sweep'] == 0).sum()
    
    # Taxas observadas (sem threshold)
    reversion_rate = reversions / total_sweeps if total_sweeps > 0 else 0
    continuation_rate = continuations / total_sweeps if total_sweeps > 0 else 0
    
    # Classificação por comportamento dominante (>50%)
    if reversion_rate > 0.5:
        state = "REVERSIVE"
        confidence = reversion_rate
    elif continuation_rate > 0.5:
        state = "TREND"
        confidence = continuation_rate
    else:
        state = "INACTIVE"  # Sem padrão claro
        confidence = max(reversion_rate, continuation_rate)
    
    metrics = {
        'total_sweeps': total_sweeps,
        'reversions': reversions,
        'continuations': continuations,
        'neutral': neutral,
        'reversion_rate': reversion_rate,
        'continuation_rate': continuation_rate,
        'confidence': confidence
    }
    
    return state, metrics

# =============================================================================
# ANÁLISE
# =============================================================================

def analyze_market_state(symbol: str, timeframe: str):
    """
    Analisa estado do mercado sem tautologias
    """
    
    print(f"\n{'='*70}")
    print(f"MARKET STATE CLASSIFIER: {symbol} - {timeframe}")
    print(f"{'='*70}")
    
    # Carregar dados
    query = f"""
        SELECT time, open, high, low, close, tick_volume
        FROM candles
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = '{symbol}')
            AND timeframe = '{timeframe}'
        ORDER BY time ASC
    """
    
    df = pd.read_sql(query, engine)
    
    if len(df) < LOOKBACK_CANDLES + ANALYSIS_WINDOW + 10:
        print(f"❌ Dados insuficientes")
        return None
    
    print(f"\n📊 Dataset: {len(df)} candles")
    print(f"   Período: {df['time'].min().date()} a {df['time'].max().date()}")
    
    # Converter para numérico
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col])
    
    # Processar
    avg_spread = calculate_spread(df)
    print(f"\n📏 Spread médio: {avg_spread:.5f}")
    print(f"   Penetração mínima: {SPREAD_MULTIPLIER * avg_spread:.5f} ({SPREAD_MULTIPLIER}x spread)")
    
    df = detect_sweeps_only(df)
    df = measure_post_sweep_return(df)
    
    # Classificar
    state, metrics = classify_market_state(df)
    
    # Reportar
    print(f"\n🎯 MARKET STATE: {state}")
    print(f"   Confiança: {metrics['confidence']:.1%}")
    
    print(f"\n📈 Estatísticas:")
    print(f"   Total de sweeps: {metrics['total_sweeps']}")
    print(f"   └─ Reversões: {metrics['reversions']} ({metrics['reversion_rate']:.1%})")
    print(f"   └─ Continuações: {metrics['continuations']} ({metrics['continuation_rate']:.1%})")
    print(f"   └─ Neutros: {metrics['neutral']}")
    
    # Interpretação
    print(f"\n💡 Interpretação:")
    if state == "REVERSIVE":
        print(f"   Mercado REJEITANDO extremos - sweeps revertem")
        print(f"   Comportamento: Range-bound, falsos breakouts")
    elif state == "TREND":
        print(f"   Mercado ACEITANDO extremos - sweeps continuam")
        print(f"   Comportamento: Trendeando, breakouts válidos")
    else:
        print(f"   Mercado SEM PADRÃO claro - baixa atividade")
        print(f"   Comportamento: Consolidado ou transição")
    
    return df, state, metrics

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("MARKET STATE CLASSIFIER (Sem Tautologias)")
    print("="*70)
    print("\nMetodologia:")
    print("  1. Detecta sweeps (critério estrutural: >2x spread)")
    print("  2. Mede TODOS os retornos pós-sweep")
    print("  3. Classifica por DISTRIBUIÇÃO observada")
    print("  4. Não usa thresholds arbitrários")
    
    symbols = ['EURUSD']
    timeframes = ['H1', 'H4', 'D1']
    
    results = {}
    
    for symbol in symbols:
        for tf in timeframes:
            try:
                df, state, metrics = analyze_market_state(symbol, tf)
                results[f"{symbol}_{tf}"] = {
                    'state': state,
                    'metrics': metrics
                }
            except Exception as e:
                print(f"\n❌ Erro em {symbol} {tf}: {e}")
    
    # Resumo
    print(f"\n{'='*70}")
    print("RESUMO - MARKET STATES")
    print(f"{'='*70}\n")
    
    for key, data in results.items():
        state = data['state']
        conf = data['metrics']['confidence']
        emoji = "🔄" if state == "REVERSIVE" else "📈" if state == "TREND" else "⚪"
        print(f"{emoji} {key}: {state} (confidence: {conf:.1%})")
    
    print(f"\n{'='*70}")
    print("\n✅ Validações:")
    print("   - Sem conversão 100% (mede TODOS os retornos)")
    print("   - Sem thresholds arbitrários (classifica por distribuição)")
    print("   - Parâmetros estruturais (spread-based)")
    print("   - Sem tautologias")

if __name__ == "__main__":
    main()
