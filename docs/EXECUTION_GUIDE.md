# 🎯 Guia de Execução Completa - Sistema MT5

## ✅ Status Atual

### Completado:
- [x] **PostgreSQL**: Rodando e acessível
- [x] **Database Schema**: 9 tabelas criadas com sucesso
- [x] **MT5 Bridge Service**: Implementado (`mt5_bridge_service.py`)
- [x] **Data Collector**: Implementado (`mt5_data_collector.py`)
- [x] **Testes End-to-End**: Script criado e parcialmente validado

### Resultados dos Testes Iniciais:
```
✓ PostgreSQL Connection: PASSOU
✓ Database Schema: PASSOU  
✓ Database Statistics: PASSOU
✗ MT5 Bridge API: Requer execução manual no Windows
✗ MT5 Account Info: Dependente do Bridge
✗ MT5 Tick Data: Dependente do Bridge
✗ MT5 Candle Data: Dependente do Bridge
✗ Data Insertion: Dependente do Bridge

Total: 3/8 testes passaram
```

---

## 🚀 Como Executar o Sistema Completo

### **PASSO 1: Iniciar o MT5 Bridge no Windows** ⚡ CRÍTICO

O MT5 Bridge **DEVE** rodar no Windows pois o MetaTrader5 só funciona lá.

#### Opção A: Via Explorador de Arquivos (Mais Fácil)

1. Abra o Explorador do Windows (`Windows + E`)
2. Navegue para: `C:\Users\jonathan-moletta`
3. **Duplo-clique** em `mt5_bridge_service.py`

OU se isso não funcionar:

4. Botão direito → "Abrir com" → "Python"

#### Opção B: Via PowerShell/CMD

```powershell
cd C:\Users\jonathan-moletta
python mt5_bridge_service.py
```

**Você verá:**
```
======================================================================
MT5 BRIDGE API - Starting...
======================================================================
[✓] MT5 inicializado e conectado
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**Mantenha esta janela aberta!** O serviço deve ficar rodando.

---

### **PASSO 2: Verificar que o Bridge está Acessível (WSL)**

No WSL, execute:

```bash
curl http://localhost:8000/health
```

**Resposta esperada:**
```json
{
  "status": "healthy",
  "mt5_connected": true,
  "terminal_build": 5488,
  "account_login": 5044246681,
  "server": "MetaQuotes-Demo"
}
```

Se você receber isso, o Bridge está OK! ✅

---

### **PASSO 3: Executar Testes End-to-End Completo (WSL)**

```bash
cd /home/workbench/projects/coding-day-trading
python3 scripts/test_end_to_end.py
```

**Output Esperado (8/8 testes passando):**
```
✓ PostgreSQL Connection: PASSOU
✓ Database Schema: PASSOU  
✓ MT5 Bridge API: PASSOU
✓ MT5 Account Info: PASSOU
✓ MT5 Tick Data: PASSOU
✓ MT5 Candle Data: PASSOU
✓ Data Insertion: PASSOU
✓ Database Statistics: PASSOU

Total: 8/8 testes passaram

✓ TODOS OS TESTES PASSARAM!
Sistema está funcionando corretamente end-to-end!
```

---

### **PASSO 4: Iniciar o Data Collector (WSL)**

```bash
python3 src/collectors/mt5_data_collector.py
```

**Menu de Opções:**
```
1. Carga inicial de dados históricos (executar uma vez)
2. Iniciar coleta contínua de ticks (HTTP polling)
3. Iniciar coleta contínua via WebSocket (recomendado)
4. Iniciar coleta de candles
5. Todos (histórico + tempo real)
6. Mostrar estatísticas
```

**Recomendação:**
- **Primeira execução:** Escolha `1` (carga histórica)
- **Produção:** Escolha `3` (WebSocket) ou `5` (completo)

---

### **PASSO 5: Monitorar os Dados (WSL)**

```bash
# Via psql
PGPASSWORD=password psql -h localhost -p 55432 -U postgres -d market_data

-- Ver últimos ticks
SELECT * FROM v_latest_ticks LIMIT 10;

-- Ver últimas candles
SELECT * FROM v_latest_candles WHERE symbol = 'EURUSD' LIMIT 10;

-- Estatísticas
SELECT 
    s.symbol,
    COUNT(t.id) as ticks,
    MAX(t.time) as last_update
FROM symbols s
LEFT JOIN ticks t ON s.id = t.symbol_id
GROUP BY s.symbol;
```

**OU via PgAdmin:**

Acesse: `http://localhost:5050`
- Email: `admin@admin.com`
- Senha: `admin`

