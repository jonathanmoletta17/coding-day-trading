# 🔍 RESOLUÇÃO DE INCERTEZAS - FASE 1

**Data**: 2026-01-02 17:21 UTC-3  
**Método**: Grep analysis de dependências

---

## ✅ RESULTADO DAS VERIFICAÇÕES

### 1. `src/analysis/smc_liquidity_sweep.py`
**Comando**: `grep -r "smc_liquidity_sweep" src/ scripts/ --include="*.py"`  
**Resultado**: ✅ **ZERO** referências encontradas  
**Decisão**: ⚪ **IMPACTO NULO** confirmado  
**Ação**: 📦 **ARQUIVAR** em `archive/2026-01-02-initial-cleanup/experiments/`

---

### 2. `src/analysis/market_state_classifier.py`
**Comando**: `grep -r "market_state_classifier" src/ scripts/ --include="*.py"`  
**Resultado**: ✅ **ZERO** referências encontradas  
**Decisão**: ⚪ **IMPACTO NULO** confirmado  
**Ação**: 📦 **ARQUIVAR** em `archive/2026-01-02-initial-cleanup/experiments/`

---

### 3. `src/analysis/trading_strategies.py`
**Comando**: `grep -r "trading_strategies" src/ scripts/ --include="*.py"`  
**Resultado**: ✅ **ZERO** referências encontradas  
**Decisão**: ⚪ **IMPACTO NULO** confirmado  
**Ação**: 📦 **ARQUIVAR** em `archive/2026-01-02-initial-cleanup/experiments/`

---

### 4. `src/models/gpu_model.py`
**Comando**: `grep -r "gpu_model" src/ scripts/ --include="*.py"`  
**Resultado**: ✅ **ZERO** referências encontradas  
**Decisão**: ⚪ **IMPACTO NULO** confirmado  
**Ação**: 📦 **ARQUIVAR** em `archive/2026-01-02-initial-cleanup/experiments/`

---

### 5. `src/collectors/market_data.py`
**Comando**: `grep -r "from src.collectors.market_data\|import market_data"`  
**Resultado**: ✅ **ZERO** referências encontradas  
**Decisão**: ⚪ **IMPACTO NULO** confirmado  
**Ação**: 📦 **ARQUIVAR** em `archive/2026-01-02-initial-cleanup/experiments/`

---

### 6. `src/collectors/mt5_candles.py` ⚠️ USADO!
**Comando**: `grep -r "mt5_candles" src/ scripts/ --include="*.py"`  
**Resultado**: ⚠️ **1 referência encontrada**  
```python
src/visualization/dashboard.py:        from src.collectors.mt5_candles import MT5CandleCollector
```

**Análise**:
- Importado **condicionalmente** no dashboard
- Import está dentro de uma função (lazy import)
- **DEPENDE DO STATUS DO DASHBOARD**

**Decisão**: 🔍 **INVESTIGAÇÃO PENDENTE**  
**Ação**:
- **SE dashboard ativo**: ✅ **MANTER** `mt5_candles.py` em `src/collectors/`
- **SE dashboard inativo**: 📦 **ARQUIVAR** junto com dashboard

---

## 📊 RESUMO DE DECISÕES

### ✅ Impacto Nulo Confirmado (8 arquivos totais):

#### Já listados no plano:
1. `scripts/test_binance_ws.py` ✅
2. `scripts/test_data_collection.py` ✅
3. `scripts/test_mt5_db_integration.py` ✅

#### Confirmados agora:
4. `src/analysis/smc_liquidity_sweep.py` ✅
5. `src/analysis/market_state_classifier.py` ✅
6. `src/analysis/trading_strategies.py` ✅
7. `src/models/gpu_model.py` ✅
8. `src/collectors/market_data.py` ✅

**Total para arquivar**: 8 arquivos (subiu de 5 para 8)

---

### ⚠️ Ainda Dependem de Dashboard (6 arquivos):

