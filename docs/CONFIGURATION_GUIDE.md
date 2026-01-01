# Guia de Configuração e Instalação

## Visão Geral
Este documento detalha as configurações realizadas para reinstalar e configurar o projeto no ambiente Windows com MetaTrader 5 (MT5).

## 1. Dependências Instaladas
As seguintes bibliotecas foram instaladas via `pip install -r requirements.txt`:
- **Core**: `numpy`, `pandas`, `requests`
- **Trading**: `MetaTrader5`, `yfinance`, `ta-lib`
- **Machine Learning**: `torch` (CUDA 11.8), `scikit-learn`
- **Visualização**: `streamlit`, `plotly`, `matplotlib`, `seaborn`
- **Banco de Dados**: `psycopg2-binary`, `sqlalchemy`
- **Testes**: `playwright`, `pytest`

## 2. Configuração do MetaTrader 5 (MT5)
O sistema foi configurado para localizar automaticamente a instalação do MT5.

- **Localização**: O executável foi encontrado em `C:\Program Files\MetaTrader 5\terminal64.exe`.
- **Validação**: Scripts de validação estão disponíveis em `scripts/mt5_validation/`.
- **Credenciais**: Para permitir a conexão automatizada, é necessário preencher as seguintes variáveis no arquivo `.env`:
  ```ini
  MT5_LOGIN=seu_login
  MT5_PASSWORD=sua_senha
  MT5_SERVER=seu_servidor
  MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
  ```
  > **Nota**: Sem essas credenciais, o script de conexão retorna erro de autorização (-6).

### 2.1. Validação de Conexão (Realizada)
A conexão foi testada com sucesso utilizando as credenciais fornecidas:
- **Conta**: 5044246681
- **Servidor**: MetaQuotes-Demo
- **Status**: ✅ Conectado e Autenticado
- **Dados**: Leitura de símbolos e saldo (100k USD) confirmada.

Evidências visuais (Screenshots) foram verificadas confirmando o login no terminal.

## 3. Configuração do Banco de Dados (PostgreSQL)
Detectou-se uma instância local do PostgreSQL rodando na porta **5432**.

- **Ajuste Realizado**: O arquivo `.env` foi atualizado para usar a porta `5432` (anteriormente 5433 para Docker).
- **Ação Necessária**: A autenticação falhou com a senha padrão (`password`). É necessário atualizar a senha no arquivo `.env`:
  ```ini
  POSTGRES_USER=postgres
  POSTGRES_PASSWORD=sua_senha_correta
  POSTGRES_DB=market_data
  POSTGRES_PORT=5432
  POSTGRES_HOST=localhost
  ```

## 4. Validação do Sistema
### Dashboard
O dashboard Streamlit foi validado e carrega corretamente em `http://localhost:8501`.
- Para iniciar: `streamlit run src/visualization/dashboard.py`

### Scripts de Teste
- **Validar Conexão MT5**: `python scripts/mt5_validation/1_check_connection.py`
- **Validar Backend/DB**: `python scripts/validate_backend.py`
- **Validar Dashboard**: `python scripts/validate_dashboard_playwright.py`

## 5. Próximos Passos
1. Preencher as credenciais no arquivo `.env`.
2. Executar `python scripts/validate_backend.py` para confirmar a conexão com o banco.
3. Executar `python scripts/mt5_validation/1_check_connection.py` para confirmar o login no MT5.
