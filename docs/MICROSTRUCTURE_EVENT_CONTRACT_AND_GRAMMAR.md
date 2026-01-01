# Contrato de Eventos Microestruturais e Gramática de Padrões (Especificação)

Este documento formaliza:
- Um contrato de eventos para um sistema baseado em order book e fluxo, onde eventos representam apenas fatos observáveis ou derivações determinísticas.
- Uma DSL (gramática) para detecção de padrões recorrentes baseada exclusivamente nos eventos permitidos e no estado reconstruído por replay determinístico.

Regras deste documento:
- Linguagem normativa: **MUST** (obrigatório), **SHOULD** (recomendado), **MAY** (opcional), **MUST NOT** (proibido).
- Termos interpretativos (ex.: “intenção”, “pressão”, “absorção”, “spoofing”, “defensivo/ofensivo”) **MUST NOT** existir no nível de evento ou de padrão.
- O sistema **MUST** funcionar sob diferentes níveis de observabilidade (L2 snapshot, L2 incremental, L3).
- Onde o feed não distingue causa (cancelamento vs execução), nenhuma semântica deve ser inferida: o contrato **MUST NOT** “preencher” essa lacuna.

## 1. Escopo e Objetivos

### 1.1 Objetivo
- Preservar causalidade observável e integridade do log.
- Permitir reconstrução determinística do estado do book por replay de eventos.
- Permitir detecção determinística de padrões recorrentes como subsequências de eventos, sob restrições temporais e contexto de estado reconstruído.

### 1.2 Fora de escopo
- Definir regimes de mercado.
- Recomendações operacionais, trading, ou ações prescritivas.
- Métricas estatísticas (distribuições, estimadores, modelos).
- Qualquer forma de previsão ou modelos de aprendizado.

## 2. Definições (vocabulário mínimo)

- **Log**: sequência de eventos ordenável por chaves de ordenação canônica.
- **Segmento íntegro**: intervalo contíguo do log sem `SEQUENCE_GAP` e sem `BOOK_RESET`.
- **Evento base**: evento primário emitido pela fonte (ou normalizado sem mudar semântica).
- **Evento derivado**: evento produzido por regra determinística a partir de evento(s) base + estado reconstruído.
- **Estado reconstruído**: materialized view do book (`S(t)`) resultante do replay determinístico do log dentro de um segmento íntegro.
- **Padrão**: ocorrência detectada como subsequência de eventos dentro de um segmento íntegro, com janela temporal, repetição e predicados sobre estado reconstruído.

## 3. Contrato de Eventos

### 3.1 Conjunto permitido de tipos (fechado)

Eventos base permitidos:
- `BOOK_SNAPSHOT`
- `LEVEL_SET`
- `TRADE_PRINT`
- `SEQUENCE_GAP`
- `BOOK_RESET`

Eventos derivados permitidos (apenas determinísticos):
- `LIQUIDITY_ADD`
- `LIQUIDITY_REMOVE`
- `CANCEL` (apenas se explicitamente observado)
- `EXECUTION_BY_AGGRESSION` (apenas se explicitamente observado)
- `REPLENISH_AFTER_CONSUMPTION`
- `LEVEL_SHIFT`

O sistema **MUST NOT** introduzir novos tipos primários fora desta lista.

### 3.2 Envelope comum (campos obrigatórios para qualquer evento)

Todo evento **MUST** carregar:
- `event_id`: identificador globalmente único e estável (para idempotência).
- `event_type`: um dos tipos permitidos.
- `instrument_id`: identificador do ativo.
- `venue`: local de negociação/mercado/fonte econômica.
- `source`: canal/stream de origem (ex.: “depth”, “trades”, “l3”).
- `ts_recv`: timestamp local de recebimento (sempre presente).
- `ts_event`: timestamp da origem (quando fornecido pela origem; **MAY** ser ausente).
- `source_seq`: sequência monotônica da origem (quando fornecida; **MAY** ser ausente).

Justificativa:
- `event_id` garante idempotência.
- `instrument_id`, `venue`, `source` garantem separação de microestruturas e streams.
- `ts_recv`, `ts_event`, `source_seq` garantem ordenação e detecção de descontinuidade.

Campos proibidos no envelope:
- Qualquer campo interpretativo ou que dependa de inferência não observável.

### 3.3 Tipos base: semântica, limites e payload mínimo

#### 3.3.1 `BOOK_SNAPSHOT`

**Definição microestrutural**
- Fotografia do book (completo ou top-N) em um instante, para uso como checkpoint do replay.

**O que significa**
- Estado exibido no instante do snapshot, no escopo de observabilidade da fonte.

**O que não significa**
- Não afirma persistência no tempo.
- Não afirma executabilidade futura.
- Não afirma origem causal de tamanhos (adição, remoção, execução).

