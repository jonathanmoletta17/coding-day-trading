# 🚀 Sistema de Trading Automatizado com MetaTrader 5

Sistema completo de coleta, armazenamento e análise de dados financeiros do MetaTrader 5, com arquitetura híbrida Windows/Linux (WSL).

## 📋 Visão Geral

```
┌──────────────────┐
│   Windows Host   │
│                  │
│  ┌────────────┐  │
│  │    MT5     │◄─┼─ MetaTrader 5 Terminal
│  └─────┬──────┘  │
│        │         │
│  ┌─────▼──────┐  │
│  │ MT5 Bridge │  │   FastAPI Service
│  │    API     │◄─┼─ http://localhost:8000
│  └─────┬──────┘  │
│        │         │
└────────┼─────────┘
         │ HTTP/WebSocket
┌────────▼─────────┐
│   WSL2 (Linux)   │
│                  │
│  ┌────────────┐  │
│  │   Data     │  │   Python Collector
│  │  Collector │◄─┼─ Consome Bridge API
│  └─────┬──────┘  │
│        │         │
│  ┌─────▼──────┐  │
│  │PostgreSQL  │  │   TimescaleDB
│  │  Database  │◄─┼─ Armazenamento
│  └────────────┘  │
 └──────────────────┘
```

## ✅ Status do Projeto

- [x] Conexão MT5 testada e funcionando
- [x] Schema PostgreSQL criado
- [x] MT5 Bridge API implementada
- [x] Data Collector implementado
- [x] Testes end-to-end criados
- [ ] Dashboard de visualização
- [ ] Estratégias de trading
- [ ] Backtesting engine

## 🛠️ Componentes

### 1. **MT5 Bridge Service** (Windows)
Serviço FastAPI que roda no Windows e expõe o MT5 via API REST/WebSocket.

**Arquivo:** `scripts/mt5_bridge_service.py`

**Endpoints:**
- `GET /health` - Status da conexão
- `GET /account` - Informações da conta
- `GET /symbols` - Lista de símbolos
- `GET /tick/{symbol}` - Último tick
- `GET /candles/{symbol}` - Dados históricos OHLCV
- `WS /ws/ticks` - Stream de ticks em tempo real

### 2. **Data Collector** (WSL/Linux)
Coleta dados do Bridge API e armazena no PostgreSQL.

**Arquivo:** `src/collectors/mt5_data_collector.py`

**Modos:**
- Carga histórica inicial
- Coleta contínua de ticks (HTTP)
- Coleta via WebSocket (recomendado)
- Atualização de candles

### 3. **PostgreSQL Database**
Banco TimescaleDB para armazenamento otimizado de dados de mercado.

**Schema:** `sql/schema.sql`

**Tabelas:**
- `symbols` - Catálogo de instrumentos
- `ticks` - Dados tick-by-tick
- `candles` - OHLCV por timeframe
- `orders`, `positions`, `deals` - Trading
- `indicators` - Indicadores técnicos
- `trade_signals` - Sinais de estratégias
- `backtests` - Resultados de backtests

## 🚀 Quick Start

### Pré-requisitos

**Windows:**
- MetaTrader 5 instalado
- Python 3.8+ instalado
- Credenciais MT5 (demo ou real)

**WSL/Linux:**
- Docker e Docker Compose
- Python 3.8+

### Passo 1: Configurar Variáveis de Ambiente

Edite o arquivo `.env`:

```bash
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=market_data
POSTGRES_PORT=55432
POSTGRES_HOST=localhost

# MetaTrader 5
MT5_LOGIN=5044246681
MT5_PASSWORD=!8JiJiOl
MT5_SERVER=MetaQuotes-Demo
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe

# Bridge API
MT5_BRIDGE_URL=http://localhost:8000

# Símbolos para coletar
SYMBOLS_TO_COLLECT=EURUSD,GBPUSD,USDJPY,XAUUSD
```

### Passo 2: Iniciar Banco de Dados (WSL)

```bash
# Subir o PostgreSQL via Docker
docker compose up -d

# Aplicar schema
PGPASSWORD=password psql -h localhost -p 55432 -U postgres -d market_data -f sql/schema.sql
```

### Passo 3: Instalar Dependências

**No Windows:**
```cmd
pip install fastapi uvicorn MetaTrader5 python-dotenv
```

