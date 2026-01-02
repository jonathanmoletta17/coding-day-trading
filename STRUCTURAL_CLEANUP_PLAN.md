# 🧹 PLANO DE LIMPEZA ESTRUTURAL CONTROLADA

**Data**: 2026-01-02  
**Projeto**: Coding Day Trading (MT5 + Binance)  
**Base**: Fases 1 (Classificação) + 2 (Impacto)  
**Filosofia**: Reorganizar > Arquivar > Remover

---

## 🎯 RESUMO EXECUTIVO

| Ação | Arquivos | Justificativa |
|------|----------|---------------|
| ✅ **MANTER** (src/) | 11 | Produção crítica - núcleo do sistema |
| 🔄 **REORGANIZAR** (scripts → estrutura nova) | 23 | Separar por função: infra/tests/tools/experiments |
| 📦 **ARQUIVAR** (archive/) | 5 | Impacto nulo confirmado, preservar histórico |
| ⚠️ **INVESTIGAR PRIMEIRO** | 3 | Incertezas bloqueantes (dashboard, collectors) |
| ❌ **REMOVER** | 0 | Nenhum arquivo será deletado permanentemente |

**Total analisado**: 42 arquivos Python  
**Filosofia**: Zero perda de informação, máxima organização

---

## 📦 CATEGORIA 1: ARQUIVAR (5 arquivos)
*Impacto nulo em todas as dimensões - mover para `/archive/` com data*

### Critérios de Seleção:
- ✅ **Zero** dependentes ativos
- ✅ **Zero** imports em código de produção
- ✅ **Zero** uso em CI/CD
- ✅ Substituídos por código mais completo

| Arquivo | Tamanho | Impacto Fase 2 | Ação | Justificativa Técnica |
|---------|---------|----------------|------|----------------------|
| `scripts/test_binance_ws.py` | 39 linhas | ⚪ Nulo (F/O/R) | 📦 **ARQUIVAR** | **Substituído por `crypto_market_data.py`**. Teste manual básico (39 linhas) que apenas imprime bid/ask por 10s. Sem validações, sem assertions. Útil durante aprendizado inicial da API Binance, mas agora redundante com collector completo. Preservar como documentação histórica de experimentação. |
| `scripts/test_data_collection.py` | 83 linhas | ⚪ Nulo (F/O/R) | 📦 **ARQUIVAR** | **Substituído por `test_end_to_end.py`**. Teste manual MT5 com prints. Não integrado ao CI/CD. Valida candles/ticks/orderbook, mas `test_end_to_end.py` faz isso de forma estruturada + persiste no DB + valida schema. Preservar como evidência de processo de desenvolvimento. |
| `scripts/test_mt5_db_integration.py` | ~65 linhas | ⚪ Nulo (F/O/R) | 📦 **ARQUIVAR** | **Substituído por `test_end_to_end.py`**. Importa `mt5_market_data` e `db_handler`, mas não referenciado por nenhum outro script. Teste antigo de integração básica MT5→DB. Substituído por E2E mais abrangente (397 linhas que testa 7 etapas). |
| `src/analysis/trading_strategies.py` | Não contado | ⚪ Nulo* | 📦 **ARQUIVAR** (após grep) | **Sem referências detectadas**. Standalone com `if __name__`. Pode conter lógica de estratégias que foi planejada mas nunca integrada. **GREP PRIMEIRO** para confirmar zero uso: `grep -r "trading_strategies" src/ scripts/`. Se zero hits = arquivar. |
| `src/models/gpu_model.py` | Não contado | ⚪ Nulo* | 📦 **ARQUIVAR** (após grep) | **Experimento ML sem integração**. Não importado por nenhum módulo ativo. Provável PoC de modelo com GPU que não foi levado adiante. **GREP PRIMEIRO**: `grep -r "gpu_model" src/ scripts/`. Se zero = arquivar como experimento histórico. |

**Destino**: `/archive/2026-01-02-initial-cleanup/experiments/`

---

## 🔄 CATEGORIA 2: REORGANIZAR (23 arquivos)
*Reestruturar para nova hierarquia de diretórios*

### 🏗️ NOVA ESTRUTURA PROPOSTA

