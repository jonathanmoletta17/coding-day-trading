# Roadmap do Projeto: Sistema B3 High-Performance

## Fase 1: Fundação e Estrutura (Atual)
- [x] Definição da estrutura de pastas.
- [x] Criação da documentação inicial.
- [ ] Implementação do coletor de dados básico (yfinance).
- [ ] Setup do ambiente de desenvolvimento (Python + CUDA).

## Fase 2: Coleta e Processamento de Dados
- [ ] Integração com API de dados em tempo real (MetaTrader5 ou API proprietária B3).
- [ ] Construção de pipeline de dados (ETL) para normalização.
- [ ] Armazenamento eficiente (HDF5 ou Parquet) para grandes volumes de dados históricos.
- [ ] Implementação de indicadores técnicos (RSI, MACD, Bollinger, VWAP) usando GPU se possível (via CuPy ou Torch).

## Fase 3: Visualização Avançada
- [ ] Dashboard em Streamlit com atualização em tempo real.
- [ ] Gráficos de Candle interativos com Plotly.
- [ ] Heatmaps de correlação e volatilidade.
- [ ] Visualização de Order Flow (Fluxo de Ordens) e Book de Ofertas.

## Fase 4: Inteligência Artificial e Modelagem
- [ ] Pesquisa de arquiteturas de Deep Learning para séries temporais (LSTMs, Transformers, TCNs).
- [ ] Treinamento de modelos utilizando a RTX A4000.
- [ ] Backtesting de estratégias baseadas em predições do modelo.
- [ ] Implementação de Reinforcement Learning para otimização de execução.

## Fase 5: Execução e Automação
- [ ] Integração com sistema de roteamento de ordens.
- [ ] Implementação de regras de Risco (Risk Management).
- [ ] Paper Trading (Simulação em tempo real).
- [ ] Go Live (Operação real com capital controlado).

## Áreas de Estudo Contínuo
- Market Microstructure (Microestrutura de Mercado).
- High Frequency Trading (HFT) techniques.
- Quantitative Finance papers (arXiv, SSRN).
