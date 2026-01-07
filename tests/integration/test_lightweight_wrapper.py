"""
@category: tool
@impact: low
@description: Teste end-to-end do wrapper lightweight_chart
"""
import pandas as pd
from datetime import datetime, timedelta

# Importa o wrapper
from src.visualization.components.lightweight_chart import render_candlestick_chart

# Cria dados de teste
dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(100, 0, -1)]
test_data = pd.DataFrame({
    'time': dates,
    'open': [100 + i*0.5 for i in range(100)],
    'high': [102 + i*0.5 for i in range(100)],
    'low': [98 + i*0.5 for i in range(100)],
    'close': [101 + i*0.5 for i in range(100)],
    'volume': [1000 + i*10 for i in range(100)]
})

print("✅ Wrapper importado com sucesso")
print(f"✅ Dados de teste criados: {len(test_data)} candles")
print("\n📊 Primeiras 3 linhas:")
print(test_data.head(3))
