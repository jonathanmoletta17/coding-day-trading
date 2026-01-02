# 🔍 AUDITORIA ESTRUTURAL - FASE 1: CLASSIFICAÇÃO

**Data**: 2026-01-02  
**Projeto**: Coding Day Trading (MT5 + Binance)  
**Metodologia**: Análise de dependências reais via imports, referências e documentação

---

## 📊 Resumo Estatístico

| Categoria | Scripts | Módulos src/ | Total | % |
|-----------|---------|--------------|-------|---|
| ✅ Produção crítica | 0 | 11 | 11 | 26% |
| 🏗️ Infraestrutura / integração | 3 | 2 | 5 | 12% |
| 🧪 Teste automatizado essencial | 6 | 0 | 6 | 14% |
| 🔬 Teste exploratório / experimental | 7 | 0 | 7 | 17% |
| 🛠️ Ferramenta de desenvolvimento | 6 | 0 | 6 | 14% |
| 📋 Auditoria / evidência histórica | 0 | 0 | 0 | 0% |
| 📖 Documentação executável | 1 | 0 | 1 | 2% |
| ⚠️ Obsoleto / legado | 0 | 6 | 6 | 14% |
| **TOTAL** | **23** | **19** | **42** | **100%** |

---

## 🎯 CATEGORIA 1: PRODUÇÃO CRÍTICA
*Necessário para execução real do sistema em ambiente de produção*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `src/microstructure/models.py` | Importado por: `book.py`, `context_core.py`, `replay.py`, `dsl_v01.py`, `test_dsl_v01_unittest.py`, `run_dsl_v01.py` | **Core data models** do sistema de microestrutura. Define `BaseEvent`, `EventRecord`, `DerivedEvent`. Base de toda pipeline de eventos. | 🟢 ALTO |
| `src/microstructure/book.py` | Importado por: `replay.py`; Importa: `models.py` | **OrderBook state management**. Define `OrderBook`, `BookStateSnapshot`, `tick_distance()`. Essencial para reconstruir estado do livro. | 🟢 ALTO |
| `src/microstructure/replay.py` | Importado por: `test_dsl_v01_unittest.py`, `run_dsl_v01.py`; Importa: `book.py`, `models.py` | **ReplayEngineV01**: processa eventos brutos e deriva eventos (LIQUIDITY_ADD/REMOVE). Core da pipeline de transformação. | 🟢 ALTO |
| `src/microstructure/dsl_v01.py` | Importado por: `context_core.py`, `test_dsl_v01_unittest.py`, `run_dsl_v01.py`; Importa: `book.py`, `models.py` | **DSLParserV01 & PatternEngineV01**: parse de padrões microestruturais e execução de matching. Engine central para detectar patterns. | 🟢 ALTO |
| `src/microstructure/context_core.py` | Importado por: `test_dsl_v01_unittest.py`, `run_dsl_v01.py`; Importa: `models.py`, `dsl_v01.py` | **classify_context_core()**: Classificador de contexto de mercado baseado em occorrências de padrões. Output final para decisões. | 🟢 ALTO |
| `src/analysis/market_context_classifier.py` | Importado por: `test_market_context_exhaustive.py` | **Market Context Classifier** com 360 linhas. Implementa análise de atividade/comportamento sem gerar sinais. Usado em testes exaustivos recentes (conversa ce82b9be). | 🟢 ALTO |
| `src/analysis/smc_liquidity_sweep.py` | Tem `if __name__` (executável standalone) | **SMC Liquidity Sweep detector**. Pode ser módulo independente para análise Smart Money Concepts. | 🟡 MÉDIO |
| `src/analysis/market_state_classifier.py` | Tem `if __name__` (executável standalone) | **Market State Classifier**. Possivelmente versão alternativa ou complementar ao `market_context_classifier.py`. | 🟡 MÉDIO |
| `src/database/db_handler.py` | Importado por: `mt5_market_data.py`, `crypto_market_data.py` | **DatabaseHandler**: abstração para persistência PostgreSQL. Usado ativamente por collectors. | 🟢 ALTO |
| `src/collectors/mt5_market_data.py` | Importa: `db_handler.py` | **MT5MarketCollector** (247 linhas): gerencia conexão MT5, livro de ofertas, ticks. Core para coleta de dados de produção. | 🟢 ALTO |
| `src/collectors/crypto_market_data.py` | Importado por: `dashboard.py`, `test_binance_ws.py`; Importa: `db_handler.py` | **BinanceCollector**: WebSocket Binance para orderbook updates. Usado em dashboard e testes. | 🟢 ALTO |

