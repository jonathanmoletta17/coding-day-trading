import plotly.graph_objects as go
import numpy as np
import pandas as pd
from datetime import datetime

class OrderBookVisualizer:
    """
    Gerencia a visualização de dados de alta frequência (Heatmap/Depth).
    """
    
    def __init__(self, max_history=100, price_levels=50):
        self.max_history = max_history
        self.price_levels = price_levels
        # Matrizes para Heatmap: (Prices x Time)
        # Como preços mudam, usamos um grid relativo ou absoluto dinâmico.
        # Simplificação: Armazenamos Snapshots brutos e renderizamos on-demand
        self.history = [] # Lista de dicts {timestamp, bids, asks}

    def update(self, snapshot):
        """
        Adiciona novo snapshot ao histórico.
        snapshot: {bids: np.array, asks: np.array, timestamp: float}
        """
        self.history.append(snapshot)
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def generate_heatmap_fig(self):
        """
        Gera figura Plotly do Heatmap.
        """
        if not self.history:
            return go.Figure()

        # Extrair todos os preços e volumes para criar um grid
        # Abordagem simplificada: Plotar Scatter 3D ou Heatmap 2D binado
        
        # Coletando dados para DataFrame
        records = []
        for snap in self.history:
            ts = datetime.fromtimestamp(snap['timestamp'])
            # Bids
            for price, vol in snap['bids']:
                records.append({'Time': ts, 'Price': price, 'Volume': vol, 'Type': 'Bid'})
            # Asks
            for price, vol in snap['asks']:
                records.append({'Time': ts, 'Price': price, 'Volume': vol, 'Type': 'Ask'})
                
        df = pd.DataFrame(records)
        
        if df.empty:
            return go.Figure()

        # Criando Heatmap usando Density Mapbox ou Heatmap 2D
        # Para Heatmap 2D, precisamos de um grid regular.
        # Vamos pivotar: Index=Price, Columns=Time, Values=Volume
        
        # Arredondar preços para agrupar (tick size)
        # Detectar tick size aproximado
        if len(df) > 1:
            prices = df['Price'].unique()
            prices.sort()
            min_diff = np.min(np.diff(prices)) if len(prices) > 1 else 0.01
            tick_size = max(min_diff, 0.01) # Evitar zero
        else:
            tick_size = 0.01
            
        df['PriceBin'] = (df['Price'] / tick_size).round() * tick_size
        
        # Agrupar volumes por (Time, PriceBin)
        pivot = df.groupby(['PriceBin', 'Time'])['Volume'].sum().unstack(fill_value=0)
        
        # Ordenar preços (Eixo Y) descrescente
        pivot = pivot.sort_index(ascending=False)
        
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='Viridis', # ou 'Hot'
            showscale=True
        ))
        
        fig.update_layout(
            title="Liquidez Real (Order Book Heatmap)",
            xaxis_title="Tempo",
            yaxis_title="Preço",
            template="plotly_dark",
            height=500,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        return fig

    def generate_depth_chart(self, snapshot):
        """
        Gera gráfico de profundidade clássico (Área).
        """
        bids = snapshot['bids']
        asks = snapshot['asks']
        
        # Cumulativo
        bid_prices = bids[:, 0]
        bid_vols = np.cumsum(bids[:, 1])
        
        ask_prices = asks[:, 0]
        ask_vols = np.cumsum(asks[:, 1])
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=bid_prices, 
            y=bid_vols, 
            fill='tozeroy',
            name='Bids (Compra)',
            line_color='green'
        ))
        
        fig.add_trace(go.Scatter(
            x=ask_prices, 
            y=ask_vols, 
            fill='tozeroy',
            name='Asks (Venda)',
            line_color='red'
        ))
        
        fig.update_layout(
            title="Profundidade de Mercado (DOM)",
            xaxis_title="Preço",
            yaxis_title="Volume Acumulado",
            template="plotly_dark",
            height=300,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        return fig
