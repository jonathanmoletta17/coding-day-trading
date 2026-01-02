# ⚡ Guia Rápido - Ativar MT5 Bridge

## 🎯 Problema Identificado
**Porta 8000 em uso** - Processo anterior não foi encerrado corretamente

## ✅ Solução - Execute no Windows:

### Passo 1: Abra o script atualizado
1. Pressione `Windows + R`
2. Digite: `C:\Users\jonathan-moletta\start_mt5_bridge.bat`
3. Pressione `Enter`

O script agora:
- ✅ Mata processos antigos automaticamente
- ✅ Libera a porta 8000
- ✅ Verifica dependências
- ✅ Inicia o Bridge

### Passo 2: Aguarde a mensagem
```
[✓] MT5 inicializado e conectado
INFO: Uvicorn running on http://0.0.0.0:8000
```

**Deixe a janela aberta!**

### Passo 3: Teste no WSL
```bash
# Teste rápido
curl http://localhost:8000/health

# Se funcionar, execute suite completa
python3 scripts/test_end_to_end.py
```

## 🔧 Alternativa Manual (Se o batch não funcionar):

### 1. Matar processo na porta 8000:
```powershell
# No PowerShell
netstat -ano | findstr :8000
# Anote o PID (última coluna)

taskkill /F /PID <PID_AQUI>
```

### 2. Iniciar Bridge:
```powershell
cd C:\Users\jonathan-moletta
python mt5_bridge_service.py
```

## 📊 Status Esperado Após Ativação:

```
Total: 8/8 testes passaram ✅

✓ PostgreSQL Connection
✓ Database Schema
✓ MT5 Bridge API  
✓ MT5 Account Info
✓ MT5 Tick Data
✓ MT5 Candle Data
✓ Data Insertion
✓ Database Statistics

✓ TODOS OS TESTES PASSARAM!
```

## 🚀 Próximo Passo:
Quando o Bridge estiver ativo (8/8 testes OK):
```bash
python3 src/collectors/mt5_data_collector.py
```

---

**Executar agora:** `C:\Users\jonathan-moletta\start_mt5_bridge.bat`