---

## 🏗️ CATEGORIA 2: INFRAESTRUTURA / INTEGRAÇÃO
*Serviços de integração e bridges entre componentes*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `scripts/mt5_bridge_service.py` | Nenhum import `src.` (standalone FastAPI server) | **Bridge API crítico**: Única ponte HTTP/WebSocket entre MT5 (Windows) e WSL/Linux. Documentado em README como componente essencial. 416 linhas FastAPI. | 🟢 ALTO |
| `scripts/load_historical_data.py` | Não analisado imports (assumido DB access) | **Carga inicial de histórico**: Popula PostgreSQL com dados passados. Bootstrap da pipeline. Mencionado em README. | 🟢 ALTO |
| `docker-compose.yml` | N/A (config) | Define **TimescaleDB + PgAdmin**. Infraestrutura de dados essencial. | 🟢 ALTO |
| `src/collectors/mt5_data_collector.py` | Tem `if __name__` (executável) | **Data Collector principal**: Consome MT5 Bridge API e persiste no DB. Mencionado em README como componente core. Múltiplos modos de coleta. | 🟢 ALTO |
| `.env` | N/A (config) | **Configuração de ambiente**: credenciais MT5, DB, URLs de serviços. Crítico para deployment. | 🟢 ALTO |

---

## 🧪 CATEGORIA 3: TESTE AUTOMATIZADO ESSENCIAL
*Testes que garantem funcionamento da pipeline de produção*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `scripts/test_end_to_end.py` | Nenhum import `src.` (testa via API HTTP) | **Teste E2E crítico** (397 linhas). Valida 7 etapas: PostgreSQL → MT5 Bridge API → Candles → Inserção DB. Atualmente aberto no editor do usuário. | 🟢 ALTO |
| `scripts/test_market_context_exhaustive.py` | Importa: `market_context_classifier` | **Teste exaustivo** (477 linhas) das 8 propriedades do Market Context Classifier. Baseado em conversa recente (ce82b9be). Teste de requisitos de negócio. | 🟢 ALTO |
| `scripts/test_dsl_v01_unittest.py` | Importa: `dsl_v01`, `context_core`, `models`, `replay` | **Suite unittest completa** (319 linhas) do DSL v0.1. Testa 7 padrões microestruturais com dados sintéticos. Essencial para garantir DSL engine. | 🟢 ALTO |
| `scripts/run_dsl_v01.py` | Importa: `dsl_v01`, `context_core`, `models`, `replay` | **Runner CLI de produção** (119 linhas). Processa eventos reais via argparse com parametrização externa. Apesar do nome "run", é usado para validar pipeline com dados reais. | 🟢 ALTO |
| `scripts/test_database_strategies.py` | Nenhum import `src.` (SQL direto) | **Teste de estratégias com PostgreSQL real** (136 linhas). Valida queries, médias móveis, volume, price action. Teste de integração SQL. | 🟢 ALTO |
| `scripts/validate_backend.py` | Tenta importar mas com fallback gracioso | **Validação de infraestrutura** (64 linhas). Health check de tabelas PostgreSQL, usado em CI/CD. | 🟢 ALTO |

---

