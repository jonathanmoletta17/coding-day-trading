# 💥 AUDITORIA ESTRUTURAL - FASE 2: ANÁLISE DE IMPACTO

**Data**: 2026-01-02  
**Projeto**: Coding Day Trading (MT5 + Binance)  
**Base**: Classificação estrutural da Fase 1  
**Postura**: Conservadora (sistema financeiro com risco de perda de capital)

---

## 🎯 Metodologia de Avaliação

### Escala de Impacto

| Nível | Financeiro | Operacional | Risco | Uso |
|-------|-----------|-------------|-------|-----|
| **🔴 CRÍTICO** | Perda direta de capital ou impossibilidade de operar | Pipeline quebrada, sistema não inicia | Sem auditoria, risco regulatório | Uso contínuo/frequente |
| **🟠 MODERADO** | Degradação de qualidade de decisão | Funcionalidade parcial, workarounds possíveis | Dificulta debug, aumenta tempo de recovery | Uso periódico |
| **🟡 BAIXO** | Sem impacto direto em decisões | Funcionalidade secundária afetada | Dificulta setup inicial apenas | Uso raro/pontual |
| **⚪ NULO** | Sem relação com operações ativas | Sem dependentes ativos | Sem uso em troubleshooting | Sem uso detectado |

---

## 📊 RESUMO EXECUTIVO DE IMPACTOS

| Categoria Original | Arquivos | Impacto Crítico | Impacto Moderado | Impacto Baixo | Impacto Nulo |
|-------------------|----------|-----------------|------------------|---------------|--------------|
| Produção crítica | 11 | 11 (100%) | 0 | 0 | 0 |
| Infraestrutura | 5 | 5 (100%) | 0 | 0 | 0 |
| Teste automatizado essencial | 6 | 0 | 4 (67%) | 2 (33%) | 0 |
| Teste exploratório | 7 | 0 | 0 | 2 (29%) | 5 (71%) |
| Ferramenta dev/debug | 6 | 0 | 4 (67%) | 2 (33%) | 0 |
| Documentação executável | 1 | 0 | 1 (100%) | 0 | 0 |
| Obsoleto/legado | 9 | 0 | 0 | 0 | 9 (100%)* |

*Assumindo que já foram desativados de produção

---

