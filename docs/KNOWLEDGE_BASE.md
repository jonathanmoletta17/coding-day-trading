# Base de Conhecimento e Referências

Este documento centraliza conceitos, fontes e estratégias para o desenvolvimento do sistema.

## 1. Áreas de Estudo

### Lógica de Mercado & Microestrutura
- **Order Book Dynamics**: Entender como a liquidez se move. Estudar o desequilíbrio entre bid/ask.
- **Auction Theory**: Como o preço é descoberto através de leilões contínuos.
- **Volume Profile & VWAP**: Ferramentas institucionais para identificar zonas de valor.

### Algoritmos & Machine Learning
- **Time Series Forecasting**: Modelos ARIMA, GARCH (clássicos) vs. Transformers, LSTMs (Deep Learning).
- **Reinforcement Learning (RL)**: Agentes que aprendem a operar por recompensa (PPO, DQN).
- **Feature Engineering**: A arte de criar inputs relevantes (ex: volatilidade realizada, skewness do book).

## 2. Ferramentas e Linguagens
- **Python**: Ecossistema principal (Pandas, Numpy, PyTorch).
- **Rust/C++**: Para componentes de latência crítica (futuro).
- **Plotly/Streamlit**: Para visualização interativa.
- **PostgreSQL/TimescaleDB**: Para banco de dados de séries temporais.

## 3. Fontes Internacionais e Referências (Pouco Divulgadas)

### Papers e Repositórios Acadêmicos
- **arXiv.org (Quantitative Finance)**: Fonte primária para novos algoritmos. Busque por "Deep Limit Order Book".
- **SSRN (Social Science Research Network)**: Papers sobre "Algorithmic Trading" e "Market Microstructure".

### Comunidades e Blogs Especializados
- **QuantConnect Community**: Discussões de alto nível sobre algotrading.
- **Kaggle Financial Competitions**: Códigos vencedores de competições de previsão de mercado (ex: Optiver Realized Volatility Prediction).
- **QuantStart / QuantInsti**: Artigos técnicos sobre implementação de estratégias.

### Traders/Quants de Referência (Internacional)
- **Marcos Lopez de Prado**: Referência em ML aplicado a finanças ("Advances in Financial Machine Learning").
- **Ernest P. Chan**: Estratégias quantitativas práticas.
- **HFT Research (GitHub)**: Buscar repositórios que implementam "Market Making" em C++ ou Rust para inspiração de lógica.

## 4. Estratégia e Metodologia (Inovação)
- **Diferencial**: Não usar apenas análise técnica tradicional (RSI, Médias). Focar em **Análise de Fluxo (Tape Reading Quantitativo)** e **Sentimento de Mercado**.
- **Uso de Hardware**: Utilizar a GPU para re-treinar modelos leves em tempo real (Online Learning) conforme o mercado muda durante o dia.

## 5. Integração de Dados (Fontes)

### B3 (Brasil) - via MetaTrader 5 (MT5)
- **Método**: Conexão IPC local com terminal MT5 rodando em background.
- **Cobertura**: Ações, Futuros (WIN, WDO), Opções.
- **Dados**:
  - Nível 1 (Tick Data): Último preço, Bid/Ask, Volume.
  - Nível 2 (Order Book): Profundidade de mercado completa (DOM).
- **Componente**: `src/collectors/mt5_market_data.py`

### Criptomoedas (Global 24/7) - via Binance
- **Método**: WebSocket (Stream) para dados em tempo real e REST API para snapshots.
- **Cobertura**: Criptomoedas (BTC, ETH, SOL, etc.) pareadas com USDT.
- **Dados**:
  - Order Book (Partial Depth): Top 20 níveis de preço com updates a cada 100ms.
- **Uso**: Permite testes de algoritmos de HFT e visualização de Heatmap 24 horas por dia, independente do horário de pregão da B3.
- **Componente**: `src/collectors/crypto_market_data.py`