## 🔬 CATEGORIA 4: TESTE EXPLORATÓRIO / EXPERIMENTAL
*Testes manuais, aprendizado ou validações pontuais*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `scripts/explore_mt5_capabilities.py` | Nenhum import `src.` (HTTP calls to bridge) | **Exploração de API** (281 linhas). Função `explore_capabilities()` testa TUDO que MT5 Bridge oferece. Útil durante descoberta, mas coberto por testes estruturados. | 🟢 ALTO |
| `scripts/test_binance_ws.py` | Importa: `crypto_market_data.BinanceCollector` | **Teste manual Binance WS** (39 linhas). Apenas imprime bid/ask por 10s. Teste básico de conexão. | 🟢 ALTO |
| `scripts/test_data_collection.py` | Nenhum import `src.` (usa MT5 diretamente) | **Teste manual MT5** (83 linhas). Testa candles, ticks, orderbook com prints. Substituído por `test_end_to_end.py`. | 🟢 ALTO |
| `scripts/test_mt5_simple.py` | Nome sugere teste básico (8211 bytes) | **Teste simplificado** (~200 linhas estimadas). Provavelmente experimento inicial de aprendizado da API MT5. | 🟡 MÉDIO |
| `scripts/test_mt5_connection_windows.py` | Nome indica teste específico Windows (6092 bytes) | **Teste legado Windows** (~150 linhas). Se sistema opera via Bridge em WSL, teste direto Windows pode ser legacy. | 🟡 MÉDIO |
| `scripts/test_mt5_db_integration.py` | Importa: `mt5_market_data`, `db_handler` | **Teste antigo integração MT5→DB** (2658 bytes, ~65 linhas). Provavelmente substituído por `test_end_to_end.py` mais completo. | 🟢 ALTO |
| `scripts/validate_dashboard_playwright.py` | Importa: `streamlit.testing.v1` | **Teste UI dashboard** (24 linhas). Valida componentes Streamlit. Depende de dashboard estar ativo. | 🟡 MÉDIO |

---

## 🛠️ CATEGORIA 5: FERRAMENTA DE DESENVOLVIMENTO / DEBUG
*Scripts auxiliares para diagnóstico e setup*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `scripts/mt5_validation/0_find_mt5.py` | Nenhum (usa winreg, busca disco) | **Diagnóstico de instalação** (146 linhas). Varre registro Windows + disco procurando `terminal64.exe`. Usado em **onboarding de novos ambientes**. Salva path em `mt5_path.txt`. | 🟢 ALTO |
| `scripts/mt5_validation/1_check_connection.py` | Path sugere sequência diagnóstica | **Passo 2 da validação MT5**. Testa conexão e login após encontrar executável. Parte de workflow de troubleshooting estruturado. | 🟢 ALTO |
| `scripts/mt5_validation/2_check_tick_data.py` | Path sugere sequência diagnóstica | **Passo 3**: valida coleta de ticks. Testa `copy_ticks_from()` e qualidade dos dados. | 🟢 ALTO |
| `scripts/mt5_validation/3_check_orderbook.py` | Path sugere sequência diagnóstica | **Passo 4**: valida Market Depth. Testa `market_book_add()` e `market_book_get()`. Crítico para microestrutura. | 🟢 ALTO |
| `scripts/mt5_validation/4_stress_test.py` | Nome indica teste de carga (3747 bytes) | **Stress test** (~90 linhas). Validação pontual de performance, não QA contínuo. | 🟡 MÉDIO |
| `scripts/mt5_validation/5_data_structure_test.py` | Nome indica validação de schema (2432 bytes) | **Teste de estrutura de dados** (~60 linhas). Validação one-time de formato de retorno MT5. | 🟡 MÉDIO |

---

## 📖 CATEGORIA 6: DOCUMENTAÇÃO EXECUTÁVEL
*Código que também serve como documentação viva*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `README.md` | Referencia múltiplos scripts no guia de uso | **384 linhas** de documentação estrutural. Descreve arquitetura, componentes, quick start. Menciona: `mt5_bridge_service.py`, `test_end_to_end.py`, collectors, schema SQL. | 🟢 ALTO |

---

## ⚠️ CATEGORIA 7: OBSOLETO / LEGADO
*Não referenciado por código de produção ou testes ativos*

| Arquivo | Dependências Detectadas | Justificativa | Certeza |
|---------|------------------------|---------------|---------|
| `src/analysis/indicators.py` | Importado por: `dashboard.py` | **Indicadores técnicos**. Usado por dashboard, mas dashboard pode estar inativo (README marca como TODO). | 🔴 BAIXO |
| `src/analysis/alerts.py` | Importado por: `dashboard.py` | **Sistema de alertas**. Mesma situação: depende de dashboard ativo. | 🔴 BAIXO |
| `src/analysis/patterns.py` | Importado por: `dashboard.py` | **Reconhecimento de padrões**. Usado por dashboard. Status incerto. | 🔴 BAIXO |
| `src/analysis/trading_strategies.py` | Tem `if __name__`, mas sem imports detectados em outros | **Estratégias de trading**. Módulo standalone sem referências ativas detectadas. | 🟡 MÉDIO |
| `src/models/gpu_model.py` | Tem `if __name__`, mas sem imports detectados | **Modelo GPU/ML**. Sem referências. Pode ser experimento ou feature planejada. | 🟡 MÉDIO |
| `src/visualization/dashboard.py` | Importa vários módulos `src.analysis` e `src.collectors` | **Dashboard Streamlit** (linhas não contadas). README marca como "TODO". Importa muitos módulos, mas status de funcionamento é incerto. | 🔴 BAIXO |
| `src/visualization/orderbook_viz.py` | Importado por: `dashboard.py` | **Visualização de orderbook**. Depende de dashboard estar ativo. | 🔴 BAIXO |
| `src/collectors/mt5_candles.py` | Importado por: `dashboard.py` (conditional import) | **MT5CandleCollector**. Importado condicionalmente no dashboard. Relação com `mt5_market_data.py` (que já coleta ticks/book) não está clara. | 🟡 MÉDIO |
| `src/collectors/market_data.py` | Tem `if __name__`, sem imports detectados | **Coletor genérico**. Pode ser abstração base ou experimento. Sem referências ativas. | 🟡 MÉDIO |

