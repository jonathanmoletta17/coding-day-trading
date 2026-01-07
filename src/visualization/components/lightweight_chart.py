"""
@category: production
@impact: low
@description: Wrapper para integração do TradingView Lightweight Charts no Dashboard
"""
import pandas as pd
from lightweight_charts_v5 import lightweight_charts_v5_component

# Design System
from src.visualization.design_system import COLORS, get_tradingview_theme

def render_candlestick_chart(df: pd.DataFrame, height: int = 500, key: str = "lwc_chart", indicators: dict = None):
    """
    Renderiza gráfico de candlestick usando TradingView Lightweight Charts.
    
    Args:
        df: DataFrame com colunas ['time', 'open', 'high', 'low', 'close', 'volume']
            - 'time' DEVE ser Unix timestamp (inteiro) ou será convertido
        height: Altura do gráfico em pixels
        key: Unique key para o componente Streamlit
        indicators: Dict opcional com line series adicionais (EMAs, etc)
            Formato: {
                'ema9': {'color': '#bb86fc', 'lineWidth': 2},
                'ema21': {'color': '#03dac6', 'lineWidth': 2},
            }
            OBS: As colunas devem existir no DataFrame
    """
    # Converte DataFrame para formato esperado pela biblioteca
    # Formato: [{"time": 1609459200, "open": 100, "high": 105, "low": 95, "close": 102}]
    
    if df.empty:
        return None
    
    # Garante que 'time' está no formato Unix timestamp (inteiro)
    df_copy = df.copy()
    if 'time' in df_copy.columns:
        # Se for datetime, converter para Unix timestamp
        if pd.api.types.is_datetime64_any_dtype(df_copy['time']):
            df_copy['time'] = df_copy['time'].astype('int64') // 10**9  # Nanoseconds to seconds
        # Se for string, tentar parsear e converter
        elif df_copy['time'].dtype == 'object':
            df_copy['time'] = pd.to_datetime(df_copy['time']).astype('int64') // 10**9
        # Se já for numérico, garantir que é int
        else:
            df_copy['time'] = df_copy['time'].astype(int)
    
    # Prepara dados de candlestick
    candle_data = df_copy[['time', 'open', 'high', 'low', 'close']].to_dict('records')
    
    # Prepara dados de volume (opcional)
    volume_data = []
    if 'volume' in df_copy.columns:
        volume_data = df_copy[['time', 'volume']].rename(columns={'volume': 'value'}).to_dict('records')
        # Adiciona cores baseadas em alta/baixa usando COLORS do design system
        for i, row in enumerate(volume_data):
            row['color'] = COLORS["bull"] if i > 0 and candle_data[i]['close'] > candle_data[i]['open'] else COLORS["bear"]
    
    # Obtém tema do design system
    theme_config = get_tradingview_theme()
    
    # Configuração de panes (gráfico principal + volume)
    charts_config = [
        {
            "height": int(height * 0.7),  # 70% para candlesticks
            "series": [
                {
                    "type": "Candlestick",
                    "data": candle_data,
                    "options": {
                        "upColor": COLORS["bull"],         # Verde institucional
                        "downColor": COLORS["bear"],       # Vermelho institucional
                        "borderVisible": False,
                        "wickUpColor": COLORS["bull"],
                        "wickDownColor": COLORS["bear"]
                    }
                }
            ],
            **theme_config  # Aplica background, grid, crosshair
        }
    ]
    
    # === Adiciona Line Series para Indicadores (EMAs, etc) ===
    if indicators and isinstance(indicators, dict):
        for indicator_name, indicator_config in indicators.items():
            # Verifica se a coluna existe no DataFrame
            if indicator_name not in df_copy.columns:
                continue
            
            # Prepara dados da line series
            line_data = df_copy[['time', indicator_name]].dropna()
            line_data = line_data.rename(columns={indicator_name: 'value'}).to_dict('records')
            
            if not line_data:
                continue
            
            # Configuração padrão + user overrides
            line_options = {
                'color': indicator_config.get('color', COLORS['accent']),
                'lineWidth': indicator_config.get('lineWidth', 2),
                'title': indicator_config.get('title', indicator_name.upper())
            }
            
            # Adiciona line series ao mesmo pane que candlesticks
            charts_config[0]['series'].append({
                'type': 'Line',
                'data': line_data,
                'options': line_options
            })

    # === Adiciona Marcadores de Sinais (BUY/SELL) ===
    # Formato esperado em markers: 
    # [{"time": 1609459200, "position": "aboveBar", "color": "red", "shape": "arrowDown", "text": "SHORT"}]
    if 'markers' in df_copy.columns:
        # Extrair marcadores da coluna se existirem
        all_markers = []
        for _, row in df_copy.iterrows():
            if isinstance(row['markers'], list):
                all_markers.extend(row['markers'])
        
        if all_markers:
            # Em lightweight-charts v5, markers costumam ser via setMarkers na série.
            # Aqui passamos como uma propriedade da série principal.
            charts_config[0]['series'][0]['markers'] = all_markers
    
    # Adiciona pane de volume se existir
    if volume_data:
        charts_config.append({
            "height": int(height * 0.3),  # 30% para volume
            "series": [
                {
                    "type": "Histogram",
                    "data": volume_data,
                    "options": {
                        "priceFormat": {
                            "type": 'volume',
                        },
                        "priceScaleId": ''  # Escala dedicada
                    }
                }
            ]
        })
    
    # Renderiza o componente
    return lightweight_charts_v5_component(
        name="TradingView Chart",
        charts=charts_config,
        height=height,
        zoom_level=100,  # Mostra últimas 100 barras
        key=key
    )
