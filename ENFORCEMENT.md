# Enforcement Mínimo: Instalação

## Hook instalado: `.githooks/pre-commit`

### O que bloqueia automaticamente:

1. **Novos arquivos em paths proibidos**
   - ❌ `scripts/` (deprecado)
   - ✅ Força uso de estrutura canônica

2. **Arquivos sem header obrigatório**
   ```python
   """
   @category: [production|infrastructure|test|tool|experiment]
   @impact: [critical|moderate|low|none]
   @description: Descrição breve
   """
   ```

3. **Imports proibidos**
   - ❌ `from experiments` em arquivos `src/`
   - Força Regra Congelada #1 (Separação de Domínios)

### Instalação:

```bash
# Ativar hook
cp .githooks/pre-commit .git/hooks/pre-commit

# Testar (sem staging)
python3 .githooks/pre-commit
```

### Bypass (emergências apenas):

```bash
git commit --no-verify -m "..."
```
**Requer justificativa em ADR se usado.**

---

## Diferença vs Documentos

| Aspecto | Documentos | Hook |
|---------|-----------|------|
| Previne violação | ❌ Depende de lembrar | ✅ Automático |
| Enforcement | ⚠️ Manual | ✅ Técnico |
| Pode ser ignorado | ✅ Fácil | ⚠️ Requer `--no-verify` |
| Custo de manutenção | 🟡 Documentos ficam obsoletos | 🟢 Código executa ou quebra |

**Resultado**: 80% do problema cortado na raiz.

---

## Próximo commit (exemplo):

### ❌ SEM hook:
```bash
# Eu crio script fora de estrutura
touch scripts/novo_teste_v03.py
git add scripts/novo_teste_v03.py
git commit -m "adiciona teste"
```
**Resultado**: Commit bem-sucedido → regressão

### ✅ COM hook:
```bash
touch scripts/novo_teste_v03.py
git add scripts/novo_teste_v03.py
git commit -m "adiciona teste"
```
**Output**:
```
🔒 Pre-commit: Validando governança estrutural...

📄 Validando: scripts/novo_teste_v03.py
  ❌ Path proibido: scripts/ (deprecado - use estrutura canônica)

🚫 COMMIT BLOQUEADO
```

**Resultado**: Regressão impedida tecnicamente.

---

## Limitações conhecidas:

1. **Não impede `git commit --no-verify`** 
   - Mitigação: Exigir ADR para uso de `--no-verify`

2. **Não valida arquivos já commitados**
   - Mitigação: Rodar `.githooks/pre-commit` manualmente em auditoria

3. **Não impede criação de arquivos fora de Git**
   - Mitigação: CI/CD pode rodar mesma validação

---

## Impacto vs Fases 2-4:

- **Fases 2-4**: Governança **declarativa** (documentos)
- **Hook**: Governança **operacional** (bloqueio técnico)

**Complementares**, não substitutos.

Documentos = "o que fazer"  
Hook = "impede fazer errado"

---

**Status**: Enforcement mínimo implementado.  
**Ação necessária**: `cp .githooks/pre-commit .git/hooks/pre-commit`
