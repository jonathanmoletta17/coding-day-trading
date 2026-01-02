# 🔒 REGRAS CONGELADAS

**Versão**: 1.0  
**Data**: 2026-01-02  
**Status**: IMUTÁVEL até ADR explicit

o

---

## 📜 O QUE SÃO REGRAS CONGELADAS?

Regras que **NÃO** são reavaliadas em cada tarefa.  
São **princípios arquiteturais** que só mudam via ADR com justificativa explícita.

**Objetivo**: Eliminar regressões conceituais, não só técnicas.

---

## 🚫 REGRA #1: SEPARAÇÃO DE DOMÍNIOS

### Declaração:
```
Código em experiments/ NUNCA roda em produção.
Código em src/ NUNCA é experimental.
```

### Rationale:
- Sistema financeiro não pode ter "PoC em produção"
- Mistura de domínios = risco de deploy acidental

### Gatilhos de violação:
- ❌ Mover arquivo de `experiments/` para `src/` sem ADR
- ❌ Importar módulo de `experiments/` em código de `src/`
- ❌ Marcar código `src/` como "prototype" em docstring

### Exceção permitida:
- Graduação consciente: `experiments/X` → validação exaustiva → ADR → `src/X`

---

## 🚫 REGRA #2: SCRIPTS NÃO SÃO SERVIÇOS

### Declaração:
```
Scripts são executáveis one-shot.
Serviços são processos persistentes.
Scripts não vão para infrastructure/.
```

### Rationale:
- `infrastructure/` é para componentes de runtime (mt5_bridge, collectors, docker)
- Scripts são ferramentas (diagnóstico, validação, runners)

### Gatilhos de violação:
- ❌ Mover `tools/diagnostics/X.py` para `infrastructure/`
- ❌ Chamar arquivo que roda daemon de "script"

### Exceção permitida:
- Script que evolui para serviço deve ser renomeado e movido com ADR

---

## 🚫 REGRA #3: IMPACTO NULO EXIGE PROVA

### Declaração:
```
Declarar "arquivo não usado" sem grep é proibido.
Declarar "teste passa" sem executar é proibido.
```

### Rationale:
- Sistema financeiro não aceita suposições
- "Deve funcionar" causou incidentes históricos

### Gatilhos de violação:
- ❌ "Este arquivo parece não ser usado"
- ❌ "O código deve passar nos testes"
- ❌ "Provavelmente funciona porque..."

### Prova mínima exigida:
- Para "não usado": `grep -r "nome_arquivo" src/ scripts/` → 0 resultados
- Para "teste passa": Execução real → Exit code 0 → Output mostrado

---

## 🚫 REGRA #4: MODIFICAÇÃO DE PRODUÇÃO = VALIDAÇÃO OBRIGATÓRIA

### Declaração:
```
Mudanças em src/* requerem:
1. Teste de import após mudança
2. Execução de testes unitários (se disponíveis)
3. Documentação de o que foi testado
```

### Rationale:
- Código em `src/` afeta decisões financeiras
- Quebra silenciosa = perda de oportunidade ou capital

### Gatilhos de violação:
- ❌ Editar `src/microstructure/models.py` → commit → "mudança aplicada"
- ❌ Refatorar sem rodar `test_dsl_v01_unittest.py`

### Prova mínima exigida:
```bash
# Após mudar src/microstructure/models.py:
python3 -c "from src.microstructure import models"  # Import OK?
PYTHONPATH=. python3 scripts/test_dsl_v01_unittest.py  # Testes passam?
```

---

## 🚫 REGRA #5: GIT MV, NUNCA RM

### Declaração:
```
Arquivos são movidos com git mv, nunca deletados com rm.
Histórico Git é rastreabilidade obrigatória.
```

### Rationale:
- Trading exige auditoria completa
- `rm` perde histórico de quem/quando/por quê
- `git mv` preserva evolução do arquivo

### Gatilhos de violação:
- ❌ `rm arquivo.py`
- ❌ `mv arquivo.py archive/` (sem git)

### Comando correto:
```bash
git mv arquivo.py archive/2026-01-02/
git commit -m "archive: motivo claro"
```

---

## 🚫 REGRA #6: INCERTEZAS BLOQUEANTES IMPEDEM CONCLUSÃO

