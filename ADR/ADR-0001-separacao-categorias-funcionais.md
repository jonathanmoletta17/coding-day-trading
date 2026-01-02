# ADR-0001: Separação de Código em Categoria Funcional

**Status**: ✅ Aceito  
**Data**: 2026-01-02  
**Contexto**: Fase 1 - Organização Assistida por IA

---

## Decisão

Separar arquivos Python em 5 categorias funcionais distintas:
1. `src/` — Produção crítica apenas
2. `infrastructure/` — Serviços de runtime (bridges, collectors, ETL)
3. `tests/` — Testes essenciais de CI/CD
4. `tools/` — Ferramentas de desenvolvimento e debug
5. `archive/` — Código histórico preservado sem uso ativo
6. `experiments/` — Protótipos e PoCs isolados

---

## Motivo

### Problema:
- 23 arquivos misturados em `scripts/` sem distinção clara
- Impossível distinguir código crítico de experimental
- Risco de modificar experimento achando que é produção
- Onboarding lento devido a falta de estrutura

### Evidências que levaram à decisão:
1. Auditoria identificou:
   - 8 arquivos sem uso (impacto nulo confirmado via grep)
   - 3 infraestruturas críticas misturadas com testes
   - 6 ferramentas de diagnóstico sem organização

2. Riscos documentados:
   - Arquivo `mt5_bridge_service.py` é SPOF mas estava em `scripts/`
   - Testes E2E críticos misturados com experimentos manuais

---

## Alternativas Consideradas

### Opção A: Manter tudo em `scripts/` com prefixos
- **Rejeitada**: Prefixos (`prod_`, `test_`, `exp_`) não impedem confusão
- Risco: Deletar `prod_importante.py` pensando ser teste

### Opção B: Apenas `src/` e `tests/`
- **Rejeitada**: Não resolve mistura de infra, tools e experiments
- `mt5_bridge_service.py` não é library (`src/`) nem teste

### Opção C: Estrutura de 5 categorias (ESCOLHIDA)
- ✅ Separação clara por função
- ✅ Impossível confundir experimento com produção
- ✅ CI/CD pode focar em `tests/` apenas
- ✅ Ferramentas isoladas em `tools/`

---

## Riscos

1. **Imports quebrados após movimentação**
   - Mitigação: Scripts standalone não são importados
   - Validação: Testar imports de produção (`src/`) após mudanças

2. **Usuário se perde na nova estrutura**
   - Mitigação: README atualizado + `MIGRATION_GUIDE.md`
   - Estrutura intuitiva por nome

3. **CI/CD com paths hardcoded**
   - Mitigação: Documentar mudanças de path
   - Atualizar workflows (se existirem)

---

## Consequências

### Positivas:
- ✅ Clareza imediata de "o que é o quê"
- ✅ Redução de risco de mudança acidental em código crítico
- ✅ Onboarding acelerado (30min → 10min estimado)
- ✅ CI/CD simplificado (testar apenas `tests/`)

### Negativas:
- ⚠️ Migração one-time necessária (3h de trabalho)
- ⚠️ Documentação desatualizada temporariamente

---

## Critério de Reversão

Reverter se:
1. Mais de 50% dos usuários não conseguem navegar após 1 semana
2. Quebra de imports não resolvida em 48h
3. CI/CD não pode ser adaptado aos novos paths

**Reversão**: `git revert` do commit de reorganização

---

## Implementação

- **Branch**: `cleanup/archive-zero-impact`
- **Commits**:
  - Fase 2: Arquivar 8 arquivos de impacto nulo → [commit hash]
  - Fase 3-9: Reorganização estrutural → Pendente

- **Validação**:
  -✅ Imports de produção: OK
  - ✅ Testes unitários: 11/11 passando
  - ⏸️ Reorganização completa: Aguardando aprovação

---

## Referências

- `STRUCTURAL_CLEANUP_PLAN.md` — Plano completo de reorganiz

ação
- `VALIDATION_REPORT.md` — Prova de que sistema funciona pós-limpeza
- `PHASE1_UNCERTAINTY_RESOLUTION.md` — Grep analysis de impacto