1. `src/visualization/dashboard.py` — Core
2. `src/visualization/orderbook_viz.py` — Usado por dashboard
3. `src/analysis/indicators.py` — Usado por dashboard
4. `src/analysis/alerts.py` — Usado por dashboard
5. `src/analysis/patterns.py` — Usado por dashboard
6. `src/collectors/mt5_candles.py` — **Confirmado usado por dashboard**

**Decisão final**: Todos os 6 dependem do teste do dashboard.

---

## 🎯 PLANO ATUALIZADO DE ARQUIVAMENTO

### Destino: `/archive/2026-01-02-initial-cleanup/`

#### Subpasta: `experiments/obsolete-tests/`
- `test_binance_ws.py`
- `test_data_collection.py`
- `test_mt5_db_integration.py`

#### Subpasta: `experiments/unused-modules/`
- `smc_liquidity_sweep.py`
- `market_state_classifier.py`
- `trading_strategies.py`
- `gpu_model.py`
- `market_data.py`

---

## 🔬 PRÓXIMA AÇÃO CRÍTICA: TESTAR DASHBOARD

**Comando pendente**:
```bash
streamlit run src/visualization/dashboard.py
```

**Cenários**:

### ✅ Cenário A: Dashboard funciona
- **Impacto**: 6 arquivos de dashboard = 🔴 **PRODUÇÃO CRÍTICA**
- **Ação**: MANTER todos em `src/`
- **README**: Atualizar status de "TODO" para "Ativo"

### ❌ Cenário B: Dashboard não funciona (erro fatal)
- **Impacto**: 6 arquivos de dashboard = ⚪ **EXPERIMENTO**
- **Ação**: Mover todos para `experiments/dashboard-poc/`
- **README**: Manter como "TODO" ou marcar como "Descontinuado"

### ⚠️ Cenário C: Dashboard parcialmente funcional
- **Impacto**: Análise caso a caso
- **Ação**: Desacoplar módulos funcionais dos quebrados
- **README**: Documentar módulos ativos vs inativos

---

## 📋 COMANDOS DE ARQUIVAMENTO PRONTOS

```bash
# Criar subpastas
mkdir -p archive/2026-01-02-initial-cleanup/experiments/{obsolete-tests,unused-modules}

# Arquivar testes obsoletos
git mv scripts/test_binance_ws.py archive/2026-01-02-initial-cleanup/experiments/obsolete-tests/
git mv scripts/test_data_collection.py archive/2026-01-02-initial-cleanup/experiments/obsolete-tests/
git mv scripts/test_mt5_db_integration.py archive/2026-01-02-initial-cleanup/experiments/obsolete-tests/

# Arquivar módulos sem uso
git mv src/analysis/smc_liquidity_sweep.py archive/2026-01-02-initial-cleanup/experiments/unused-modules/
git mv src/analysis/market_state_classifier.py archive/2026-01-02-initial-cleanup/experiments/unused-modules/
git mv src/analysis/trading_strategies.py archive/2026-01-02-initial-cleanup/experiments/unused-modules/
git mv src/models/gpu_model.py archive/2026-01-02-initial-cleanup/experiments/unused-modules/
git mv src/collectors/market_data.py archive/2026-01-02-initial-cleanup/experiments/unused-modules/

# Commit
git add -A
git commit -m "archive: move 8 zero-impact files to archive/2026-01-02

Arquivos sem uso detectado:
- 3 testes obsoletos (substituídos por test_end_to_end.py)
- 5 módulos experimentais sem referências ativas

Verificado via grep recursivo em src/ e scripts/.
Preservando histórico completo via git mv."
```

---

## ✅ STATUS ATUAL

| Categoria | Antes | Depois Grep | Status |
|-----------|-------|-------------|--------|
| Impacto Nulo Confirmado | 5 | **8** ✅ | Pronto para arquivar |
| Dependentes de Dashboard | 5 | **6** ⚠️ | Aguardando teste |
| Incertezas Bloqueantes | 3 | **1** | Dashboard é última incerteza |

---

**Próximo passo**: Testar dashboard ou proceder com arquivamento dos 8 confirmados?
