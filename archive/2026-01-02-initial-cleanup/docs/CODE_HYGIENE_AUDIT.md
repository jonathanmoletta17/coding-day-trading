# 🧹 Code Hygiene Audit - pasta `scripts/`

**Data da Auditoria**: 2026-01-02  
**Projeto**: Coding Day Trading (MT5 + Binance)  
**Objetivo**: Identificar códigos mortos, experimentos e redundâncias para reduzir dívida técnica

---

## 📊 Resumo Executivo

| Categoria | Quantidade | % do Total |
|-----------|------------|------------|
| ✅ Critical Infrastructure | 2 | 9% |
| ✅ Quality Assurance | 8 | 36% |
| ⚠️ Exploratory/Legacy | 8 | 36% |
| 🔍 Review Needed | 4 | 18% |
| **TOTAL** | **22** | **100%** |

---

## 📋 Classificação Detalhada

### ✅ Critical Infrastructure (2 arquivos)

Esses scripts são **essenciais** para operação do sistema em produção e **NÃO devem ser removidos**.

| Arquivo | Justificativa | Ação Recomendada |
|---------|---------------|------------------|
| `mt5_bridge_service.py` | **API Gateway crítico** que expõe REST/WebSocket do MT5 para WSL/Linux. É o único ponto de comunicação entre ambiente Linux (produção) e MT5 Windows. Sem ele, nenhuma operação de trading funciona. | ✅ **MANTER** - Infraestrutura crítica |
| `load_historical_data.py` | Script de **carga inicial de dados históricos** no PostgreSQL. Necessário para bootstrap do sistema e backfill de dados. Sem dados históricos, o Market Context Classifier não funciona. | ✅ **MANTER** - Pipeline de dados essencial |

---

### ✅ Quality Assurance (8 arquivos)

Scripts de teste que **validam funcionalidades ativas** e devem ser mantidos para CI/CD.

| Arquivo | Justificativa | Ação Recomendada |
|---------|---------------|------------------|
| `test_end_to_end.py` | **Teste crítico end-to-end** da pipeline completa: MT5 → Bridge API → Collector → PostgreSQL. Valida 7 etapas críticas incluindo health checks, account info, tick data, candles e inserção no DB. Atualmente aberto no editor (linha 65). | ✅ **MANTER** - Teste de integração essencial |
| `test_market_context_exhaustive.py` | **Teste exaustivo do Market Context Classifier** (477 linhas). Valida TODAS as 8 propriedades declaradas do classificador: não gera sinais, não prevê preço, separação activity/behavior, determinismo, auditabilidade. Baseado na conversa recente (ce82b9be). | ✅ **MANTER** - Validação de requisitos de negócio |
| `test_dsl_v01_unittest.py` | **Suite unittest completa** (319 linhas) do DSL v0.1 Pattern Engine. Testa 7 padrões microestruturais (Depletion, Erosion, Touch Reprice, etc) + replay engine + context classifier. Usa dados sintéticos controlados. | ✅ **MANTER** - Testes unitários ativos |
| `run_dsl_v01.py` | **Runner de produção** do DSL v0.1. Não é um teste, mas um **entrypoint CLI** que processa eventos reais via argparse. Usado para rodar patterns em produção com parametrização externa. | ✅ **MANTER** - Ferramenta de produção |
| `validate_backend.py` | **Script de validação de infraestrutura**. Verifica existência de tabelas PostgreSQL (`market_ticks`, `orderbook_snapshots`), conexões e schema. Usado em deploy/CI para garantir que banco está funcional. | ✅ **MANTER** - Health check de infra |
| `mt5_validation/1_check_connection.py` | Segundo passo da **suíte de diagnóstico MT5**. Valida conexão, login, e acesso básico ao MT5 após encontrar o executável. Parte de pipeline de troubleshooting. | ✅ **MANTER** - Diagnóstico estruturado |
| `mt5_validation/2_check_tick_data.py` | Terceiro passo: valida **coleta de ticks** do MT5. Testa `copy_ticks_from()` e verifica qualidade dos dados recebidos. | ✅ **MANTER** - Validação de dados críticos |
| `mt5_validation/3_check_orderbook.py` | Quarto passo: valida **acesso ao Market Depth** (livro de ofertas). Testa `market_book_add()` e `market_book_get()`. Crítico para estratégias de microestrutura. | ✅ **MANTER** - Validação de feature essencial |