## 🔴 CATEGORIA 1: PRODUÇÃO CRÍTICA (11 arquivos)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `src/microstructure/models.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Base de todo sistema de eventos**. Remoção = colapso total. Define contratos de dados usados em decisões de trading. Sem ele, nenhum padrão microestrutural pode ser detectado. |
| `src/microstructure/book.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Reconstrução do orderbook**. Essencial para análise de liquidez e detecção de sweeps. Erros aqui = decisões baseadas em estado incorreto do mercado = perda financeira. |
| `src/microstructure/replay.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Derivação de eventos LIQUIDITY_ADD/REMOVE**. Pipeline de transformação central. Sem ele, sistema recebe eventos brutos mas não consegue processar padrões. |
| `src/microstructure/dsl_v01.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Pattern Engine**. Detecta os 7 padrões microestruturais (Depletion, Erosion, etc). Lógica core de análise de mercado. Falha = sistema cego para padrões = operação manual ou random. |
| `src/microstructure/context_core.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Classificador de contexto final**. Output direto para decisão de operar ou não. Falha = decisões sem contexto = risco de operar em condições adversas. |
| `src/analysis/market_context_classifier.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **360 linhas de lógica de classificação**. Separa atividade/comportamento. Validado exaustivamente (8 propriedades). Usado em produção para evitar sinais falsos. |
| `src/analysis/smc_liquidity_sweep.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🟠 **MODERADO** | Frequente | **SMC Liquidity Sweep detector**. Se usado em estratégia ativa, impacto crítico. Sweeps são eventos chave para reversões. Incerteza sobre uso ativo reduz confiança. |
| `src/analysis/market_state_classifier.py` | 🟠 **MODERADO** | 🟠 **MODERADO** | 🟠 **MODERADO** | Desconhecido | **Segundo classificador**. Pode ser versão alternativa ou complementar. Sem referências detectadas = incerteza. Conservador = moderado até confirmar não uso. |
| `src/database/db_handler.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Abstração de persistência**. Usado por todos collectors. Sem ele = dados não salvos = sem histórico = sem backtesting = sem auditoria. Violação de governança. |
| `src/collectors/mt5_market_data.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **247 linhas de coleta MT5**. Gerencia conexão, orderbook, ticks. Fonte primária de dados de mercado. Falha = sistema cego. |
| `src/collectors/crypto_market_data.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **BinanceCollector**. Se sistema opera crypto via Binance, é crítico. WebSocket para orderbook updates em tempo real. |

### 💡 Insight Crítico:
> Todos os 11 arquivos de produção têm **impacto crítico em pelo menos 2 dimensões**. Qualquer falha resulta em degradação severa ou colapso do sistema de decisão.

---

## 🏗️ CATEGORIA 2: INFRAESTRUTURA / INTEGRAÇÃO (5 arquivos)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `scripts/mt5_bridge_service.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Única ponte MT5 ↔ Linux/WSL**. 416 linhas FastAPI. Sem ele, sistema WSL não acessa MT5 = sem dados = sistema parado. Não há redundância. SPOF (Single Point of Failure). |
| `scripts/load_historical_data.py` | 🟡 **BAIXO** | 🟠 **MODERADO** | 🟠 **MODERADO** | Pontual (bootstrap) | **Carga inicial**. Usado uma vez no setup. Perda = precisa recoletar histórico manualmente (trabalhoso, mas possível). Impacto operacional moderado em disaster recovery. |
| `docker-compose.yml` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Infraestrutura de dados**. Define PostgreSQL/TimescaleDB. Sem banco = sem persistência = sem auditoria = violação de compliance. Recriável, mas crítico. |
| `src/collectors/mt5_data_collector.py` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Collector principal**. Consome Bridge API → persiste no DB. Loop contínuo de coleta. Falha = gap nos dados = backtests inválidos = decisões sem contexto completo. |
| `.env` | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | 🔴 **CRÍTICO** | Contínuo | **Credenciais MT5 + DB**. Sem ele = sem autenticação = sistema não inicia. Perda acidental = exposição de credenciais = risco de segurança. |

### 💡 Insight Crítico:
> **4 de 5** infraestruturas têm impacto crítico total. São componentes de runtime necessários para operação contínua.

---

## 🧪 CATEGORIA 3: TESTE AUTOMATIZADO ESSENCIAL (6 arquivos)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `scripts/test_end_to_end.py` | ⚪ **NULO** | 🟠 **MODERADO** | 🟠 **MODERADO** | A cada deploy | **397 linhas de validação E2E**. Não afeta produção diretamente, mas perda = deploys sem validação = risco de regressões. CI/CD degradado. |
| `scripts/test_market_context_exhaustive.py` | ⚪ **NULO** | 🟠 **MODERADO** | 🔴 **CRÍTICO** | A cada mudança no classifier | **477 linhas validando 8 propriedades**. Garante que classifier NÃO gera sinais (governança). Perda = possível violação de princípios sem detecção = risco regulatório. |
| `scripts/test_dsl_v01_unittest.py` | ⚪ **NULO** | 🟠 **MODERADO** | 🟠 **MODERADO** | A cada mudança no DSL | **319 linhas unittest DSL**. Testa 7 padrões. Perda = mudanças em padrões sem validação = comportamento não testado = risco de falsos positivos. |
| `scripts/run_dsl_v01.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟡 **BAIXO** | Ocasional (validação) | **CLI runner**. Usado para validar pipeline com dados reais. Útil em debug, mas não crítico. Substituível por chamadas diretas aos módulos. |
| `scripts/test_database_strategies.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟡 **BAIXO** | Ocasional | **136 linhas de testes SQL**. Valida queries e estratégias básicas. Útil, mas não essencial no CI/CD. Estratégias podem ser testadas diretamente. |
| `scripts/validate_backend.py` | ⚪ **NULO** | 🟠 **MODERADO** | 🟠 **MODERADO** | A cada deploy | **64 linhas health check**. Valida schema PostgreSQL. Perda = deploys sem validação de infraestrutura = possível falha silenciosa de tabelas. |