**Payload mínimo**
- `bids`: lista de pares `(price, size)` agregados e ordenados por preço desc.
- `asks`: lista de pares `(price, size)` agregados e ordenados por preço asc.
- `depth_limit`: inteiro N se snapshot for top-N; **MAY** ser ausente se for completo.

**Campos derivados aceitáveis**
- Normalizações formais (ex.: arredondamento ao tick) desde que reversíveis e explícitas.

**Campos proibidos**
- “mid”, “spread”, “imbalance”, rótulos de regime e quaisquer interpretações.

#### 3.3.2 `LEVEL_SET`

**Definição microestrutural**
- Define o tamanho agregado exibido em um nível de preço: `(side, price) -> new_size`.

**O que significa**
- A fonte afirma que o tamanho exibido naquele nível passou a ser `new_size`.

**O que não significa**
- Não distingue causa (adição, cancelamento, execução), a menos que a fonte explicite.
- Não contém identidade de ordens/participantes em L2 agregado.

**Payload mínimo**
- `side`: `BID` | `ASK`.
- `price`: preço do nível.
- `new_size`: tamanho agregado exibido após o update (>= 0).

**Campos derivados aceitáveis (apenas determinísticos)**
- `old_size`: tamanho anterior do mesmo nível, derivado do estado reconstruído.
- `delta_size`: `new_size - old_size`, derivado do estado reconstruído.
- `level_index`: índice no top-N, derivado do estado reconstruído (utilitário, não econômico).

**Campos proibidos**
- `cause = CANCEL/EXECUTE` quando a fonte não fornece.
- `aggressor_side` inferido.
- qualquer rótulo interpretativo.

#### 3.3.3 `TRADE_PRINT`

**Definição microestrutural**
- Registro publicado de execução (negócio), com preço, tamanho e timestamp.

**O que significa**
- Ocorreu uma execução publicada pela fonte.

**O que não significa**
- Não garante redução de liquidez visível no L2 (pode envolver liquidez não exibida).
- Não garante o lado agressor, a menos que a fonte explicite.

**Payload mínimo**
- `price`
- `size` (> 0)
- `trade_id` (se fornecido; **MAY** ser ausente)
- `aggressor_side` (apenas se explicitamente fornecido; **MAY** ser ausente)

**Campos proibidos**
- “consumiu o nível X” sem mapeamento observável.
- “foi cancelamento disfarçado” e equivalentes.

#### 3.3.4 `SEQUENCE_GAP` e `BOOK_RESET`

**Definição microestrutural**
- Evento de integridade do log: perda de mensagens (`SEQUENCE_GAP`) ou reinicialização do stream (`BOOK_RESET`).

**O que significa**
- Causalidade observável foi interrompida. Replay determinístico exige ressíncrono (tipicamente por snapshot).

**O que não significa**
- Não é fenômeno econômico.

**Payload mínimo**
- `expected_seq_range` (quando aplicável).
- `recovery_action` (ex.: “require_snapshot”).

### 3.4 Tipos derivados: regras determinísticas (semântica e limites)

#### 3.4.1 `LIQUIDITY_ADD`
- Derivado de `LEVEL_SET` quando `delta_size > 0` (com `delta_size` determinístico do estado).
- **MUST NOT** ser emitido se não existir `old_size` determinístico.

#### 3.4.2 `LIQUIDITY_REMOVE`
- Derivado de `LEVEL_SET` quando `delta_size < 0`.
- Não distingue cancelamento vs execução.

#### 3.4.3 `CANCEL`
- Só pode existir quando a fonte fornece explicitamente cancelamento (L3 ou flags inequívocas).
- **MUST NOT** ser derivado de L2 agregado sem suporte explícito.

#### 3.4.4 `EXECUTION_BY_AGGRESSION`
- Só pode existir quando a fonte fornece execução com vínculo causal observável (L3 match ou marcação inequívoca).
- **MUST NOT** ser inferido de co-ocorrência de `TRADE_PRINT` e `LEVEL_SET`.

#### 3.4.5 `REPLENISH_AFTER_CONSUMPTION`
- Derivado apenas como relação temporal entre episódios definidos por eventos permitidos:
  - “consumption” só existe se observado explicitamente (`EXECUTION_BY_AGGRESSION`) ou por redução L2 sem causa (ainda assim, o nome do derivado é fixo e não implica causa).
- **MUST** referenciar (via ids) os eventos antecedentes usados na derivação.

#### 3.4.6 `LEVEL_SHIFT`
- Derivado quando mudanças no recorte top-N decorrem apenas de inserções/remoções em preços melhores, sem que um nível específico tenha “mudado economicamente”.
- Utilitário para normalizar o “efeito rank” do top-N.

## 4. Invariantes Microestruturais (não violáveis)

