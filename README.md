# Sistema B3 Real-Time Analysis (Trae AI + GPU)

Este projeto é um sistema de análise de mercado financeiro de alta performance, focado na B3 (Bolsa do Brasil), utilizando a metodologia de Agentes de IA para auxiliar na tomada de decisão.

## 🎯 Objetivo
Eliminar incertezas de mercado através de análise quantitativa avançada, processamento de dados em tempo real e uso intensivo de GPU para modelos preditivos.

## 🏗 Estrutura do Projeto

- `config/`: Arquivos de configuração (parâmetros de modelos, chaves de API).
- `data/`: Armazenamento de dados brutos e processados.
- `docs/`: Documentação, roadmap e base de conhecimento.
- `notebooks/`: Jupyter Notebooks para exploração e prototipagem.
- `src/`: Código fonte do sistema.
  - `collectors/`: Scripts para coleta de dados (API B3, yfinance, etc.).
  - `processors/`: Limpeza e transformação de dados.
  - `models/`: Modelos de Machine Learning/Deep Learning (PyTorch/GPU).
  - `visualization/`: Dashboards interativos e gráficos avançados.
  - `strategies/`: Lógica de trading e algoritmos.

## 🚀 Tecnologias
- **Linguagem**: Python 3.10+
- **Coleta**: yfinance (inicial), MetaTrader5 (futuro), Websockets.
- **Visualização**: Plotly, Streamlit/Dash.
- **ML/AI**: PyTorch (CUDA enabled), Scikit-learn.
- **Hardware**: Otimizado para 64GB RAM + NVIDIA RTX A4000.

## 📚 Como usar
1. Instale as dependências: `pip install -r requirements.txt`
2. Configure suas credenciais em `config/`.
3. Execute os coletores: `python src/collectors/market_data.py`
4. Inicie o dashboard: `streamlit run src/visualization/dashboard.py`