### 💡 Insight Moderado:
> Testes não afetam produção diretamente (impacto financeiro nulo), mas **3 de 6** têm impacto de risco moderado a crítico por garantirem governança e qualidade.

---

## 🔬 CATEGORIA 4: TESTE EXPLORATÓRIO / EXPERIMENTAL (7 arquivos)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `scripts/explore_mt5_capabilities.py` | ⚪ **NULO** | ⚪ **NULO** | 🟡 **BAIXO** | Obsoleto (setup inicial) | **281 linhas de exploração**. Útil durante aprendizado inicial, mas substituído por testes estruturados. Perda = perde documentação "viva" de capabilities. |
| `scripts/test_binance_ws.py` | ⚪ **NULO** | ⚪ **NULO** | ⚪ **NULO** | Obsoleto | **39 linhas teste básico**. Apenas imprime bid/ask. Sem utilidade ativa. Substituído por collector completo. |
| `scripts/test_data_collection.py` | ⚪ **NULO** | ⚪ **NULO** | ⚪ **NULO** | Obsoleto | **83 linhas teste manual**. Substituído por `test_end_to_end.py`. Sem utilidade ativa. |
| `scripts/test_mt5_simple.py` | ⚪ **NULO** | ⚪ **NULO** | 🟡 **BAIXO** | Obsoleto (setup inicial) | **~200 linhas** (8211 bytes). Provável teste didático inicial. Pode ser útil em onboarding de novos devs, mas não essencial. |
| `scripts/test_mt5_connection_windows.py` | ⚪ **NULO** | ⚪ **NULO** | 🟡 **BAIXO** | Obsoleto (se usa bridge) | **~150 linhas** (6092 bytes). Teste direto Windows. Se arquitetura atual é Bridge em WSL, não tem uso. Pode ser útil em troubleshooting de ambiente Windows. |
| `scripts/test_mt5_db_integration.py` | ⚪ **NULO** | ⚪ **NULO** | ⚪ **NULO** | Obsoleto | **~65 linhas** (2658 bytes). Substituído por E2E. Importa módulos de produção, mas sem uso ativo. |
| `scripts/validate_dashboard_playwright.py` | ⚪ **NULO** | ⚪ **NULO** | 🟡 **BAIXO** | Desconhecido (depende de dashboard) | **24 linhas**. Se dashboard está inativo (README = TODO), teste também está. Se dashboard for ativado, retorna para QA essencial. |

### 💡 Insight Baixo:
> **5 de 7** têm impacto nulo em todas as dimensões. São experimentos históricos sem uso ativo.

---

## 🛠️ CATEGORIA 5: FERRAMENTA DE DESENVOLVIMENTO / DEBUG (6 arquivos)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `scripts/mt5_validation/0_find_mt5.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟠 **MODERADO** | Setup inicial / troubleshooting | **146 linhas busca MT5**. Crítico no **onboarding** e em troubleshooting de ambiente. Perda = setup manual mais demorado. Aumenta tempo de recovery em disaster. |
| `scripts/mt5_validation/1_check_connection.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟠 **MODERADO** | Troubleshooting | **Passo 2 de diagnóstico estruturado**. Valida conexão/login. Perda = debug manual mais lento. Tempo de recovery aumenta. |
| `scripts/mt5_validation/2_check_tick_data.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟠 **MODERADO** | Troubleshooting | **Passo 3**: valida coleta de ticks. Essencial para diagnosticar problemas de qualidade de dados. Perda = debug mais lento. |
| `scripts/mt5_validation/3_check_orderbook.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟠 **MODERADO** | Troubleshooting | **Passo 4**: valida Market Depth. Crítico para microestrutura. Sem ele, debug de orderbook é "cego". |
| `scripts/mt5_validation/4_stress_test.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟡 **BAIXO** | Pontual (performance testing) | **~90 linhas stress test**. Útil antes de aumentar load, mas não essencial em operação normal. |
| `scripts/mt5_validation/5_data_structure_test.py` | ⚪ **NULO** | 🟡 **BAIXO** | 🟡 **BAIXO** | Pontual (validação one-time) | **~60 linhas schema test**. Validação de estrutura de dados MT5. Útil, mas não repetitivo. |