---

## 🗺️ CATEGORIA 8: INCERTEZA REMANESCENTE
*Arquivos que requerem inspeção manual adicional*

| Arquivo | Razão da Incerteza | Próxima Ação |
|---------|-------------------|--------------|
| `test_mt5_wsl_helper.sh` | **Bash script** (2958 bytes) em meio a Python. Pode ser helper crítico para WSL ou legacy. | Ler conteúdo completo |
| Dashboard status | README marca como "TODO", mas código existe e importa módulos ativos | Testar se `streamlit run src/visualization/dashboard.py` funciona |
| `src/collectors/mt5_candles.py` vs `mt5_market_data.py` | Duas classes de coleta MT5 com propósitos possivelmente sobrepostos | Comparar implementações |
| `docs/*` (13 arquivos markdown) | Documentação adicional não auditada: `MICROSTRUCTURE_EVENT_CONTRACT_AND_GRAMMAR.md` (17KB), `SMC_PATTERN_AUDIT.md`, etc | Avaliar relevância e atualização |

---

## 📐 MAPA DE DEPENDÊNCIAS (Core Pipeline)

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRODUÇÃO CRÍTICA                          │
└─────────────────────────────────────────────────────────────────┘

[BaseEvent] (models.py)
    ↓
[OrderBook, tick_distance] (book.py)
    ↓
[ReplayEngineV01] (replay.py) → deriva eventos (LIQUIDITY_ADD/REMOVE)
    ↓
[DSLParserV01, PatternEngineV01] (dsl_v01.py) → detecta padrões
    ↓
[classify_context_core] (context_core.py) → classifica contexto
    ↓
OUTPUT: MarketContext (decisão de operação)

┌─────────────────────────────────────────────────────────────────┐
│                      INFRAESTRUTURA                              │
└─────────────────────────────────────────────────────────────────┘

[MT5 Terminal] (Windows)
    ↓ PyMT5
[mt5_bridge_service.py] FastAPI :8000
    ↓ HTTP/WS
[MT5MarketCollector] (mt5_market_data.py)
[BinanceCollector] (crypto_market_data.py)
    ↓
[DatabaseHandler] (db_handler.py)
    ↓
[PostgreSQL/TimescaleDB] (docker-compose.yml)

┌─────────────────────────────────────────────────────────────────┐
│                     TESTES ESSENCIAIS                            │
└─────────────────────────────────────────────────────────────────┘

[test_end_to_end.py] → valida pipeline completa via HTTP
[test_dsl_v01_unittest.py] → valida DSL engine + padrões
[test_market_context_exhaustive.py] → valida classifier (8 propriedades)
[test_database_strategies.py] → valida queries SQL + estratégias