```
coding-day-trading/
├── src/                              # PRODUÇÃO CRÍTICA (11 arquivos)
│   ├── microstructure/               # 5 arquivos - Core DSL engine
│   ├── analysis/                     # 3 arquivos - Classifiers ativos
│   ├── database/                     # 1 arquivo - Persistência
│   └── collectors/                   # 2 arquivos - MT5 + Binance collectors
│
├── infrastructure/                   # SERVIÇOS CRÍTICOS (3→3 arquivos)
│   ├── mt5_bridge_service.py         # MOVER de scripts/
│   ├── mt5_data_collector.py         # MOVER de src/collectors/
│   └── load_historical_data.py       # MOVER de scripts/
│
├── tests/                            # TESTES ESSENCIAIS CI/CD (6→3 arquivos)
│   ├── integration/
│   │   ├── test_end_to_end.py        # MOVER de scripts/
│   │   └── validate_backend.py       # MOVER de scripts/
│   └── unit/
│       ├── test_dsl_v01_unittest.py  # MOVER de scripts/
│       └── test_market_context_exhaustive.py  # MOVER de scripts/
│
├── tools/                            # FERRAMENTAS DE DEV (10 arquivos)
│   ├── diagnostics/                  # MOVER scripts/mt5_validation/
│   │   ├── 0_find_mt5.py
│   │   ├── 1_check_connection.py
│   │   ├── 2_check_tick_data.py
│   │   └── 3_check_orderbook.py
│   ├── runners/
│   │   └── run_dsl_v01.py            # MOVER de scripts/
│   └── validation/
│       ├── test_database_strategies.py  # MOVER de scripts/
│       └── validate_dashboard_playwright.py  # MOVER de scripts/
│
├── experiments/                      # EXPLORATÓRIOS (4 arquivos)
│   ├── mt5_exploration/
│   │   ├── explore_mt5_capabilities.py  # MOVER de scripts/
│   │   ├── test_mt5_simple.py           # MOVER de scripts/
│   │   └── test_mt5_connection_windows.py  # MOVER de scripts/
│   └── stress_tests/
│       ├── 4_stress_test.py          # MOVER de scripts/mt5_validation/
│       └── 5_data_structure_test.py  # MOVER de scripts/mt5_validation/
│
├── archive/                          # HISTÓRICO (5 arquivos + futuros)
│   └── 2026-01-02-initial-cleanup/
│       └── ...                       # Arquivos de impacto nulo
│
├── docs/                             # Documentação (mantida como está)
├── sql/                              # Schema (mantido)
└── data/                             # Dados (mantido)
```

---

## 📋 MAPA DE REORGANIZAÇÃO DETALHADO

### 🚀 Grupo A: Infraestrutura Crítica (3 arquivos)

| Arquivo Original | Novo Local | Justificativa |
|-----------------|------------|---------------|
| `scripts/mt5_bridge_service.py` | `infrastructure/mt5_bridge_service.py` | **SPOF crítico**. 416 linhas FastAPI. Não é um "script", é um **serviço de runtime**. Merece diretório próprio. |
| `src/collectors/mt5_data_collector.py` | `infrastructure/mt5_data_collector.py` | **Loop de coleta contínua**. Executável standalone que consome Bridge API. Mais um serviço que uma lib. |
| `scripts/load_historical_data.py` | `infrastructure/load_historical_data.py` | **ETL de bootstrap**. Script de setup/recovery de infraestrutura. |

**Renomear `scripts/` → `infrastructure/`** para refletir papel real.

---

### 🧪 Grupo B: Testes Essenciais (6→4 arquivos)

| Arquivo Original | Novo Local | Impacto | Justificativa |
|-----------------|------------|---------|---------------|
| `scripts/test_end_to_end.py` | `tests/integration/test_end_to_end.py` | 🟠 Moderado (O+R) | **397 linhas E2E**. Valida 7 etapas. CI/CD essencial. |
| `scripts/validate_backend.py` | `tests/integration/validate_backend.py` | 🟠 Moderado (O+R) | **Health check** de deploy. 64 linhas. |
| `scripts/test_dsl_v01_unittest.py` | `tests/unit/test_dsl_v01_unittest.py` | 🟠 Moderado (O+R) | **319 linhas unittest DSL**. Testa 7 padrões. |
| `scripts/test_market_context_exhaustive.py` | `tests/unit/test_market_context_exhaustive.py` | 🔴 Crítico (R) | **477 linhas governança**. Valida 8 propriedades. Risco regulatório. |