**No WSL:**
```bash
pipin install -r requirements.txt
```

### Passo 4: Iniciar MT5 Bridge (Windows)

```cmd
cd C:\Users\jonathan-moletta
python test_mt5_simple.py  # Teste rápido (opcional)

# Inicie o bridge service
python mt5_bridge_service.py
```

O serviço estará disponível em: `http://localhost:8000`

### Passo 5: Testar Sistema End-to-End (WSL)

```bash
python scripts/test_end_to_end.py
```

Este script testa:
- ✓ Conexão PostgreSQL
- ✓ Schema do banco
- ✓ MT5 Bridge API
- ✓ Obtenção de dados da conta
- ✓ Obtenção de ticks
- ✓ Obtenção de candles
- ✓ Inserção de dados no banco

### Passo 6: Iniciar Coleta de Dados (WSL)

```bash
python src/collectors/mt5_data_collector.py
```

Escolha uma opção:
1. **Carga histórica inicial** - Carrega dados históricos (executar uma vez)
2. **Coleta contínua HTTP** - Polling de ticks
3. **Coleta via WebSocket** - Stream em tempo real (recomendado)
4. **Coleta de candles** - Atualização de OHLCV
5. **Todos** - Histórico + Tempo real

## 📊 Verificando os Dados

### Via psql (WSL)

```bash
PGPASSWORD=password psql -h localhost -p 55432 -U postgres -d market_data

-- Ver últimos ticks
SELECT * FROM v_latest_ticks LIMIT 10;

-- Ver últimas candles
SELECT * FROM v_latest_candles WHERE symbol = 'EURUSD' LIMIT 10;

-- Estatísticas
SELECT 
    s.symbol,
    COUNT(DISTINCT t.id) as total_ticks,
    COUNT(DISTINCT c.id) as total_candles
FROM symbols s
LEFT JOIN ticks t ON s.id = t.symbol_id
LEFT JOIN candles c ON s.id = c.symbol_id
GROUP BY s.symbol;
```

### Via PgAdmin

Acesse: `http://localhost:5050`

- Email: `admin@admin.com`
- Senha: `admin`

## 🧪 Testes

### Teste de Conexão MT5 (Windows)
```cmd
python test_mt5_simple.py
```

### Teste End-to-End (WSL)
```bash
python scripts/test_end_to_end.py
```

### Teste do Bridge API (qualquer)
```bash
# Health check
curl http://localhost:8000/health

# Informações da conta
curl http://localhost:8000/account

# Último tick EURUSD
curl http://localhost:8000/tick/EURUSD

# Candles H1
curl "http://localhost:8000/candles/EURUSD?timeframe=H1&count=10"
```

## 📁 Estrutura do Projeto

```
coding-day-trading/
├── .env                          # Variáveis de ambiente
├── docker-compose.yml            # PostgreSQL + PgAdmin
├── requirements.txt              # Dependências Python
│
├── src/                    # 🟢 NÚCLEO DE PRODUÇÃO (Lógica Crítica)
│   ├── microstructure/     # Engine de detecção de padrões e DSL
│   ├── analysis/           # Classificadores de contexto de mercado
│   ├── database/           # Abstração de persistência
│   └── collectors/         # Interfaces de coleta
│
├── infrastructure/         # 🏗️ SERVIÇOS DE RUNTIME (Daemons)
│   ├── mt5_bridge_service.py   # Ponte API Windows (FastAPI)
│   ├── mt5_data_collector.py   # Loop de coleta contínua
│   └── load_historical_data.py # ETL inicial
│
├── tests/                  # 🧪 TESTES AUTOMATIZADOS (CI/CD)
│   ├── integration/        # Testes E2E e validação de backend
│   └── unit/               # Testes isolados de lógica core
│
├── tools/                  # 🛠️ FERRAMENTAS DE DESENVOLVIMENTO
│   ├── diagnostics/        # Validadores de ambiente MT5 (0-3)
│   ├── runners/            # CLI runners para processos manuais
│   └── validation/         # Testes pontuais (SQL, UI Dashboard)
│
├── experiments/            # 🔬 PROTÓTIPOS E EXPLORAÇÃO
│   ├── mt5_exploration/    # Aprendizado da API MT5
│   └── stress_tests/       # Testes de carga não-funcionais
│
├── archive/                # 📦 DEPÓSITO DE CÓDIGO LEGADO (Histórico)
├── ADR/                    # 🏛️ REGISTROS DE DECISÃO ARQUITETURAL
└── docs/                   # Documentação detalhada
```