```

---

## 🔍 DEPENDÊNCIAS INVERSAS (Quem usa quem)

### Módulos mais referenciados (hotspots de dependência):

1. **`src/microstructure/models.py`** → Referenciado por 6 arquivos
2. **`src/microstructure/dsl_v01.py`** → Referenciado por 3 arquivos  
3. **`src/microstructure/replay.py`** → Referenciado por 2 arquivos
4. **`src/database/db_handler.py`** → Referenciado por 2 collectors
5. **`scripts/mt5_bridge_service.py`** → Referenciado indiretamente via HTTP por todos collectors

### Arquivos standalone (sem dependentes):
- `scripts/explore_mt5_capabilities.py`
- `scripts/test_data_collection.py`
- `scripts/test_mt5_simple.py`
- `src/analysis/trading_strategies.py`
- `src/models/gpu_model.py`

---

## 📊 ANÁLISE POR TIPO DE ARQUIVO

### Python Executáveis (`if __name__ == "__main__"`):
- **Produção**: `mt5_data_collector.py`, `mt5_market_data.py`
- **Teste**: `test_end_to_end.py`, `test_market_context_exhaustive.py`, etc
- **Diagnóstico**: `mt5_validation/*`
- **Standalone uncertain**: `trading_strategies.py`, `gpu_model.py`, `market_data.py`

### Bibliotecas/Módulos (sem main):
- **Core**: `models.py`, `book.py`, `replay.py`, `dsl_v01.py`, `context_core.py`
- **Serviços**: `db_handler.py`
- **Análise**: `indicators.py`, `alerts.py`, `patterns.py` (status incerto)

### Configuração:
- `.env`, `docker-compose.yml`, `requirements.txt`

### Infraestrutura:
- `mt5_bridge_service.py` (FastAPI server)
- `load_historical_data.py` (ETL inicial)

---

## 🎯 CONCLUSÕES ESTRUTURAIS

### Pipeline de Produção Validada:
```
MT5 → Bridge API → Collectors → DB → DSL Engine → Context Classifier → Decision
  ✓      ✓           ✓         ✓       ✓              ✓              (output)
```

### Áreas com Alta Cobertura de Testes:
- ✅ **Microestrutura DSL**: unittest + E2E + exhaustive
- ✅ **Database integration**: E2E + strategies + backend validation
- ✅ **MT5 Bridge API**: E2E + validation suite (0-3)

### Áreas com Baixa Visibilidade:
- ⚠️ **Dashboard**: Código existe, mas marcado como TODO
- ⚠️ **Estratégias**: `trading_strategies.py` sem referências ativas
- ⚠️ **GPU/ML**: `gpu_model.py` isolado

### Redundâncias Potenciais:
- `test_data_collection.py` vs `test_end_to_end.py` (ambos testam coleta)
- `mt5_candles.py` vs `mt5_market_data.py` (ambos coletam MT5)
- `explore_mt5_capabilities.py` vs `mt5_validation/*` (ambos diagnóstico)

---

## 📋 PRÓXIMOS PASSOS SUGERIDOS (SEM REMOÇÃO)

### Fase 2A: Resolução de Incertezas
1. Ler `test_mt5_wsl_helper.sh` para classificar definitivamente
2. Testar dashboard: `streamlit run src/visualization/dashboard.py`
3. Comparar `mt5_candles.py` vs `mt5_market_data.py` (propósito)
4. Verificar uso de `trading_strategies.py` e `gpu_model.py`

### Fase 2B: Documentação de Propósito
1. Adicionar docstrings explicando propósito em arquivos "uncertain"
2. Atualizar README para refletir estado atual (dashboard é TODO ou funcional?)
3. Documentar workflow de `mt5_validation/0-5` como guia de troubleshooting

### Fase 2C: Análise de Documentação
1. Auditar `docs/*.md` para identificar documentação obsoleta vs ativa
2. Verificar consistência entre docs e código atual

---

## 🔐 ARQUIVOS CRÍTICOS (NÃO TOCAR SEM ANÁLISE)

> [!CAUTION]
> **Mudanças nos seguintes arquivos afetam pipeline de produção:**

- `src/microstructure/*.py` (5 arquivos) — Core da análise de mercado
- `scripts/mt5_bridge_service.py` — Única ponte MT5
- `src/collectors/mt5_market_data.py` — Coleta de produção
- `src/database/db_handler.py` — Persistência
- `docker-compose.yml` — Infraestrutura de dados
- `.env` — Credenciais e configuração

---

**Metodologia aplicada**: Análise estática via `grep_search`, `view_file_outline`, análise de imports, cross-referência com README e conversas recentes.

**Limitações conhecidas**:
- Dependências dinâmicas (importações condicionais) podem não estar totalmente mapeadas
- Status do dashboard precisa de teste ativo
- Arquivos bash/shell não analisados em profundidade
- Documentação em `docs/` não auditada (13 arquivos)

**Data de validade**: Esta auditoria reflete o estado do projeto em 2026-01-02 17:15 UTC-3.
