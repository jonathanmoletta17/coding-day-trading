# 🔄 GUIA DE MIGRAÇÃO 2026-01-02

**Contexto**: Reorganização estrutural completa para separar Produção, Infraestrutura, Testes e Experimentos.
**Autor**: Antigravity (IA sob Governança)
**ADR**: `ADR/ADR-0001-separacao-categorias-funcionais.md`

---

## 🗺️ Mapa de Mudanças (De -> Para)

### 🔴 Infraestrutura Crítica (Serviços)
| Antes (scripts/) | Depois (infrastructure/) | Tipo |
|------------------|--------------------------|------|
| `mt5_bridge_service.py` | `mt5_bridge_service.py` | SPOF (Single Point of Failure) |
| `src/collectors/mt5_data_collector.py` | `mt5_data_collector.py` | Daemon Service |
| `load_historical_data.py` | `load_historical_data.py` | ETL Script |

### 🧪 Testes Automatizados
| Antes (scripts/) | Depois (tests/) |
|------------------|-----------------|
| `test_end_to_end.py` | `integration/test_end_to_end.py` |
| `validate_backend.py` | `integration/validate_backend.py` |
| `test_dsl_v01_unittest.py` | `unit/test_dsl_v01_unittest.py` |
| `test_market_context_exhaustive.py` | `unit/test_market_context_exhaustive.py` |

### 🛠️ Ferramentas (Tools)
| Antes (scripts/) | Depois (tools/) | Subcategoria |
|------------------|-----------------|--------------|
| `run_dsl_v01.py` | `runners/run_dsl_v01.py` | CLI Runner |
| `mt5_validation/*` | `diagnostics/*` | 0-3 Find/Connect/Tick/Orderbook |
| `test_database_strategies.py` | `validation/test_database_strategies.py` | SQL Validation |
| `validate_dashboard_playwright.py` | `validation/validate_dashboard_playwright.py` | UI Test |

### 🔬 Experimentos (Experiments)
| Antes (scripts/) | Depois (experiments/) |
|------------------|-----------------------|
| `explore_mt5_capabilities.py` | `mt5_exploration/explore_capabilities.py` |
| `test_mt5_simple.py` | `mt5_exploration/simple_test.py` |
| `mt5_validation/4_stress_test.py` | `stress_tests/mt5_stress_test.py` |

---

## 🚀 Como Executar Tarefas Comuns

### 1. Rodar a Ponte MT5 (Bridge)
**Antigo**: `python scripts/mt5_bridge_service.py`
**Novo**: `python infrastructure/mt5_bridge_service.py`

### 2. Rodar Coletores
**Antigo**: `python src/collectors/mt5_data_collector.py`
**Novo**: `python infrastructure/mt5_data_collector.py`

### 3. Executar Testes Unitários
**Antigo**: `python scripts/test_dsl_v01_unittest.py`
**Novo**: `PYTHONPATH=. python tests/unit/test_dsl_v01_unittest.py`
*(Recomendado usar `pytest` no futuro)*

### 4. Diagnosticar Conexão MT5
**Antigo**: `python scripts/mt5_validation/1_check_connection.py`
**Novo**: `python tools/diagnostics/1_check_connection.py`

---

## ⚠️ Dores de Cabeça Comuns (Troubleshooting)

**Erro**: `ModuleNotFoundError: No module named 'src'`
**Causa**: Script movido para subpasta perdeu referência relativa.
**Solução**: Executar da raiz com `PYTHONPATH=.` ou `python -m ...`

**Erro**: `Commit bloqueado: Path proibido`
**Causa**: Tentativa de criar arquivo em `scripts/` ou raiz.
**Solução**: Usar pastas canônicas (`experiments/`, `tools/`). Ver `PROJECT_CONTEXT.yaml`.

**Erro**: `Commit bloqueado: Header ausente`
**Causa**: Novo arquivo python sem header `@category`.
**Solução**: Adicionar docstring padrão no topo (ver `ENFORCEMENT.md`).
