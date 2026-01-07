"""
@category: tool
@impact: low
@description: Mini dashboard de teste para validação visual do componente
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add paths
sys.path.insert(0, '/home/workbench/projects/coding-day-trading')

from src.visualization.components.lightweight_chart import render_candlestick_chart

st.set_page_config(layout="wide", page_title="Lightweight Charts Test")
st.title("🧪 TradingView Lightweight Charts - POC Test")

# Gera dados de teste
st.sidebar.header("Test Data Generator")
num_candles = st.sidebar.slider("Number of candles", 10, 500, 100)

# Timestamps UNIX (inteiros) - formato correto para TradingView
import time
base_time = int(time.time()) - (num_candles * 3600)  # Começa N horas atrás
timestamps = [base_time + (i * 3600) for i in range(num_candles)]  # 1 hora por candle

test_data = pd.DataFrame({
    'time': timestamps,  # UNIX timestamp (inteiro)
    'open': [100 + i*0.5 for i in range(num_candles)],
    'high': [102 + i*0.5 for i in range(num_candles)],
    'low': [98 + i*0.5 for i in range(num_candles)],
    'close': [101 + i*0.5 for i in range(num_candles)],
    'volume': [1000 + i*10 for i in range(num_candles)]
})

st.sidebar.success(f"✅ Generated {len(test_data)} candles")

# Renderiza o gráfico
st.subheader("📊 Candlestick Chart (TradingView Lightweight Charts)")
try:
    render_candlestick_chart(test_data, height=600, key="test_chart")
    st.success("✅ Chart rendered successfully!")
except Exception as e:
    st.error(f"❌ Error rendering chart: {e}")
    import traceback
    st.code(traceback.format_exc())

# Mostra dados de amostra
with st.expander("View Sample Data"):
    st.dataframe(test_data.head(10))