---

## 📊 Exemplo de Uso Completo

### Terminal 1 (Windows PowerShell):
```powershell
# Inicia o Bridge
cd C:\Users\jonathan-moletta
python mt5_bridge_service.py
```

### Terminal 2 (WSL - Testes):
```bash
# Valida sistema
cd /home/workbench/projects/coding-day-trading
python3 scripts/test_end_to_end.py
```

### Terminal 3 (WSL - Collector):
```bash
# Inicia coleta
python3 src/collectors/mt5_data_collector.py
# Escolha opção 5 (Todos)
```

### Terminal 4 (WSL - Monitoramento):
```bash
# Loop de monitoramento
watch -n 5 'PGPASSWORD=password psql -h localhost -p 55432 -U postgres -d market_data -c "SELECT symbol, COUNT(*) as ticks FROM v_latest_ticks GROUP BY symbol;"'
```

---

## 🔧 Troubleshooting Rápido

### Problema: "Connection refused" ao acessar Bridge

**Causa:** MT5 Bridge não está rodando no Windows

**Solução:**
1. Abra PowerShell no Windows
2. Execute: `cd C:\Users\jonathan-moletta; python mt5_bridge_service.py`
3. Aguarde mensagem "[✓] MT5 inicializado e conectado"

---

### Problema: "MT5 não está conectado"

**Causa:** MT5 terminal não está logado ou conexão caiu

**Solução:**
1. Abra o MetaTrader 5 manualmente no Windows
2. Faça login na conta
3. Reinicie o Bridge Service

---

### Problema: "No module named 'MetaTrader5'"

**Contexto:** Erro no Windows ao rodar o Bridge

**Solução:**
```powershell
# No Windows
pip install MetaTrader5 fastapi uvicorn python-dotenv
```

---

### Problema: PostgreSQL não conecta

**Solução:**
```bash
# WSL
docker compose ps  # Verifica se está rodando
docker compose up -d  # Inicia se necessário
docker compose logs timescaledb  # Verifica logs
```

---

## 🎯 Checklist de Verificação

Antes de executar o sistema completo, verifique:

### Windows:
- [ ] MetaTrader 5 está instalado
- [ ] Python 3.8+ está instalado
- [ ] Dependências instaladas (`pip install MetaTrader5 fastapi uvicorn python-dotenv`)
- [ ] Arquivo `.env` está em `C:\Users\jonathan-moletta\.env`
- [ ] Arquivo `mt5_bridge_service.py` está em `C:\Users\jonathan-moletta\`

### WSL:
- [ ] Docker está rodando (`docker compose ps`)
- [ ] PostgreSQL está acessível (porta 55432)
- [ ] Schema foi aplicado (`psql -U postgres -d market_data -c "\dt"`)
- [ ] Dependências Python instaladas (`pip install -r requirements.txt`)

### Conexão:
- [ ] MT5 Bridge responde em `http://localhost:8000/health`
- [ ] PostgreSQL conecta via `psql`

---

## 📈 Próxima Execução

Após validar que tudo funciona:

1. **Coletar Dados Históricos** (executar uma vez):
   ```bash
   python3 src/collectors/mt5_data_collector.py
   # Escolha opção 1
   ```

2. **Manter Coleta em Tempo Real** (deixar rodando):
   ```bash
   python3 src/collectors/mt5_data_collector.py
   # Escolha opção 3 (WebSocket)
   ```

3. **Desenvolver Estratégias**:
   - Implementar indicadores técnicos
   - Criar lógica de trading
   - Backtesting com dados coletados

---

## 🎊 Sistema Funcionando?

Se todos os 8 testes passaram, você tem:

✅ Conexão MT5 ativa  
✅ Dados em tempo real fluindo  
✅ Armazenamento em PostgreSQL  
✅ API REST/WebSocket funcionando  
✅ Sistema completo end-to-end operacional  

**Parabéns! 🚀 O sistema está pronto para desenvolvimento de estratégias de trading!**

---

## 📞 Suporte

Se encontrar problemas:

1. Verifique os logs do Bridge Service (janela do PowerShell)
2. Verifique os logs do PostgreSQL (`docker compose logs timescaledb`)
3. Execute os testes: `python3 scripts/test_end_to_end.py`
4. Consulte o README.md completo
5. Verifique docs/MT5_TEST_INSTRUCTIONS.md

---

**Última atualização:** 2026-01-02  
**Sistema:** MT5 Trading Automation v1.0