### 4.1 Determinismo de replay
- O estado reconstruído **MUST** ser uma função determinística de:
  - snapshot(s) + eventos ordenados, dentro de um segmento íntegro.
Risco ao violar:
- Perda de reprodutibilidade; padrões deixam de ser invariantes do log.

### 4.2 Não negatividade e domínio de valores
- `new_size >= 0` em `LEVEL_SET`.
- `size > 0` em `TRADE_PRINT`.
Risco:
- Estado impossível e corrupção de derivações baseadas em delta.

### 4.3 Idempotência
- Reprocessar o mesmo `event_id` **MUST NOT** alterar o estado mais de uma vez.
Risco:
- Dupla contagem de mudanças e padrões falsos.

### 4.4 Integridade de ordenação e barreira de gaps
- Se `source_seq` existir, deve ser monotônico por stream; gaps **MUST** gerar `SEQUENCE_GAP/BOOK_RESET`.
- Padrões **MUST NOT** atravessar gaps/resets.
Risco:
- Eventos fora de ordem criam transformações artificiais e não reprodutíveis.

### 4.5 Separação entre streams
- `TRADE_PRINT` **MUST NOT** “mutar” estado do book L2 se o book é reconstruído por `LEVEL_SET`; apenas correlação temporal é permitida.
Risco:
- Double counting de consumo e estados inconsistentes.

## 5. Relação Evento → Estado

### 5.1 Princípio
- Estado do book é uma **materialized view**; eventos são a fonte primária.
- `S(t)` é obtido por replay determinístico dentro de um segmento íntegro.

### 5.2 Estado observável vs estado inferido
- Observável: mapa `(side, price) -> size` e funções mecânicas derivadas dele (top-N, touch, spread em ticks).
- Inferido: qualquer rótulo explicativo (proibido nesta camada).

### 5.3 Consequência
- Qualquer módulo posterior (FSM/regimes) **MUST** consumir:
  - eventos e padrões detectados, nunca snapshots como “verdade primária”.

---

# Gramática de Padrões (DSL)

## 6. Princípios da DSL
- Opera apenas sobre eventos permitidos + consultas mecânicas ao estado reconstruído.
- Sempre determinística: mesmo log → mesmas ocorrências.
- Padrões são definidos por: sequência + condições temporais + contexto de estado + início/término.
- Padrões **MUST NOT** atravessar `SEQUENCE_GAP` ou `BOOK_RESET`.

## 7. Ordenação canônica do log (para matching)
Dentro de `(venue, instrument_id, source)`:
1) `source_seq` (se presente)  
2) `ts_event`  
3) `ts_recv`  
4) `event_id`  

## 8. Whitelist de consultas ao estado reconstruído
Consultas permitidas:
- `S_PRE(e).touch_price(side)`
- `S_PRE(e).best_bid_price`, `S_PRE(e).best_ask_price`
- `S_PRE(e).spread_ticks`
- `S_PRE(e).level_size(side, price)`
- `S_PRE(e).top_n(side, N)`
- `tick_distance(price_a, price_b)`
- `prices_in_range(side, from_price, to_price)`

Consultas proibidas:
- qualquer função que devolva rótulo interpretativo ou “explicação”.

## 9. Sintaxe textual mínima (DSL)

```text
DERIVE <DerivedType> FROM <BaseType> WHEN <predicate>

PATTERN <Name>(<params...>):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN <window_ms>
  LET <id> = <expr>
  MATCH <expression>
  START: <start_rule>
  END:   <end_rule>
  EMIT { <fields...> }
  DESC: <descrição operacional>

<expression> pode ser:
  SEQUENCE <id>: <event_bind>... [WITHIN][MAX_GAP][REPEAT>=][DISTINCT>= BY]
  ALL_OF(expr, expr, ...)
  ANY_OF(expr, expr, ...)
  NONE_OF(expr)
  HOLD(predicate_over_state) FOR <duration_ms>
```

## 10. Catálogo inicial de padrões (operacionais e mecânicos)

### 10.1 DepletionSequence
```text
PATTERN DepletionSequence(side, n_ticks, k, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT r: LIQUIDITY_REMOVE WHERE
      r.side == side AND
      tick_distance(r.price, S_PRE(r).touch_price(side)) <= n_ticks
  WITHIN window_ms REPEAT>= k
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, remove_count=k, distinct_prices=COUNT_DISTINCT(r.price) }
  DESC: Reduções repetidas de size exibido em níveis a ≤ n_ticks do touch do mesmo lado.
```

### 10.2 MultiLevelErosion
```text
PATTERN MultiLevelErosion(side, n_ticks, min_levels, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT r: LIQUIDITY_REMOVE WHERE
      r.side == side AND
      tick_distance(r.price, S_PRE(r).touch_price(side)) <= n_ticks
  WITHIN window_ms DISTINCT>= min_levels BY r.price
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, levels=min_levels }
  DESC: Remoções distribuídas por múltiplos preços próximos ao touch.
```