### 💡 Insight Moderado:
> **4 de 6** têm impacto de risco moderado por serem essenciais em **troubleshooting**. Em sistemas financeiros, tempo de recovery é crítico = impacto moderado justificado.

---

## 📖 CATEGORIA 6: DOCUMENTAÇÃO EXECUTÁVEL (1 arquivo)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `README.md` | ⚪ **NULO** | 🟡 **BAIXO** | 🟠 **MODERADO** | Constante (referência) | **384 linhas documentação**. Guia de arquitetura, setup, troubleshooting. Perda = onboarding mais lento, conhecimento tribal. Em eventos de disaster, README é entrada crítica. |

---

## ⚠️ CATEGORIA 7: OBSOLETO / LEGADO (9 arquivos)

| Arquivo | Impacto Financeiro | Impacto Operacional | Impacto Risco | Frequência Uso | Justificativa de Impacto |
|---------|-------------------|---------------------|---------------|----------------|--------------------------|
| `src/analysis/indicators.py` | ⚪ **NULO*** | ⚪ **NULO*** | ⚪ **NULO*** | Desconhecido | Usado por dashboard (status incerto). **SE dashboard inativo** = nulo. **SE dashboard ativo** = crítico. Marcado com * asterisco. |
| `src/analysis/alerts.py` | ⚪ **NULO*** | ⚪ **NULO*** | ⚪ **NULO*** | Desconhecido | Idem. Depende de status do dashboard. |
| `src/analysis/patterns.py` | ⚪ **NULO*** | ⚪ **NULO*** | ⚪ **NULO*** | Desconhecido | Idem. Pode ter padrões usados em análise. |
| `src/analysis/trading_strategies.py` | ⚪ **NULO** | ⚪ **NULO** | ⚪ **NULO** | Não detectado | Standalone sem referências. Assumido inativo. |
| `src/models/gpu_model.py` | ⚪ **NULO** | ⚪ **NULO** | ⚪ **NULO** | Não detectado | Sem referências. Provável experimento ML. |
| `src/visualization/dashboard.py` | **DESCONHECIDO** | **DESCONHECIDO** | **DESCONHECIDO** | **REQUER TESTE** | **README marca como TODO**, mas código existe e importa 7+ módulos. **CRITICAL UNKNOWN** - pode estar ativo! |
| `src/visualization/orderbook_viz.py` | ⚪ **NULO*** | ⚪ **NULO*** | ⚪ **NULO*** | Desconhecido | Depende de dashboard. |
| `src/collectors/mt5_candles.py` | **DESCONHECIDO** | **DESCONHECIDO** | **DESCONHECIDO** | Desconhecido | Importado condicionalmente no dashboard. Relação com `mt5_market_data.py` não clara. Pode ser redundante ou especializado. |
| `src/collectors/market_data.py` | ⚪ **NULO** | ⚪ **NULO** | ⚪ **NULO** | Não detectado | Standalone sem referências. Assumido inativo. |

### 💡 Insight Crítico:
> **3 arquivos têm impacto DESCONHECIDO** por dependerem do status do dashboard. **Requer teste imediato** de `streamlit run src/visualization/dashboard.py` antes de qualquer decisão.

---

## 🚨 ANÁLISE DE RISCO AGREGADA

### 🔴 CRÍTICO: Impacto Total em Todas as Dimensões (16 arquivos)