---

### ⚠️ Exploratory/Legacy (8 arquivos)

Scripts de **aprendizado, experimentos ou versões antigas** que podem ser **removidos com segurança**.

| Arquivo | Justificativa | Ação Recomendada |
|---------|---------------|------------------|
| `explore_mt5_capabilities.py` | **Script exploratório** (281 linhas) com função `explore_capabilities()` que testa TUDO que é possível fazer com MT5. Útil durante descoberta inicial, mas agora **redundante** com os testes validação específicos da pasta `mt5_validation/`. | 🗑️ **REMOVER** - Exploração superada por testes estruturados |
| `test_binance_ws.py` | **Teste manual antigo** (39 linhas) do WebSocket Binance. Apenas imprime bid/ask por 10 segundos. Muito básico e não integrado ao sistema atual. Substituído por coletores de produção em `src/collectors/`. | 🗑️ **REMOVER** - Experimento descartável |
| `test_data_collection.py` | **Teste manual de MT5** (83 linhas). Testa coleta de candles, ticks e orderbook com `print()` statements. Substituído por `test_end_to_end.py` que faz validações estruturadas + persiste no DB. | 🗑️ **REMOVER** - Redundante com E2E test |
| `test_mt5_simple.py` | Nome sugere **teste simplificado/didático** do MT5 (8211 bytes = ~200 linhas). Provavelmente outro experimento durante aprendizado da API. | 🗑️ **REMOVER** - Provável experimento |
| `test_mt5_connection_windows.py` | Teste **específico para Windows** (6092 bytes). Se o sistema roda em WSL/Linux usando o bridge, este teste é legacy. | 🗑️ **REMOVER** - Arquitetura antiga |
| `test_mt5_db_integration.py` | Apenas 2658 bytes (~65 linhas). Provavelmente teste antigo de integração MT5→DB. Substituído por `test_end_to_end.py` que é mais completo. | 🗑️ **REMOVER** - Redundante com E2E test |
| `mt5_validation/4_stress_test.py` | **Teste de carga** do MT5 (3747 bytes). Útil pontualmente, mas não é QA contínuo. Pode ser descartado se não usado regularmente. | ⚠️ **ARQUIVAR** - Mover para pasta `/experiments/` se quiser manter |
| `mt5_validation/5_data_structure_test.py` | **Teste de estrutura de dados** retornados pelo MT5 (2432 bytes). Validação one-time, não faz parte de CI/CD. | ⚠️ **ARQUIVAR** - Mover para pasta `/experiments/` |

---

### 🔍 Review Needed (4 arquivos)

Arquivos cujo **propósito não é claro** apenas pelo nome/estrutura. **Revisão manual necessária**.

| Arquivo | Justificativa | Ação Recomendada |
|---------|---------------|------------------|
| `test_database_strategies.py` | Nome genérico (4424 bytes). Pode testar estratégias de armazenamento no DB ou regras de negócio. **Necessário abrir o arquivo** para verificar se testa lógica ativa ou é experimento. | 🔍 **REVISAR MANUALMENTE** - Avaliar se testa código de produção |
| `validate_dashboard_playwright.py` | **Apenas 639 bytes** (~24 linhas). Valida dashboard Streamlit com `AppTest`. Pode ser relevante se dashboard está ativo, mas muito pequeno para julgar importância. | 🔍 **REVISAR MANUALMENTE** - Verificar se dashboard está em uso |
| `test_mt5_wsl_helper.sh` | **Script Bash** (2958 bytes) em meio a Python scripts. Nome sugere helper para rodar MT5 no WSL. Pode ser crítico para ambiente ou legacy. | 🔍 **REVISAR MANUALMENTE** - Avaliar necessidade no setup atual |
| `mt5_validation/0_find_mt5.py` | **Diagnóstico** que varre registro Windows e disco procurando `terminal64.exe`. Útil apenas em **setup inicial** de novos ambientes. Salva caminho em `mt5_path.txt`. | 🔍 **REVISAR** - Manter se usado em onboarding/setup automation |

