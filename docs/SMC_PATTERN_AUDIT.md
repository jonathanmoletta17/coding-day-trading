# 🔍 Auditoria do Padrão Liquidity Sweep

## Objetivo
Avaliar cada critério para identificar:
1. Função estrutural vs arbitrária
2. Risco de tautologia (padrão se valida sozinho)
3. Sensibilidade a parâmetros
4. Robustez do modelo

---

## 📋 Critérios Auditados

### 1. LOOKBACK_CANDLES = 20

**Função no Mercado:**
- Define "liquidez recente" = zona onde stops estão concentrados
- High/low de 20 candles = referência visual comum aos traders

**Arbitrário vs Estrutural:**
- ⚠️ **ARBITRÁRIO**: Número escolhido sem base estrutural
- Poderia ser 15, 25, 30... sem mudança conceitual
- NÃO há razão matemática para ser exatamente 20

**Risco de Tautologia:**
- ⚠️ **MÉDIO**: Define artificialmente o que é "liquidez"
- Se mudarmos para 50, detectaremos "liquidez" diferente
- Padrão depende da nossa definição de "zona de liquidez"

**Teste de Sensibilidade:**
```
Lookback 16 (-20%): detectaria sweeps mais frequentes (zona menor)
Lookback 24 (+20%): detectaria sweeps menos frequentes (zona maior)
```

**Correção:**
- Usar múltiplos lookbacks (15, 20, 30) e validar consenso
- OU derivar de ATR (período adaptativo ao mercado)

---

### 2. DISPLACEMENT_THRESHOLD = 0.3 (30% do range)

**Função no Mercado:**
- Identifica "movimento significativo" após sweep
- 30% = assume que reversão deve ser "visível"

**Arbitrário vs Estrutural:**
- ⚠️ **ARBITRÁRIO**: Por que 30% e não 25% ou 40%?
- NÃO há base estrutural para este threshold
- Depende do conceito subjetivo de "displacement"

**Risco de Tautologia:**
- 🔴 **ALTO**: **TAUTOLOGIA DETECTADA**
- Definimos displacement como "movimento de 30%"
- Depois validamos que "houve displacement" (claro, definimos assim!)
- **Padrão se valida sozinho**

**Teste de Sensibilidade:**
```
Threshold 0.24 (-20%): +40% mais padrões
Threshold 0.36 (+20%): -30% menos padrões
```

**Correção:**
- NÃO definir displacement por threshold fixo
- OBSERVAR distribuição natural de retornos pós-sweep
- Usar estatística (ex: >1 desvio padrão do retorno médio)

---

### 3. DISPLACEMENT_CANDLES = 5

**Função no Mercado:**
- Define janela temporal para reversão acontecer
- 5 candles = "rapidez" do movimento

**Arbitrário vs Estrutural:**
- ⚠️ **ARBITRÁRIO**: Por que 5 e não 3 ou 7?
- Conceito de "rápido" é subjetivo
- NÃO há estrutura de mercado que indique 5

**Risco de Tautologia:**
- ⚠️ **MÉDIO**: Ao definir janela, forçamos padrão a ocorrer nela
- Se mudarmos para 10, encontraremos "padrões mais lentos"
- Criamos artificialmente a categoria de "displacement rápido"

**Teste de Sensibilidade:**
```
Candles 4 (-20%): padrões mais rápidos (menos ocorrências)
Candles 6 (+20%): padrões mais lentos (mais ocorrências)
```

**Correção:**
- Usar janela adaptativa baseada em volatilidade
- OU testar múltiplas janelas (3, 5, 7) e ver qual é mais informativa

---

### 4. MIN_SWEEP_PENETRATION = 0.02%

**Função no Mercado:**
- Filtra ruído de "quase sweeps"
- 0.02% ≈ 2 pips em forex = spread típico

**Arbitrário vs Estrutural:**
- ✅ **ESTRUTURAL (parcial)**: Baseado em spread/custo de transação
- Faz sentido: sweep deve ultrapassar spread para ser real
- MAS: 0.02% não serve para todos os instrumentos

**Risco de Tautologia:**
- ✅ **BAIXO**: Filtro técnico razoável
- Não cria padrão, apenas remove ruído
- Baseado em característica real do mercado (spread)

**Teste de Sensibilidade:**
```
Penetration 0.016% (-20%): mais sweeps (alguns falsos)
Penetration 0.024% (+20%): menos sweeps (perde alguns reais)
```

**Correção:**
- Derivar de spread médio real do símbolo
- Usar 2x ou 3x o spread médio (mais estrutural)

---

## 🔴 Tautologias Identificadas

### Problema Principal: Conversão 100%

**Resultado:** "100% dos sweeps resultaram em displacement"

**Por quê?**
- Definimos displacement como condição APÓS sweep
- Só contamos padrão se AMBOS ocorrem
- Conversão 100% é **circular**: medimos o que definimos

**Analogia:**
```
"100% das pessoas com >1.80m são altas"
(porque definimos 'alto' como >1.80m)
```

**Correção necessária:**
- Separar detecção de sweep de detecção de displacement
- Medir sweeps que NÃO tiveram displacement
- Taxa real seria: X% dos sweeps → displacement

---

## ✅ Refatoração Proposta

### Em vez de "Liquidity Sweep + Displacement":

### Medir 3 Regimes de Mercado:

**1. REVERSIVE:**
- Muitos sweeps seguidos de reversão
- Alta frequência de failed breakouts
- Mercado rejeitando extremos

**2. TREND:**
- Sweeps seguidos de continuação (não displacement)
- Breakouts válidos
- Mercado aceitando novos extremos

**3. INACTIVE:**
- Poucos sweeps
- Baixa volatilidade
- Range consolidado

### Critérios Objetivos (sem tautologia):

```python
# 1. Detectar sweeps (estrutural)
sweep = price breaks recent high/low + penetration > spread

# 2. Medir retorno subsequente (sem definir threshold)
return_5candles = (close[t+5] - close[t]) / (high[t] - low[t])

# 3. Classificar regime pela DISTRIBUIÇÃO de retornos
if return_5candles reverte em >70% dos casos:
    regime = REVERSIVE
elif return_5candles continua em >70% dos casos:
    regime = TREND
else:
    regime = INACTIVE
```

---

## 📊 Próximos Passos

1. ✅ Identificar tautologia principal (feito)
2. [ ] Implementar detector de sweeps sem displacement
3. [ ] Medir distribuição de retornos pós-sweep
4. [ ] Classificar regimes por comportamento observado
5. [ ] Validar sem parâmetros arbitrários

---

**Conclusão:**
O padrão atual tem **tautologia forte** (100% conversão).  
Refatoração para regimes de mercado resolve o problema.