| Arquivo | Razão |
|---------|-------|
| `src/microstructure/*` (5 arquivos) | Core da pipeline de decisão |
| `src/analysis/market_context_classifier.py` | Validado exaustivamente, usado em produção |
| `src/database/db_handler.py` | Persistência e auditoria |
| `src/collectors/mt5_market_data.py` | Fonte primária de dados MT5 |
| `src/collectors/crypto_market_data.py` | Fonte primária de dados Binance |
| `scripts/mt5_bridge_service.py` | SPOF (Single Point of Failure) |
| `src/collectors/mt5_data_collector.py` | Loop de coleta contínua |
| `docker-compose.yml` | Infraestrutura de dados |
| `.env` | Credenciais e configuração |

> **TOTAL: 16 arquivos de impacto crítico = NÚCLEO INTOCÁVEL**

---

### 🟠 MODERADO: Impacto em 1-2 Dimensões (11 arquivos)

**Risco Alto:**
- `test_market_context_exhaustive.py` — Governança crítica
- `validate_backend.py` — Health check de deploy
- `mt5_validation/0-3.py` — Troubleshooting estruturado

**Operacional Moderado:**
- `load_historical_data.py` — Bootstrap/recovery
- `test_end_to_end.py` — CI/CD validation
- `test_dsl_v01_unittest.py` — Qualidade do DSL

**Risco Documentação:**
- `README.md` — Knowledge base

---

### 🟡 BAIXO: Impacto em Dimensões Secundárias (7 arquivos)

- Testes pontuais: `run_dsl_v01.py`, `test_database_strategies.py`
- Ferramentas ocasionais: `mt5_validation/4-5.py`
- Experimentos documentados: `explore_mt5_capabilities.py`, `test_mt5_simple.py`, `test_mt5_connection_windows.py`

---

### ⚪ NULO: Sem Impacto Detectado (5 arquivos)

- `test_binance_ws.py`
- `test_data_collection.py`
- `test_mt5_db_integration.py`
- `trading_strategies.py` (sem uso)
- `gpu_model.py` (sem uso)
- `market_data.py` (sem uso)

---

## 🔍 ANÁLISE POR DIMENSÃO

### Impacto Financeiro Direto

| Nível | Arquivos | % Total |
|-------|----------|---------|
| 🔴 Crítico | 13-16* | 31-38% |
| 🟠 Moderado | 1-2 | 2-5% |
| 🟡 Baixo | 1 | 2% |
| ⚪ Nulo | 22-25 | 55-62% |

*Varia conforme status do dashboard

### Impacto Operacional

| Nível | Arquivos | % Total |
|-------|----------|---------|
| 🔴 Crítico | 14-17* | 33-40% |
| 🟠 Moderado | 7-10* | 17-24% |
| 🟡 Baixo | 8 | 19% |
| ⚪ Nulo | 8-12* | 19-29% |

### Impacto de Risco (Debug/Auditoria)

| Nível | Arquivos | % Total |
|-------|----------|---------|
| 🔴 Crítico | 14-17* | 33-40% |
| 🟠 Moderado | 8-11* | 19-26% |
| 🟡 Baixo | 8 | 19% |
| ⚪ Nulo | 8-12* | 19-29% |

---

## 🎯 INCERTEZAS CRÍTICAS QUE BLOQUEIAM ANÁLISE

### 🚨 PRIORIDADE 1: Dashboard Status

**Bloqueio**: 6 arquivos têm impacto de DESCONHECIDO a CRÍTICO dependendo do dashboard.

**Teste necessário**:
```bash
streamlit run src/visualization/dashboard.py
```

**Cenários**:

| Se dashboard | Impacto de | Decisão para |
|--------------|-----------|--------------|
| ✅ **Funciona** | `dashboard.py`, `indicators.py`, `alerts.py`, `patterns.py`, `orderbook_viz.py` = 🔴 **CRÍTICO** | MANTER TODOS |
| ❌ **Não funciona** | Todos = ⚪ **NULO** | Mover para legacy |
| ⚠️ **Parcial** | Análise caso a caso | Desacoplar módulos ativos |

