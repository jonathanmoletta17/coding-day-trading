"""
Exemplos de Estratégias de Trading Prontas para Implementar
Todas usam dados reais do MT5 via Bridge API
"""

import asyncio
import httpx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()
BRIDGE_URL = os.getenv("MT5_BRIDGE_URL", "http://172.17.96.1:8000")

# =============================================================================
# ESTRATÉGIA 1: MÉDIA MÓVEL DUPLA (CROSSOVER)
# =============================================================================

async def moving_average_crossover(symbol="EURUSD", fast=20, slow=50):
    """
    Estratégia clássica de crossover de médias móveis
    
    Sinal COMPRA: MA rápida cruza MA lenta para cima
    Sinal VENDA: MA rápida cruza MA lenta para baixo
    """
    print(f"\n=== ESTRATÉGIA: Média Móvel Dupla ({fast}/{slow}) ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Obter dados históricos
        response = await client.get(
            f"{BRIDGE_URL}/candles/{symbol}",
            params={"timeframe": "H1", "count": slow + 10}
        )
        candles = response.json()
        
        # Converter para DataFrame
        df = pd.DataFrame(candles)
        df['close'] = pd.to_numeric(df['close'])
        
        # Calcular médias móveis
        df['SMA_fast'] = df['close'].rolling(window=fast).mean()
        df['SMA_slow'] = df['close'].rolling(window=slow).mean()
        
        # Detectar crossovers
        df['signal'] = 0
        df.loc[df['SMA_fast'] > df['SMA_slow'], 'signal'] = 1  # COMPRA
        df.loc[df['SMA_fast'] < df['SMA_slow'], 'signal'] = -1  # VENDA
        
        # Verificar sinal atual
        last_signal = df.iloc[-1]['signal']
        prev_signal = df.iloc[-2]['signal']
        
        print(f"\nSímbolo: {symbol}")
        print(f"Preço atual: {df.iloc[-1]['close']:.5f}")
        print(f"SMA {fast}: {df.iloc[-1]['SMA_fast']:.5f}")
        print(f"SMA {slow}: {df.iloc[-1]['SMA_slow']:.5f}")
        
        if last_signal != prev_signal:
            if last_signal == 1:
                print(f"\n🟢 SINAL DE COMPRA! MA{fast} cruzou MA{slow} para cima")
            elif last_signal == -1:
                print(f"\n🔴 SINAL DE VENDA! MA{fast} cruzou MA{slow} para baixo")
        else:
            trend = "ALTA" if last_signal == 1 else "BAIXA" if last_signal == -1 else "NEUTRO"
            print(f"\n⚪ Tendência atual: {trend}")
        
        return df

# =============================================================================
# ESTRATÉGIA 2: RSI (RELATIVE STRENGTH INDEX)
# =============================================================================

async def rsi_strategy(symbol="EURUSD", period=14, oversold=30, overbought=70):
    """
    Estratégia baseada em RSI
    
    Sinal COMPRA: RSI < 30 (sobrevendido)
    Sinal VENDA: RSI > 70 (sobrecomprado)
    """
    print(f"\n=== ESTRATÉGIA: RSI ({period}) ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BRIDGE_URL}/candles/{symbol}",
            params={"timeframe": "H1", "count": period + 50}
        )
        candles = response.json()
        
        df = pd.DataFrame(candles)
        df['close'] = pd.to_numeric(df['close'])
        
        # Calcular RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        current_rsi = df.iloc[-1]['RSI']
        current_price = df.iloc[-1]['close']
        
        print(f"\nSímbolo: {symbol}")
        print(f"Preço atual: {current_price:.5f}")
        print(f"RSI atual: {current_rsi:.2f}")
        
        if current_rsi < oversold:
            print(f"\n🟢 SINAL DE COMPRA! RSI em área de sobrevenda ({current_rsi:.2f} < {oversold})")
        elif current_rsi > overbought:
            print(f"\n🔴 SINAL DE VENDA! RSI em área de sobrecompra ({current_rsi:.2f} > {overbought})")
        else:
            print(f"\n⚪ Zona neutra (RSI entre {oversold} e {overbought})")
        
        return df

# =============================================================================
# ESTRATÉGIA 3: BOLLINGER BANDS
# =============================================================================

async def bollinger_bands(symbol="EURUSD", period=20, std_dev=2):
    """
    Estratégia de Bollinger Bands
    
    Sinal COMPRA: Preço toca banda inferior
    Sinal VENDA: Preço toca banda superior
    """
    print(f"\n=== ESTRATÉGIA: Bollinger Bands ({period}, {std_dev}σ) ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BRIDGE_URL}/candles/{symbol}",
            params={"timeframe": "H1", "count": period + 20}
        )
        candles = response.json()
        
        df = pd.DataFrame(candles)
        df['close'] = pd.to_numeric(df['close'])
        
        # Calcular Bollinger Bands
        df['SMA'] = df['close'].rolling(window=period).mean()
        df['STD'] = df['close'].rolling(window=period).std()
        df['Upper'] = df['SMA'] + (std_dev * df['STD'])
        df['Lower'] = df['SMA'] - (std_dev * df['STD'])
        
        current_price = df.iloc[-1]['close']
        upper_band = df.iloc[-1]['Upper']
        lower_band = df.iloc[-1]['Lower']
        middle_band = df.iloc[-1]['SMA']
        
        print(f"\nSímbolo: {symbol}")
        print(f"Preço atual: {current_price:.5f}")
        print(f"Banda Superior: {upper_band:.5f}")
        print(f"Banda Média: {middle_band:.5f}")
        print(f"Banda Inferior: {lower_band:.5f}")
        
        # Calcular posição relativa
        bb_position = (current_price - lower_band) / (upper_band - lower_band) * 100
        
        if current_price <= lower_band:
            print(f"\n🟢 SINAL DE COMPRA! Preço tocou banda inferior")
        elif current_price >= upper_band:
            print(f"\n🔴 SINAL DE VENDA! Preço tocou banda superior")
        else:
            print(f"\n⚪ Preço no meio das bandas ({bb_position:.1f}% da faixa)")
        
        return df

# =============================================================================
# ESTRATÉGIA 4: BREAKOUT DE VOLATILIDADE
# =============================================================================

async def volatility_breakout(symbol="EURUSD", lookback=20):
    """
    Estratégia de breakout baseada em volatilidade
    
    Sinal COMPRA: Preço rompe acima do range
    Sinal VENDA: Preço rompe abaixo do range
    """
    print(f"\n=== ESTRATÉGIA: Volatility Breakout ({lookback} períodos) ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BRIDGE_URL}/candles/{symbol}",
            params={"timeframe": "H1", "count": lookback + 10}
        )
        candles = response.json()
        
        df = pd.DataFrame(candles)
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        
        # Calcular range histórico
        df['range_high'] = df['high'].rolling(window=lookback).max()
        df['range_low'] = df['low'].rolling(window=lookback).min()
        
        current_price = df.iloc[-1]['close']
        resistance = df.iloc[-2]['range_high']  # Range anterior
        support = df.iloc[-2]['range_low']
        
        print(f"\nSímbolo: {symbol}")
        print(f"Preço atual: {current_price:.5f}")
        print(f"Resistência ({lookback}H): {resistance:.5f}")
        print(f"Suporte ({lookback}H): {support:.5f}")
        print(f"Range: {(resistance - support):.5f}")
        
        if current_price > resistance:
            print(f"\n🟢 BREAKOUT DE ALTA! Preço rompeu resistência")
        elif current_price < support:
            print(f"\n🔴 BREAKOUT DE BAIXA! Preço rompeu suporte")
        else:
            position = (current_price - support) / (resistance - support) * 100
            print(f"\n⚪ Dentro do range ({position:.1f}% do range)")
        
        return df

# =============================================================================
# ESTRATÉGIA 5: MULTI-TIMEFRAME ANALYSIS
# =============================================================================

async def multi_timeframe_trend(symbol="EURUSD"):
    """
    Análise de tendência em múltiplos timeframes
    
    Confirma tendência quando todos os TFs apontam na mesma direção
    """
    print(f"\n=== ESTRATÉGIA: Multi-Timeframe Trend ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        timeframes = {
            "H1": 50,
            "H4": 50,
            "D1": 50
        }
        
        trends = {}
        
        for tf, count in timeframes.items():
            response = await client.get(
                f"{BRIDGE_URL}/candles/{symbol}",
                params={"timeframe": tf, "count": count}
            )
            candles = response.json()
            
            df = pd.DataFrame(candles)
            df['close'] = pd.to_numeric(df['close'])
            
            # SMA 20
            df['SMA'] = df['close'].rolling(window=20).mean()
            
            current_price = df.iloc[-1]['close']
            sma = df.iloc[-1]['SMA']
            
            trend = "ALTA" if current_price > sma else "BAIXA"
            trends[tf] = trend
            
            print(f"\n{tf}: Preço {current_price:.5f} vs SMA {sma:.5f} → {trend}")
        
        # Verificar alinhamento
        if all(t == "ALTA" for t in trends.values()):
            print(f"\n🟢🟢🟢 TENDÊNCIA FORTE DE ALTA! Todos os timeframes alinhados")
        elif all(t == "BAIXA" for t in trends.values()):
            print(f"\n🔴🔴🔴 TENDÊNCIA FORTE DE BAIXA! Todos os timeframes alinhados")
        else:
            print(f"\n⚪ Tendências divergentes - Aguardar confirmação")
        
        return trends

# =============================================================================
# RUNNER: EXECUTAR TODAS AS ESTRATÉGIAS
# =============================================================================

async def run_all_strategies():
    """Executa todas as estratégias para análise completa"""
    
    print("=" * 70)
    print("ANÁLISE COMPLETA DE ESTRATÉGIAS - TEMPO REAL")
    print("=" * 70)
    
    symbol = "EURUSD"
    
    # Executar cada estratégia
    await moving_average_crossover(symbol)
    await rsi_strategy(symbol)
    await bollinger_bands(symbol)
    await volatility_breakout(symbol)
    await multi_timeframe_trend(symbol)
    
    print("\n" + "=" * 70)
    print("ANÁLISE COMPLETA!")
    print("=" * 70)
    print("\n💡 Dica: Combine múltiplos sinais para maior confiabilidade")
    print("   Ex: Compra quando RSI < 30 E preço > SMA 20")

if __name__ == "__main__":
    asyncio.run(run_all_strategies())