### Governança e Controle
Este projeto utiliza um **Contrato de Execução** e **Hooks de Git** para garantir integridade.
- Novos arquivos devem seguir a estrutura canônica.
- Commits são validados automaticamente por `.githooks/pre-commit`.
- Consulte `GOVERNANCE_INDEX.md` antes de contribuir.

### Componentes Principais

#### 1. MT5 Bridge Service (`infrastructure/mt5_bridge_service.py`)
Serviço REST/WebSocket que roda no Windows e expõe a API do MetaTrader 5 para o ambiente WSL/Linux.
- Porta: 8000
- Endpoints: `/account`, `/ticks`, `/candles`, `/orderbook`

#### 2. MT5 Data Collector (`infrastructure/mt5_data_collector.py`)
Serviço daemon que consome a Bridge API e persiste dados no TimescaleDB.

#### 3. DSL Pattern Engine (`src/microstructure/dsl_v01.py`)
Núcleo da análise de microestrutura. Processa eventos de tick e detecta padrões de liquidez (ex: `LiquiditySweep`, `BookPressure`).

---

## Como Executar

Consulte o [Guia de Migração](MIGRATION_GUIDE.md) para comandos atualizados.

### Testes Rápidos
```bash
# Testes unitários (Lógica Core)
PYTHONPATH=. python tests/unit/test_dsl_v01_unittest.py

# Diagnóstico de Infraestrutura
python tools/diagnostics/1_check_connection.py
```

## 🔧 Troubleshooting

### MT5 Bridge não está acessível

**Problema:** `Connection refused` ao acessar `http://localhost:8000`

**Solução:**
1. Certifique-se de que `mt5_bridge_service.py` está rodando no Windows
2. Verifique o firewall do Windows
3. Confirme que a porta 8000 não está em uso

### PostgreSQL não conecta

**Problema:** `Connection refused` ao conectar no PostgreSQL

**Solução:**
```bash
# Verifique se o container está rodando
docker compose ps

# Se não estiver, inicie
docker compose up -d

# Verifique os logs
docker compose logs timescaledb
```

### Erro ao inserir ticks

**Problema:** `Foreign key violation` ou `symbol not found`

**Solução:**
```bash
# Certifique-se de que o símbolo existe
PGPASSWORD=password psql -h localhost -p 55432 -U postgres -d market_data \
  -c "SELECT get_or_create_symbol('EURUSD');"
```

### WebSocket desconecta

**Problema:** WebSocket fecha inesperadamente

**Solução:**
1. Aumente o timeout no collector
2. Implemente reconnect automático
3. Verifique logs do bridge service

## 📈 Próximos Passos

### Implementação Imediata

1. **Dashboard de Visualização**
   - Gráficos de candles em tempo real
   - Indicadores técnicos
   - Monitoramento de performance

2. **Indicadores Técnicos**
   - SMA, EMA, MACD, RSI, Bollinger Bands
   - Armazenamento pré-calculado
   - API para consulta rápida

3. **Estratégias de Trading**
   - Framework de estratégias
   - Backtesting engine
   - Geração de sinais

### Médio Prazo

4. **Otimizações**
   - Particionamento de tabelas por data
   - Indexação avançada
   - Compressão de dados antigos

5. **Alertas e Notificações**
   - Telegram/Discord bot
   - Email alerts
   - Push notifications

6. **Gestão de Risco**
   - Cálculo de position sizing
   - Stop loss dinâmico
   - Risk/reward analysis

## 📝 Documentação Adicional

- [Instruções de Teste MT5](docs/MT5_TEST_INSTRUCTIONS.md)
- [Resultados do Teste](docs/MT5_TEST_RESULTS.md)
- [API Documentation](http://localhost:8000/docs) - Swagger UI (quando bridge estiver rodando)

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto é privado e proprietário.

## 📧 Contato

Jonathan Moletta - Sistema de Trading Automatizado

---

**⚠️ Aviso Legal:** Este sistema é para fins educacionais e de pesquisa. Trading envolve risco significativo de perda. Não use em contas reais sem testes extensivos.