---

### 🚨 PRIORIDADE 2: Redundância mt5_candles vs mt5_market_data

**Bloqueio**: Dois collectors MT5 podem ser redundantes ou complementares.

**Análise necessária**:
```bash
diff -u src/collectors/mt5_candles.py src/collectors/mt5_market_data.py
```

**Perguntas**:
1. `mt5_candles.py` coleta apenas OHLCV?
2. `mt5_market_data.py` coleta ticks + orderbook?
3. São usados simultaneamente ou alternativamente?

---

### 🚨 PRIORIDADE 3: SMC e Market State Classifier

**Bloqueio**: Dois módulos de análise sem uso detectado explícito.

**Verificação necessária**:
```bash
grep -r "smc_liquidity_sweep\|market_state_classifier" src/ scripts/
```

**Se usado em produção** = 🔴 CRÍTICO  
**Se não usado** = ⚪ NULO

---

## 📋 MATRIZ DE DECISÃO CONSERVADORA

### Para Arquivos de Impacto Crítico (16 arquivos):
- ✅ **MANTER** sem questionar
- ✅ **DOCUMENTAR** propósito se não óbvio
- ✅ **TESTAR** antes de qualquer mudança
- ❌ **NUNCA** remover sem plano de migração completo

### Para Arquivos de Impacto Moderado (11 arquivos):
- ✅ **MANTER** até análise de uso real
- ⚠️ **CONSIDERAR** consolidação se redundantes
- ✅ **JUSTIFICAR** manutenção ou remoção com dados

### Para Arquivos de Impacto Baixo (7 arquivos):
- ⚠️ **AVALIAR** custo de manutenção vs benefício
- ✅ **ARQUIVAR** em vez de deletar (mover para `/archive/`)
- ✅ **DOCUMENTAR** em changelog se removidos

### Para Arquivos de Impacto Nulo (5 arquivos):
- ✅ **REMOVER** após backup em `/archive/`
- ✅ **COMMIT** separado com mensagem clara
- ✅ **VALIDAR** que nenhum import externo existe

---

## 🔐 PROTOCOLO DE SEGURANÇA PARA SISTEMAS FINANCEIROS

### Antes de Remover QUALQUER Arquivo:

1. ✅ **Backup completo** em `/archive/YYYY-MM-DD/`
2. ✅ **Grep global**: `grep -r "nome_do_arquivo" .`
3. ✅ **Teste completo**: `python scripts/test_end_to_end.py`
4. ✅ **Commit isolado**: mensagem descritiva
5. ✅ **Rollback plan**: branch separada, não direto em main
6. ✅ **Documentação**: atualizar README e changelog

---

## 📊 RECOMENDAÇÃO FINAL (Conservadora)

### 🔴 NÃO TOCAR (33 arquivos):
- 16 de impacto crítico total
- 11 de impacto moderado
- 6 que dependem de dashboard (até testar)

### 🟡 INVESTIGAR ANTES DE DECIDIR (3 arquivos):
- Dashboard status
- Redundância collectors
- Uso de SMC/market_state

### 🟢 CANDIDATOS A ARQUIVAMENTO (5 arquivos):
- `test_binance_ws.py`
- `test_data_collection.py`
- `test_mt5_db_integration.py`
- `trading_strategies.py` (se confirmado não uso)
- `gpu_model.py` (se confirmado não uso)
- `market_data.py` (se confirmado não uso)

---

**Próximo Passo**: Resolver 3 incertezas críticas antes de Fase 3 (Execução).

**Postura**: Em sistemas financeiros, **custo de manter arquivo desnecessário < risco de remover arquivo necessário**.

---

**Metodologia aplicada**: Análise de impacto em cascata considerando dependências diretas/indiretas, frequência de uso inferida pelo papel no fluxo, e conservadorismo financeiro.

**Data de validade**: 2026-01-02 17:16 UTC-3