### 10.3 TouchRepriceWithoutPrint
```text
PATTERN TouchRepriceWithoutPrint(side, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  LET p0 = S_PRE(e0).touch_price(side)
  MATCH ALL_OF(
    SEQUENCE T:
      EVENT e0: LEVEL_SET WHERE TRUE
      EVENT e1: LEVEL_SET WHERE S_POST(e1).touch_price(side) != p0
    WITHIN window_ms,
    NONE_OF(
      SEQUENCE Z:
        EVENT t: TRADE_PRINT WHERE t.price == p0
      WITHIN window_ms
    )
  )
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, touch_from=p0, touch_to=S_POST(e1).touch_price(side) }
  DESC: Alteração do touch observada via updates do book, sem prints no preço do touch anterior na janela.
```

### 10.4 PrintClusterAtTouch
```text
PATTERN PrintClusterAtTouch(side, k, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT t: TRADE_PRINT WHERE t.price == S_PRE(t).touch_price(side)
  WITHIN window_ms REPEAT>= k
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, trade_count=k }
  DESC: Conjunto de prints ocorrendo no preço do touch do lado especificado no instante de cada print.
```

### 10.5 LevelFlickerSequence
```text
PATTERN LevelFlickerSequence(side, price, toggles, max_gap_ms, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT a: LIQUIDITY_ADD    WHERE a.side==side AND a.price==price
    EVENT r: LIQUIDITY_REMOVE WHERE r.side==side AND r.price==price
  WITHIN window_ms MAX_GAP max_gap_ms REPEAT>= toggles
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, price, toggles=toggles }
  DESC: Alternância rápida de aumentos e reduções do size exibido no mesmo nível.
```

### 10.6 SpreadExpansionSequence
```text
PATTERN SpreadExpansionSequence(min_increase_ticks, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT u: LEVEL_SET WHERE
      S_POST(u).spread_ticks >= S_PRE(u).spread_ticks + min_increase_ticks
  WITHIN window_ms
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, spread_delta_ticks=min_increase_ticks }
  DESC: Aumento do spread observado como mudança discreta do estado pré para o pós update.
```

### 10.7 ReplenishAfterDepletionSequence (composição)
```text
PATTERN ReplenishAfterDepletionSequence(side, n_ticks, k_depl, w_depl_ms, k_add, w_rec_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN (w_depl_ms + w_rec_ms)
  MATCH ALL_OF(
    PATTERN_REF DepletionSequence(side, n_ticks, k_depl, w_depl_ms) AS D,
    SEQUENCE R:
      EVENT a: LIQUIDITY_ADD WHERE
        a.side == side AND
        tick_distance(a.price, S_PRE(a).touch_price(side)) <= n_ticks
    WITHIN w_rec_ms REPEAT>= k_add AFTER D.end
  )
  START: D.start
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, depl_count=k_depl, add_count=k_add }
  DESC: Após uma sequência de remoções próximas ao touch, ocorrem adições na mesma zona dentro de janela posterior.
```

## 11. Regras de composição (padrões → padrões)

### 11.1 Operadores permitidos
- `ALL_OF`: conjunção (co-ocorrência controlada).
- `ANY_OF`: disjunção.
- `NONE_OF`: ausência explícita numa janela.
- `SEQUENCE`: concatenação ordenada.
- `PATTERN_REF`: reutilização com vínculo explícito de `start`/`end`.

### 11.2 Restrições obrigatórias
- Um padrão composto **MUST** impor integridade no intervalo união (barreira de gap/reset).
- Um padrão composto **MUST** declarar relações temporais (`AFTER`, `BEFORE`, `WITHIN`, `MAX_GAP`) para evitar múltiplos matchings válidos.
- Um padrão composto **MUST NOT** declarar causalidade não observável entre `TRADE_PRINT` e `LEVEL_SET`; apenas co-ocorrência temporal e contexto de estado são permitidos.
- Um padrão **MUST NOT** introduzir novos campos interpretativos no `EMIT`.

## 12. Limites explícitos da linguagem

### 12.1 Não expressável por design
- Atribuir `CANCEL` ou `EXECUTION_BY_AGGRESSION` em feeds L2 onde isso não é observado.
- Determinar lado agressor de um trade quando a fonte não fornece.
- Atribuir trade a níveis específicos do L2 agregado sem vínculo observável.
- Produzir estados/labels de regime.

### 12.2 Fronteira com a camada de regimes (posterior)
Esta DSL:
- Detecta ocorrências `P(start,end)` reprodutíveis, com contagens e referências mecânicas.

A camada posterior (FSM/classificador) pode:
- Agregar ocorrências ao longo do tempo e criar estados/rotulagens, desde que não retroalimente o nível de evento/padrão com semântica interpretativa.