### Declaração:
```
Tarefa com incerteza bloqueante documentada não pode ser concluída.
"Dashboard status: unknown" bloqueia decisão sobre 6 arquivos.
```

### Rationale:
- Decidir sob incerteza = acumular dívida técnica
- "Resolver depois" vira "nunca resolver"

### Gatilhos de violação:
- ❌ "Dashboard não testado, mas limpeza concluída"
- ❌ "Impacto incerto, mas vamos mover mesmo assim"

### Resolução obrigatória:
1. Executar teste que resolve incerteza
2. OU documentar decisão de prosseguir com risco aceito
3. OU bloquear tarefa até resolução

---

## 🚫 REGRA #7: ZERO PERDA DE INFORMAÇÃO

### Declaração:
```
Nenhum arquivo é deletado permanentemente.
Archive/ preserva histórico de experimentos.
Commits documentam razão de cada mudança.
```

### Rationale:
- Código descartado hoje pode ter insight amanhã
- Experimentos falhados ensinam o que não fazer
- Histórico é conhecimento institucional

### Gatilhos de violação:
- ❌ `git rm --cached arquivo.py` sem mover para archive/
- ❌ Commit genérico: "cleanup files"

### Commit model:
```bash
git commit -m "archive: move 8 zero-impact files to archive/2026-01-02

Arquivos sem uso detectado:
- 3 testes obsoletos (substituídos por test_end_to_end.py)
- 5 módulos experimentais sem referências ativas

Verificado via grep recursivo.
Ref: PHASE1_UNCERTAINTY_RESOLUTION.md"
```

---

## 🚫 REGRA #8: ADR PARA DECISÕES ESTRUTURAIS

### Declaração:
```
Decisões que afetam arquitetura geram ADR.
Exemplos: Reorganização de diretórios, mudança de padrão, deprecação de módulo.
```

### Rationale:
- Evita rediscutir mesma decisão
- Documenta alternativas rejeitadas
- Fornece critério de reversão

### Gatilhos de ADR obrigatório:
- ✅ Criar nova categoria de diretório (`infrastructure/`)
- ✅ Mover 5+ arquivos de uma vez
- ✅ Deprecar módulo usado em produção
- ✅ Mudar convenção de nomenclatura

### Não requer ADR:
- Pequenas refatorações internas (< 50 linhas)
- Correção de bugs pontuais
- Atualização de documentação

---

## 📋 CHECKLIST DE CONFORMIDADE

Antes de concluir tarefa crítica, verificar:

- [ ] ✅ Separação de domínios respeitada (Regra #1)
- [ ] ✅ Scripts vs Serviços correto (Regra #2)
- [ ] ✅ Impacto provado com grep/teste (Regra #3)
- [ ] ✅ Produção validada pós-mudança (Regra #4)
- [ ] ✅ Movimentações via `git mv` (Regra #5)
- [ ] ✅ Incertezas bloqueantes resolvidas (Regra #6)
- [ ] ✅ Zero perda de informação (Regra #7)
- [ ] ✅ ADR criado se aplicável (Regra #8)

---

## 🔓 PROCESSO DE ALTERAÇÃO DE REGRA

### Uma Regra Congelada pode mudar?

**Sim**, mas com processo formal:

1. **Criar ADR** propondo mudança
2. **Justificar** por quê regra não se aplica mais
3. **Documentar** casos onde regra atual falhou
4. **Propor** nova regra ou exceção
5. **Aprovar** explicitamente (humano)
6. **Atualizar** este documento com nova versão

### Exemplo de mudança válida:
```
ADR-0042: Relaxar Regra #2 para permitir "Serviços Leves"

Contexto: 
Alguns scripts evoluíram para daemons simples (< 100 linhas)
mas não são infraestrutura crítica.

Proposta:
Criar infrastructure/lightweight/ para serviços não-críticos.

Justificativa:
...
```

---

## 🔐 ASSINATURA DE VIGÊNCIA

**Estas regras entram em vigor imediatamente.**

**Revisão obrigatória**: A cada 6 meses OU após 20 tarefas críticas.

**Última atualização**: 2026-01-02  
**Próxima revisão**: 2026-07-02

---

**Declaração de Conformidade**:  
Ao executar tarefas neste projeto, o modelo reconhece estas regras como imutáveis até alteração via ADR.