**Não mover**:
- `run_dsl_v01.py` → não é teste, é runner (vai para tools/)
- `test_database_strategies.py` → teste ocasional de SQL, não CI/CD (vai para tools/validation/)

---

### 🛠️ Grupo C: Ferramentas de Desenvolvimento (10 arquivos)

#### C1: Diagnóstico MT5 (4 arquivos)

| Arquivo Original | Novo Local | Justificativa |
|-----------------|------------|---------------|
| `scripts/mt5_validation/0_find_mt5.py` | `tools/diagnostics/0_find_mt5.py` | Workflow estruturado de troubleshooting. Impacto moderado em recovery time. |
| `scripts/mt5_validation/1_check_connection.py` | `tools/diagnostics/1_check_connection.py` | Passo 2 do diagnóstico. |
| `scripts/mt5_validation/2_check_tick_data.py` | `tools/diagnostics/2_check_tick_data.py` | Passo 3 - valida qualidade de dados. |
| `scripts/mt5_validation/3_check_orderbook.py` | `tools/diagnostics/3_check_orderbook.py` | Passo 4 - crítico para microestrutura. |

**Preservar numeração** para indicar sequência de execução.

#### C2: Runners & Validação (3 arquivos)

| Arquivo Original | Novo Local | Justificativa |
|-----------------|------------|---------------|
| `scripts/run_dsl_v01.py` | `tools/runners/run_dsl_v01.py` | **CLI runner de produção**. 119 linhas. Usado para validar pipeline com dados reais via argparse. |
| `scripts/test_database_strategies.py` | `tools/validation/test_database_strategies.py` | **136 linhas SQL tests**. Validação ocasional de queries, não CI/CD contínuo. |
| `scripts/validate_dashboard_playwright.py` | `tools/validation/validate_dashboard_playwright.py` | **24 linhas UI test**. Depende de dashboard estar ativo. |

---

### 🔬 Grupo D: Experimentos (6 arquivos)

| Arquivo Original | Novo Local | Impacto | Justificativa |
|-----------------|------------|---------|---------------|
| `scripts/explore_mt5_capabilities.py` | `experiments/mt5_exploration/explore_capabilities.py` | 🟡 Baixo (R) | **281 linhas exploração**. Documentação "viva" de API. Útil para onboarding, mas não essencial. |
| `scripts/test_mt5_simple.py` | `experiments/mt5_exploration/simple_test.py` | 🟡 Baixo (R) | **~200 linhas teste didático**. Experimento inicial de aprendizado. |
| `scripts/test_mt5_connection_windows.py` | `experiments/mt5_exploration/windows_connection_test.py` | 🟡 Baixo (R) | **~150 linhas teste direto Windows**. Legacy se arquitetura atual é Bridge em WSL. |
| `scripts/mt5_validation/4_stress_test.py` | `experiments/stress_tests/mt5_stress_test.py` | 🟡 Baixo (R) | **~90 linhas performance test**. Validação pontual, não contínua. |
| `scripts/mt5_validation/5_data_structure_test.py` | `experiments/validation/data_structure_test.py` | 🟡 Baixo (R) | **~60 linhas schema test**. Validação one-time de formato MT5. |
| `scripts/test_mt5_wsl_helper.sh` | `experiments/mt5_exploration/wsl_helper.sh` | 🟡 Baixo (?) | **Bash script** não analisado. Mover para experiments até análise completa. |

---

### ⚠️ Grupo E: Investigação Pendente (9 arquivos)

**NÃO MOVER ATÉ RESOLVER INCERTEZAS**

