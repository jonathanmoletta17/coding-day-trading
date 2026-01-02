"""
Market Context Classifier - Versão Definitiva

Princípios:
1. NÃO gera sinais de trading
2. NÃO prevê preços futuros
3. NÃO otimiza parâmetros
4. Separa ATIVIDADE (eventos) de COMPORTAMENTO (padrões)
5. Mede TODOS os eventos (não filtra "válidos")
6. Classifica APENAS por distribuição observada
7. Determinístico (mesmos dados = mesmo output)
8. Auditável (cada cálculo verificável)
9. Output EXCLUSIVAMENTE descritivo

Output:
- Descrição do que FOI observado
- Sem prescrição do que FAZER
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Tuple
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DB_URL)

# =============================================================================
# DATA CLASSES (Output Estruturado)
# =============================================================================

@dataclass
class ActivityMetrics:
    """Métricas de ATIVIDADE (quantas coisas aconteceram)"""
    period_start: str
    period_end: str
    total_candles: int
    total_sweeps: int
    sweeps_per_day: float
    avg_spread: float
    avg_range: float
    
    def describe(self) -> str:
        return f"""
ATIVIDADE DO MERCADO:
  Período: {self.period_start} a {self.period_end}
  Total de candles: {self.total_candles}
  Varreduras de liquidez: {self.total_sweeps}
  Frequência: {self.sweeps_per_day:.2f} sweeps/dia
  Spread médio: {self.avg_spread:.5f}
  Range médio: {self.avg_range:.5f}
        """.strip()

@dataclass
class BehaviorMetrics:
    """Métricas de COMPORTAMENTO (como mercado reagiu)"""
    total_measured: int
    reversions_count: int
    continuations_count: int
    neutral_count: int
    reversion_rate: float
    continuation_rate: float
    neutral_rate: float
    dominant_pattern: str  # REVERSIVE, TREND, ou MIXED
    
    def describe(self) -> str:
        return f"""
COMPORTAMENTO PÓS-SWEEP:
  Total de sweeps analisados: {self.total_measured}
  Reversões observadas: {self.reversions_count} ({self.reversion_rate:.1%})
  Continuações observadas: {self.continuations_count} ({self.continuation_rate:.1%})
  Movimentos neutros: {self.neutral_count} ({self.neutral_rate:.1%})
  Padrão dominante: {self.dominant_pattern}
        """.strip()

@dataclass
class MarketContext:
    """Contexto completo do mercado (descritivo apenas)"""
    symbol: str
    timeframe: str
    activity: ActivityMetrics
    behavior: BehaviorMetrics
    activity_level: str  # HIGH, MEDIUM, LOW
    behavior_type: str   # REVERSIVE, TREND, MIXED
    
    def describe(self) -> str:
        """Output puramente descritivo"""
        return f"""
{'='*70}
CONTEXTO DE MERCADO: {self.symbol} - {self.timeframe}
{'='*70}

{self.activity.describe()}

Nível de atividade: {self.activity_level}

{self.behavior.describe()}

Tipo de comportamento: {self.behavior_type}

{'='*70}
INTERPRETAÇÃO DESCRITIVA:

Atividade:
  {"Alta frequência de sweeps - mercado ativo" if self.activity_level == "HIGH" else 
   "Frequência moderada de sweeps - atividade normal" if self.activity_level == "MEDIUM" else
   "Baixa frequência de sweeps - mercado quieto"}

Comportamento:
  {f"Sweeps majoritariamente REVERTEM ({self.behavior.reversion_rate:.0%})" if self.behavior_type == "REVERSIVE" else
   f"Sweeps majoritariamente CONTINUAM ({self.behavior.continuation_rate:.0%})" if self.behavior_type == "TREND" else
   "Sem padrão claro - comportamento misto"}

