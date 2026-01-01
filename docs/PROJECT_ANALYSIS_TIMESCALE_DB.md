# ANÁLISE TÉCNICA E PLANO DE IMPLEMENTAÇÃO: Persistência de Dados HFT (TimescaleDB)

**Data:** 03/12/2025
**Responsável:** Trae AI (Senior System Architect)
**Referência:** Auditoria 01 - Módulo Crypto HFT
**Versão do Documento:** 1.0

---

## 1. Especificação de Requisitos

### 1.1. Requisitos Técnicos (Arquitetura & Infraestrutura)
*   **Motor de Banco de Dados:** TimescaleDB (Extensão do PostgreSQL).
    *   *Justificativa:* Otimizado para séries temporais, particionamento automático (hypertables) e alta taxa de ingestão (ingestion rate).
*   **Método de Deploy:** Docker Container (Linux image via WSL2 no Windows).
    *   *Isolamento:* Mantém o ambiente do Windows limpo.
*   **Interface de Conexão:** Driver `psycopg2-binary` ou `asyncpg` (para Python).
*   **Requisitos de Hardware (Alocados):**
    *   RAM: 4GB reservados para Cache do PostgreSQL.
    *   Armazenamento: SSD NVMe (Crítico para escrita de logs WAL).

### 1.2. Requisitos Funcionais (Regras de Negócio)
*   **RF01 - Persistência de Ticks (L1):** Armazenar cada atualização de preço (Last, Bid, Ask, Volume) com precisão de milissegundos.
*   **RF02 - Persistência de Snapshots (L2):** Armazenar o estado do Order Book (Top 20 levels) a cada X milissegundos ou quando houver mudança significativa.
*   **RF03 - Consulta Temporal:** Permitir queries como "Média do Spread nos últimos 10 minutos" com latência < 50ms.
*   **RF04 - Expurgo Automático:** Política de retenção de dados (Data Retention) para apagar dados brutos (raw) com mais de 7 dias, mantendo apenas agregados (candles).

### 1.3. Métricas de Sucesso (KPIs)
*   **Throughput de Escrita:** > 2.000 linhas/segundo sem travar a aplicação principal.
*   **Latência de Leitura:** < 100ms para renderizar o Heatmap histórico.
*   **Uptime:** O banco deve se recuperar automaticamente em caso de reinício do sistema.

---

## 2. Avaliação de Viabilidade

### 2.1. Estudo Técnico
*   **Compatibilidade:** Totalmente compatível com o ecossistema Python atual (`pandas` lê nativamente SQL). O Docker roda bem no Windows via WSL2.
*   **Recursos:** A máquina atual (64GB RAM, A4000) é superdimensionada para essa tarefa, garantindo zero impacto na performance do modelo de ML futuro.
*   **Restrições:** O Windows File System (NTFS) pode ser mais lento que EXT4 para banco de dados, mas o uso de Docker Volume mitiga parte disso.

### 2.2. Análise Econômica
*   **TCO (Custo Total de Propriedade):**
    *   Licença de Software: $0 (Open Source / Community Edition).
    *   Infraestrutura: $0 (Hardware já existente).
*   **ROI (Retorno sobre Investimento):**
    *   *Intangível:* Capacidade de realizar Backtesting realístico. Sem dados históricos de nível 2 (L2), é impossível validar estratégias de HFT. O ROI é a viabilização do próprio core business (trading algorítmico).

---

## 3. Planejamento Temporal (Cronograma)

### Fase 1: Preparação (Duração Estimada: 2h)
*   [ ] Instalação do Docker Desktop (se não houver) ou configuração do `docker-compose`.
*   [ ] Definição do arquivo `docker-compose.yml` com TimescaleDB e pgAdmin (interface visual).

### Fase 2: Modelagem de Dados (Duração Estimada: 3h)
*   [ ] Criação do Schema SQL (`init.sql`).
*   [ ] Definição das Hypertables (particionamento por tempo).
*   [ ] Otimização de índices (ex: índice composto `symbol` + `time`).

### Fase 3: Desenvolvimento da Integração (Duração Estimada: 6h)
*   [ ] Implementar classe `DatabaseHandler` (Singleton).
*   [ ] Atualizar `BinanceCollector` e `MT5Collector` para enviar dados para uma fila (Queue).
*   [ ] Criar *Worker* de persistência (Batch Insert) para não bloquear a thread de coleta.

### Fase 4: Validação e Testes (Duração Estimada: 4h)
*   [ ] Stress Test: Inserir dados simulados em alta velocidade.
*   [ ] Validação de integridade: Comparar dados do CSV/API com o Banco.

---

## 4. Gestão de Riscos

| Risco | Probabilidade | Impacto | Plano de Mitigação |
| :--- | :---: | :---: | :--- |
| **Gargalo de I/O (Disco)** | Média | Alto | Utilizar *Batch Inserts* (inserir 1000 linhas de uma vez) em vez de *Row-by-Row*. |
| **Crescimento Desenfreado do DB** | Alta | Médio | Configurar *Chunk Compression* e *Data Retention Policies* nativas do Timescale. |
| **Perda de Conexão DB** | Baixa | Alto | Implementar lógica de *Retry* e *Buffer Local* (memória) caso o DB caia. |
| **Conflito de Versão Python** | Baixa | Baixo | Usar ambiente virtual (já em uso) e fixar versões no `requirements.txt`. |

---

## 5. Validação e Qualidade

### Plano de Testes
1.  **Teste Unitário:**
    *   Verificar conexão com DB.
    *   Verificar criação automática de tabelas.
2.  **Teste de Integração:**
    *   Ligar o Coletor Crypto -> Verificar se dados aparecem no pgAdmin.
3.  **Teste de Carga (Stress Test):**
    *   Simular 50 ativos enviando 10 updates/segundo simultaneamente.
    *   *Critério de Aprovação:* Uso de CPU do container < 20% e Lag de inserção < 1s.

---

## 6. Documentação Formal e Próximos Passos

### Parecer Técnico
A implementação do TimescaleDB é a solução padrão-ouro para sistemas de Trading Quantitativo. Alternativas como arquivos simples (CSV/Parquet) não suportam concorrência de leitura/escrita necessária para um Dashboard em tempo real que também alimenta modelos de ML.

### Solicitação de Aprovação
Solicito autorização para iniciar a **Fase 1 (Preparação)**, que consiste na criação do arquivo de orquestração de containers (`docker-compose.yml`) e instalação das bibliotecas de conexão.

---
*Documento gerado automaticamente pelo Sistema Trae AI - Módulo de Auditoria.*