| Arquivo | Bloqueio | Ação Necessária | Destino Potencial |
|---------|----------|-----------------|-------------------|
| `src/visualization/dashboard.py` | Dashboard status | `streamlit run src/visualization/dashboard.py` | Se ativo: **MANTER src/**. Se inativo: **experiments/** |
| `src/visualization/orderbook_viz.py` | Depende de dashboard | Teste dashboard | Idem dashboard |
| `src/analysis/indicators.py` | Usado por dashboard | Teste dashboard | Idem dashboard |
| `src/analysis/alerts.py` | Usado por dashboard | Teste dashboard | Idem dashboard |
| `src/analysis/patterns.py` | Usado por dashboard | Teste dashboard | Idem dashboard |
| `src/collectors/mt5_candles.py` | Redundância? | Comparar com `mt5_market_data.py` | Se redundante: **archive/**. Se complementar: **MANTER** |
| `src/collectors/market_data.py` | Sem uso detectado | `grep -r "market_data" src/ scripts/` | Se zero: **archive/** |
| `src/analysis/smc_liquidity_sweep.py` | Uso incerto | `grep -r "smc_liquidity" src/ scripts/` | Se usado: **MANTER**. Se não: **experiments/** |
| `src/analysis/market_state_classifier.py` | Uso incerto | `grep -r "market_state" src/ scripts/` | Se usado: **MANTER**. Se não: **experiments/** |

---

## 🎬 PLANO DE EXECUÇÃO PASSO A PASSO

### FASE 0: PRÉ-REQUISITOS (Segurança)

```bash
# 1. Criar branch de trabalho
git checkout -b cleanup/structural-reorganization

# 2. Commit do estado atual
git add -A
git commit -m "checkpoint: antes da reorganização estrutural"

# 3. Criar diretórios de destino
mkdir -p infrastructure
mkdir -p tests/{integration,unit}
mkdir -p tools/{diagnostics,runners,validation}
mkdir -p experiments/{mt5_exploration,stress_tests,validation}
mkdir -p archive/2026-01-02-initial-cleanup/experiments
```

---

### FASE 1: RESOLVER INCERTEZAS BLOQUEANTES

#### 1.1 Testar Dashboard

```bash
# Tentar executar dashboard
streamlit run src/visualization/dashboard.py

# Se funcionar:
#   - Dashboard e dependentes = PRODUÇÃO (manter em src/)
# Se não funcionar:
#   - Dashboard e dependentes = EXPERIMENTO (mover para experiments/)
```

#### 1.2 Verificar Uso de Classifiers

```bash
# SMC Liquidity Sweep
grep -r "smc_liquidity_sweep" src/ scripts/ --include="*.py" | grep -v ".pyc"

# Market State Classifier
grep -r "market_state_classifier" src/ scripts/ --include="*.py" | grep -v ".pyc"

# Se zero resultados = mover para experiments/
```

#### 1.3 Comparar Collectors MT5

```bash
# Ver diferenças
diff -u src/collectors/mt5_candles.py src/collectors/mt5_market_data.py

# Verificar uso do mt5_candles
grep -r "mt5_candles" src/ scripts/ --include="*.py"

# Verificar uso do market_data
grep -r "from src.collectors.market_data\|import market_data" . --include="*.py"
```

---

### FASE 2: ARQUIVAR (Impacto Nulo Confirmado)

```bash
# Criar backup datado
mkdir -p archive/2026-01-02-initial-cleanup/experiments

# Mover arquivos de impacto nulo
git mv scripts/test_binance_ws.py archive/2026-01-02-initial-cleanup/experiments/
git mv scripts/test_data_collection.py archive/2026-01-02-initial-cleanup/experiments/
git mv scripts/test_mt5_db_integration.py archive/2026-01-02-initial-cleanup/experiments/

# Verificar trading_strategies e gpu_model (após grep confirmar zero uso)
grep -r "trading_strategies" src/ scripts/ --include="*.py" | grep -v ".pyc"
if [ $? -ne 0 ]; then
    git mv src/analysis/trading_strategies.py archive/2026-01-02-initial-cleanup/experiments/
fi

grep -r "gpu_model" src/ scripts/ --include="*.py" | grep -v ".pyc"
if [ $? -ne 0 ]; then
    git mv src/models/gpu_model.py archive/2026-01-02-initial-cleanup/experiments/
fi

# Commit
git commit -m "archive: move impacto-nulo experiments to archive/2026-01-02"
```

---

### FASE 3: REORGANIZAR INFRAESTRUTURA

```bash
# Mover serviços críticos
git mv scripts/mt5_bridge_service.py infrastructure/
git mv src/collectors/mt5_data_collector.py infrastructure/
git mv scripts/load_historical_data.py infrastructure/

# Atualizar imports (se necessário)
# mt5_data_collector.py pode precisar ajustar path relativo

# Commit
git commit -m "refactor: move critical services to infrastructure/"
```

---

### FASE 4: REORGANIZAR TESTES

```bash
# Testes de integração
git mv scripts/test_end_to_end.py tests/integration/
git mv scripts/validate_backend.py tests/integration/

# Testes unitários
git mv scripts/test_dsl_v01_unittest.py tests/unit/
git mv scripts/test_market_context_exhaustive.py tests/unit/

# Commit
git commit -m "refactor: organize tests into integration/ and unit/"
```

---

### FASE 5: ORGANIZAR FERRAMENTAS

```bash
# Diagnóstico
git mv scripts/mt5_validation/0_find_mt5.py tools/diagnostics/
git mv scripts/mt5_validation/1_check_connection.py tools/diagnostics/
git mv scripts/mt5_validation/2_check_tick_data.py tools/diagnostics/
git mv scripts/mt5_validation/3_check_orderbook.py tools/diagnostics/

# Runners
git mv scripts/run_dsl_v01.py tools/runners/

# Validação
git mv scripts/test_database_strategies.py tools/validation/
git mv scripts/validate_dashboard_playwright.py tools/validation/

# Commit
git commit -m "refactor: organize dev tools into diagnostics/runners/validation"
```

---

### FASE 6: ISOLAR EXPERIMENTOS

```bash
# Exploração MT5
git mv scripts/explore_mt5_capabilities.py experiments/mt5_exploration/explore_capabilities.py
git mv scripts/test_mt5_simple.py experiments/mt5_exploration/simple_test.py
git mv scripts/test_mt5_connection_windows.py experiments/mt5_exploration/windows_connection_test.py
git mv scripts/test_mt5_wsl_helper.sh experiments/mt5_exploration/

# Stress tests
git mv scripts/mt5_validation/4_stress_test.py experiments/stress_tests/mt5_stress_test.py
git mv scripts/mt5_validation/5_data_structure_test.py experiments/validation/data_structure_test.py

# Commit
git commit -m "refactor: isolate experimental scripts in experiments/"
```

---

### FASE 7: LIMPAR DIRETÓRIOS VAZIOS

```bash
# Remover scripts/ se vazio
if [ -z "$(ls -A scripts/)" ]; then
    rmdir scripts/
    git add -A
    git commit -m "cleanup: remove empty scripts/ directory"
fi

# Remover scripts/mt5_validation/ se vazio
if [ -d scripts/mt5_validation ] && [ -z "$(ls -A scripts/mt5_validation/)" ]; then
    rmdir scripts/mt5_validation/
    git add -A
    git commit -m "cleanup: remove empty scripts/mt5_validation/"
fi
```

---

### FASE 8: ATUALIZAR DOCUMENTAÇÃO

```bash
# Atualizar README.md
# - Atualizar estrutura de diretórios
# - Atualizar caminhos de execução
# - Adicionar seção sobre experiments/ e tools/

# Criar MIGRATION_GUIDE.md
cat > MIGRATION_GUIDE.md << 'EOF'
# Guia de Migração - Reorganização Estrutural 2026-01-02

## Mudanças de Caminho

| Caminho Antigo | Caminho Novo | Razão |
|----------------|--------------|-------|
| `scripts/mt5_bridge_service.py` | `infrastructure/mt5_bridge_service.py` | Serviço de runtime crítico |
| `scripts/test_end_to_end.py` | `tests/integration/test_end_to_end.py` | Organização de testes |
| `scripts/run_dsl_v01.py` | `tools/runners/run_dsl_v01.py` | Ferramenta de desenvolvimento |
| ... | ... | ... |

## Como Executar Após Reorganização

### Antes:
```bash
python scripts/mt5_bridge_service.py
python scripts/test_end_to_end.py
```

### Depois:
```bash
python infrastructure/mt5_bridge_service.py
python tests/integration/test_end_to_end.py
```

## Imports Afetados

Se você tem código externo que importa módulos, atualize:
- `from src.collectors.mt5_data_collector import *` → Ainda funciona (sem mudança)
- Scripts standalone não são importáveis, então sem impacto

EOF

git add MIGRATION_GUIDE.md
git commit -m "docs: add migration guide for structural reorganization"
```

---

### FASE 9: VALIDAÇÃO PÓS-REORGANIZAÇÃO

```bash
# Rodar teste E2E no novo local
python tests/integration/test_end_to_end.py

# Verificar que nenhum import quebrou
python -c "from src.microstructure import models, book, replay, dsl_v01, context_core"
python -c "from src.analysis import market_context_classifier"
python -c "from src.database import db_handler"
python -c "from src.collectors import mt5_market_data, crypto_market_data"

# Se tudo passar:
echo "✅ Reorganização validada com sucesso"
```

---

## 📊 IMPACTO DA REORGANIZAÇÃO

### Antes:
```
scripts/ (23 arquivos misturados)
  ├── Infraestrutura crítica (3)
  ├── Testes essenciais (4)
  ├── Ferramentas (7)
  ├── Experimentos (6)
  └── Legacy (3)

src/ (19 arquivos)
  ├── Produção (11)
  ├── Dashboard incerto (6)
  └── Sem uso (2)
```

### Depois:
```
infrastructure/ (3 arquivos)     ← Serviços de runtime
tests/ (4 arquivos)              ← CI/CD essenciais
tools/ (7 arquivos)              ← Dev utilities
experiments/ (6 arquivos)        ← Isolados do crítico
archive/ (5 arquivos)            ← Histórico preservado
src/ (11-17 arquivos*)           ← Apenas produção
```

*Depende da resolução do status do dashboard

---

## 🎯 BENEFÍCIOS ESPERADOS

### Técnicos:
- ✅ **Separação clara** entre produção e experimentação
- ✅ **Testes organizados** por tipo (integration/unit)
- ✅ **Infraestrutura isolada** de scripts auxiliares
- ✅ **Rastreabilidade total** via git history

### Operacionais:
- ✅ **Onboarding mais rápido**: estrutura clara de "o que é o quê"
- ✅ **CI/CD simplificado**: `tests/` claramente definido
- ✅ **Troubleshooting estruturado**: `tools/diagnostics/` em sequência
- ✅ **Experiments isolados**: sem poluir código crítico

### Risco:
- ✅ **Zero perda de código**: tudo movido com `git mv`
- ✅ **Rollback trivial**: `git revert` se necessário
- ✅ **Histórico preservado**: Git mantém rastreamento
- ✅ **Nenhum arquivo deletado**: apenas reorganizado

---

## ⚠️ RISCOS E MITIGAÇÕES

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| Imports absolutos quebrados | Baixa | Scripts standalone não são importados; produção em `src/` não muda |
| Comandos em docs desatualizados | Média | `MIGRATION_GUIDE.md` documenta todas as mudanças |
| CI/CD com paths hardcoded | Média | Verificar `.github/workflows/` (se existir) e atualizar |
| Usuário se perde na nova estrutura | Baixa | README atualizado + estrutura intuitiva |

---

## 📋 CHECKLIST DE EXECUÇÃO

- [ ] **FASE 0**: Criar branch + backup + diretórios
- [ ] **FASE 1**: Resolver 3 incertezas bloqueantes
  - [ ] Testar dashboard
  - [ ] Grep classifiers
  - [ ] Comparar collectors
- [ ] **FASE 2**: Arquivar 5 arquivos de impacto nulo
- [ ] **FASE 3**: Mover infraestrutura (3 arquivos)
- [ ] **FASE 4**: Mover testes (4 arquivos)
- [ ] **FASE 5**: Mover ferramentas (7 arquivos)
- [ ] **FASE 6**: Mover experimentos (6 arquivos)
- [ ] **FASE 7**: Limpar diretórios vazios
- [ ] **FASE 8**: Atualizar documentação
- [ ] **FASE 9**: Validar reorganização
- [ ] **FASE 10**: Merge para main (após revisão)

---

## 🚀 COMANDO DE EXECUÇÃO RÁPIDA

```bash
# Script completo de reorganização (executar após resolver incertezas)
bash tools/reorganize_structure.sh
```

Criarei este script em próximo artefato se solicitado.

---

## 📝 NOTAS FINAIS

> [!IMPORTANT]
> **Nenhum arquivo será deletado permanentemente**. Todos os movimentos são via `git mv` para preservar histórico completo.

> [!NOTE]
> Após esta reorganização, considerar:
> - Adicionar `__init__.py` em novos diretórios se quiser torná-los importáveis
> - Atualizar `.gitignore` se necessário
> - Adicionar `pytest.ini` em `tests/` para configurar pytest
> - Considerar `pyproject.toml` para organizar dependências

---

**Status**: ⏸️ **AGUARDANDO APROVAÇÃO**  
**Próximo passo**: Resolver Fase 1 (incertezas) ou aprovar execução completa

**Data de criação**: 2026-01-02 17:20 UTC-3