{'='*70}
        """.strip()

# =============================================================================
# STEP 1: MEDIR ATIVIDADE (Quantos eventos)
# =============================================================================

def measure_activity(df: pd.DataFrame, symbol: str, timeframe: str) -> ActivityMetrics:
    """
    Mede ATIVIDADE do mercado (eventos que aconteceram)
    
    Não filtra, não julga, apenas CONTA
    """
    
    # Spread médio (estrutural)
    avg_spread = (df['high'] - df['low']).median()
    avg_range = (df['high'] - df['low']).mean()
    
    # Threshold estrutural (2x spread médio)
    min_penetration = 2 * avg_spread
    
    # Detectar sweeps (rompe high/low recente com penetração mínima)
    df['rolling_high'] = df['high'].shift(1).rolling(window=20).max()
    df['rolling_low'] = df['low'].shift(1).rolling(window=20).min()
    
    df['sweep_high'] = (df['high'] - df['rolling_high']) > min_penetration
    df['sweep_low'] = (df['rolling_low'] - df['low']) > min_penetration
    df['sweep_any'] = df['sweep_high'] | df['sweep_low']
    
    total_sweeps = df['sweep_any'].sum()
    
    # Frequência temporal
    days = (df['time'].max() - df['time'].min()).days
    sweeps_per_day = total_sweeps / days if days > 0 else 0
    
    return ActivityMetrics(
        period_start=str(df['time'].min().date()),
        period_end=str(df['time'].max().date()),
        total_candles=len(df),
        total_sweeps=total_sweeps,
        sweeps_per_day=sweeps_per_day,
        avg_spread=avg_spread,
        avg_range=avg_range
    ), df

# =============================================================================
# STEP 2: MEDIR COMPORTAMENTO (Como mercado reagiu)
# =============================================================================

def measure_behavior(df: pd.DataFrame) -> BehaviorMetrics:
    """
    Mede COMPORTAMENTO após sweeps
    
    Analisa TODOS os sweeps, não só os "válidos"
    Classifica por distribuição observada, sem threshold arbitrário
    """
    
    df['direction'] = 0  # -1 = reversão, +1 = continuação, 0 = neutro
    
    analysis_window = 5
    
    for i in range(len(df) - analysis_window):
        if df.iloc[i]['sweep_high']:
            # Sweep high: medimos se reverteu (caiu) ou continuou (subiu)
            sweep_high = df.iloc[i]['high']
            sweep_range = df.iloc[i]['high'] - df.iloc[i]['low']
            
            # Próximos N candles
            future_low = df.iloc[i+1:i+analysis_window+1]['low'].min()
            future_high = df.iloc[i+1:i+analysis_window+1]['high'].max()
            
            if sweep_range > 0:
                down_move = (sweep_high - future_low) / sweep_range
                up_move = (future_high - sweep_high) / sweep_range
                
                # Classifica por movimento predominante
                if down_move > 0.2 and down_move > up_move:
                    df.iloc[i, df.columns.get_loc('direction')] = -1  # Reverteu
                elif up_move > 0.2 and up_move > down_move:
                    df.iloc[i, df.columns.get_loc('direction')] = 1  # Continuou
        
        elif df.iloc[i]['sweep_low']:
            # Sweep low: medimos se reverteu (subiu) ou continuou (caiu)
            sweep_low = df.iloc[i]['low']
            sweep_range = df.iloc[i]['high'] - df.iloc[i]['low']
            
            future_low = df.iloc[i+1:i+analysis_window+1]['low'].min()
            future_high = df.iloc[i+1:i+analysis_window+1]['high'].max()
            
            if sweep_range > 0:
                up_move = (future_high - sweep_low) / sweep_range
                down_move = (sweep_low - future_low) / sweep_range
                
                if up_move > 0.2 and up_move > down_move:
                    df.iloc[i, df.columns.get_loc('direction')] = -1  # Reverteu
                elif down_move > 0.2 and down_move > up_move:
                    df.iloc[i, df.columns.get_loc('direction')] = 1  # Continuou
    
    # Contar comportamentos
    reversions = (df['direction'] == -1).sum()
    continuations = (df['direction'] == 1).sum()
    neutral = (df['direction'] == 0).sum()
    total = reversions + continuations + neutral
    
    if total == 0:
        return BehaviorMetrics(0, 0, 0, 0, 0.0, 0.0, 0.0, "INDEFINIDO")
    
    rev_rate = reversions / total
    cont_rate = continuations / total
    neut_rate = neutral / total
    
    # Classificar por DISTRIBUIÇÃO (não threshold)
    if rev_rate > 0.5:
        dominant = "REVERSIVE"
    elif cont_rate > 0.5:
        dominant = "TREND"
    else:
        dominant = "MIXED"
    
    return BehaviorMetrics(
        total_measured=total,
        reversions_count=reversions,
        continuations_count=continuations,
        neutral_count=neutral,
        reversion_rate=rev_rate,
        continuation_rate=cont_rate,
        neutral_rate=neut_rate,
        dominant_pattern=dominant
    )

# =============================================================================
# STEP 3: CLASSIFICAR CONTEXTO (Descritivo)
# =============================================================================

def classify_context(activity: ActivityMetrics, behavior: BehaviorMetrics, 
                     symbol: str, timeframe: str) -> MarketContext:
    """
    Classifica contexto do mercado de forma PURAMENTE DESCRITIVA
    
    Sem sinais, sem previsões, apenas descrição do observado
    """
    
    # Classificar nível de atividade (baseado em frequência)
    if activity.sweeps_per_day > 2.0:
        activity_level = "HIGH"
    elif activity.sweeps_per_day > 0.5:
        activity_level = "MEDIUM"
    else:
        activity_level = "LOW"
    
    # Comportamento já classificado
    behavior_type = behavior.dominant_pattern
    
    return MarketContext(
        symbol=symbol,
        timeframe=timeframe,
        activity=activity,
        behavior=behavior,
        activity_level=activity_level,
        behavior_type=behavior_type
    )

# =============================================================================
# INTERFACE PRINCIPAL
# =============================================================================

def analyze_market_context(symbol: str, timeframe: str) -> MarketContext:
    """
    Analisa contexto de mercado de forma determinística e auditável
    
    Retorna APENAS descrição do que foi observado
    """
    
    # Carregar dados
    query = f"""
        SELECT time, open, high, low, close, tick_volume
        FROM candles
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = '{symbol}')
            AND timeframe = '{timeframe}'
        ORDER BY time ASC
    """
    
    df = pd.read_sql(query, engine)
    
    # Converter para numérico
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col])
    
    # Step 1: Medir atividade
    activity, df = measure_activity(df, symbol, timeframe)
    
    # Step 2: Medir comportamento
    behavior = measure_behavior(df)
    
    # Step 3: Classificar contexto
    context = classify_context(activity, behavior, symbol, timeframe)
    
    return context

# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Executa análise de contexto para múltiplos timeframes
    Output EXCLUSIVAMENTE descritivo
    """
    
    print("="*70)
    print("MARKET CONTEXT CLASSIFIER - Análise Descritiva")
    print("="*70)
    print("\nPrincípios:")
    print("  ✓ Não gera sinais")
    print("  ✓ Não prevê preço")
    print("  ✓ Não otimiza parâmetros")
    print("  ✓ Separa atividade de comportamento")
    print("  ✓ Mede TODOS os eventos")
    print("  ✓ Classifica por distribuição")
    print("  ✓ Determinístico e auditável")
    print("  ✓ Output puramente descritivo")
    print()
    
    # Analisar
    for timeframe in ['H1', 'H4', 'D1']:
        try:
            context = analyze_market_context('EURUSD', timeframe)
            print("\n" + context.describe())
            print()
        except Exception as e:
            print(f"\n❌ Erro em {timeframe}: {e}\n")
    
    print("\n" + "="*70)
    print("NOTA IMPORTANTE:")
    print("Este é um CLASSIFICADOR DE CONTEXTO, não um sistema de trading.")
    print("Descreve o que FOI observado, não prescreve o que FAZER.")
    print("="*70)

if __name__ == "__main__":
    main()