---

## 🎯 Recomendações de Ação

### Fase 1: Remoção Segura (8 arquivos)
```bash
# Criar backup antes
mkdir -p archive/scripts_legacy_$(date +%Y%m%d)
mv scripts/explore_mt5_capabilities.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/test_binance_ws.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/test_data_collection.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/test_mt5_simple.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/test_mt5_connection_windows.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/test_mt5_db_integration.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/mt5_validation/4_stress_test.py archive/scripts_legacy_$(date +%Y%m%d)/
mv scripts/mt5_validation/5_data_structure_test.py archive/scripts_legacy_$(date +%Y%m%d)/
```

### Fase 2: Revisão Manual (4 arquivos)
1. **Agendar análise** dos arquivos marcados como "Review Needed"
2. **Ler o código** e documentar propósito
3. **Reclassificar** como QA, Infrastructure ou Legacy
4. **Adicionar docstring** se mantido, ou remover se legacy

### Fase 3: Organização
```bash
# Criar estrutura clara
scripts/
├── infrastructure/     # Critical (ex: mt5_bridge_service.py)
├── tests/             # QA (ex: test_end_to_end.py)
│   └── integration/
│   └── unit/
└── diagnostics/       # Tools pontuais (ex: mt5_validation/)
```

---

## 📈 Impacto Esperado

| Métrica | Antes | Depois | Redução |
|---------|-------|--------|---------|
| **Total de arquivos** | 22 | 14 | 36% ⬇️ |
| **Scripts legados** | 8 | 0 | 100% ⬇️ |
| **Clareza de propósito** | ~60% | 100% | 40% ⬆️ |
| **Linhas de código mantidas** | ~2000 | ~1200 | 40% ⬇️ |

---

## ⚠️ Avisos Importantes

> [!CAUTION]
> **NUNCA delete arquivos antes de**:
> 1. ✅ Criar backup em `archive/`
> 2. ✅ Verificar que não há imports em `src/`
> 3. ✅ Rodar suite de testes completa
> 4. ✅ Commit no git com mensagem descritiva

> [!IMPORTANT]
> Arquivos marcados como **Critical Infrastructure** gerenciam **operações financeiras reais**.  
> Remoção acidental pode causar:
> - ❌ Perda de conexão com MT5
> - ❌ Impossibilidade de executar trades
> - ❌ Pipeline de dados quebrada

---

## 📝 Checklist de Execução

- [ ] Fase 1: Criar branch `cleanup/scripts-hygiene`
- [ ] Fase 1: Executar backup para `archive/`
- [ ] Fase 1: Remover 8 arquivos Exploratory/Legacy
- [ ] Fase 1: Rodar `test_end_to_end.py` para validar pipeline
- [ ] Fase 2: Revisar manualmente 4 arquivos "Review Needed"
- [ ] Fase 2: Reclassificar e documentar
- [ ] Fase 3: Reorganizar estrutura de pastas
- [ ] Fase 3: Atualizar README.md com nova estrutura
- [ ] Fase 4: Commit, push e criar PR
- [ ] Fase 5: Code review com segundo par

---

## 🔗 Referências

- Conversa relacionada: `ce82b9be` (Market Context Classifier Tests)
- Projeto BD_Cau_V2: Governança aplicada em outro projeto similar
- Protocolo Operacional: Estudo → Plano → Aprovação → Execução → Prova

---

**Autor**: Antigravity (Senior Software Architect)  
**Próximo passo**: Aguardar aprovação do usuário para Fase 1
