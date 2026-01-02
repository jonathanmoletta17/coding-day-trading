# 🔌 Teste de Conexão MT5 - Instruções

## ⚠️ Contexto Importante

O pacote `MetaTrader5` para Python **só funciona no Windows**. Como você está usando **WSL2** (Linux), existem duas formas de testar:

### ✅ **Opção 1: Executar no Windows (RECOMENDADO - MAIS SIMPLES)**

Já preparei tudo para você! Os arquivos foram copiados para: `C:\Users\jonathan-moletta\`

#### Passo a Passo:

1. **Abra o Explorador de Arquivos do Windows** e vá para:
   ```
   C:\Users\jonathan-moletta
   ```

2. **Duplo clique no arquivo:** `run_mt5_test.bat`

   OU

3. **Abra o PowerShell/CMD** e execute:
   ```cmd
   cd C:\Users\jonathan-moletta
   run_mt5_test.bat
   ```

O script automaticamente:
- ✅ Verifica se Python está instalado
- ✅ Instala dependências necessárias (`MetaTrader5`, `python-dotenv`)
- ✅ Executa o teste de conexão
- ✅ Mostra relatório completo com:
  - Status da conexão
  - Informações da conta
  - Símbolos disponíveis
  - Teste de obtenção de dados em tempo real

---

### 🔧 **Opção 2: Manual (se preferir ter mais controle)**

#### 1. Instalar Dependências no Windows:
```cmd
pip install MetaTrader5 python-dotenv
```

#### 2. Executar o Script:
```cmd
cd C:\Users\jonathan-moletta
python test_mt5.py
```

---

## 📋 O que o teste vai verificar:

1. ✅ **Inicialização do MT5**
   - Verifica se o terminal está acessível
   - Usa o path configurado no `.env`

2. ✅ **Login na Conta**
   - Login: `5044246681`
   - Server: `MetaQuotes-Demo`
   - Password: (da variável `.env`)

3. ✅ **Informações do Terminal**
   - Nome e versão
   - Status de conexão com servidor
   - Permissões de trading

4. ✅ **Informações da Conta**
   - Saldo, equity, margem
   - Moeda e alavancagem
   - Servidor conectado

5. ✅ **Acesso a Símbolos**
   - Total de símbolos disponíveis
   - Testa símbolos comuns (EURUSD, WIN$, etc.)

6. ✅ **Obtenção de Dados**
   - Busca último tick (preço em tempo real)
   - Verifica se consegue receber dados do mercado

---

## 🚨 Possíveis Erros e Soluções

### ❌ "Python não encontrado"
**Solução:** Instale Python de https://www.python.org/downloads/
- ⚠️ Durante a instalação, marque **"Add Python to PATH"**

### ❌ "Falha na inicialização do MT5"
**Causas possíveis:**
1. MetaTrader 5 não está instalado
2. Path incorreto no `.env`
3. Terminal está bloqueado/corrompido

**Solução:**
- Verifique se existe: `C:\Program Files\MetaTrader 5\terminal64.exe`
- Tente executar o MT5 manualmente primeiro
- Atualize o `MT5_PATH` no `.env` se o caminho for diferente

### ❌ "Falha no login"
**Causas possíveis:**
1. Credenciais incorretas
2. Servidor inválido
3. Sem conexão com internet
4. Conta desativada/bloqueada

**Solução:**
- Verifique os dados no `.env`:
  - `MT5_LOGIN=5044246681`
  - `MT5_PASSWORD=!8JiJiOl`
  - `MT5_SERVER=MetaQuotes-Demo`
- Tente fazer login manualmente no MT5 primeiro

### ❌ "Terminal não conectado ao servidor"
**Solução:**
- Verifique sua conexão com a internet
- Abra o MT5 manualmente e faça login
- Certifique-se de que o servidor está online

---

## 🎯 Próximos Passos (Após Teste bem-sucedido)

### Para desenvolvimento no WSL/Linux:

Você terá 3 opções:

#### **Opção A: MT5 Gateway/Bridge (RECOMENDADO)**
Criar um servidor HTTP/WebSocket no Windows que:
- Roda em segundo plano no Windows
- Conecta-se ao MT5 (via MetaTrader5 Python)
- Expõe API REST/WebSocket em `http://localhost:8000`
- Seus scripts no WSL fazem requests HTTP

**Vantagens:**
- ✅ Desenvolve no Linux/WSL normalmente
- ✅ Acesso completo à API MT5
- ✅ Pode ser usado por múltiplos scripts/projetos

#### **Opção B: Scripts híbridos**
- Escreve lógica de trading no WSL
- Scripts de conexão MT5 rodam no Windows
- Comunicação via arquivos compartilhados ou sockets

#### **Opção C: Ambiente Windows completo**
- Desenvolve tudo no Windows
- Usa VSCode Remote para editar do WSL

---

## 📝 Arquivos Criados

### No WSL (projeto):
- `scripts/test_mt5_connection_windows.py` - Script principal de teste
- `scripts/test_mt5_wsl_helper.sh` - Helper para WSL
- `run_mt5_test.bat` - Batch script Windows

### No Windows (copiados automaticamente):
- `C:\Users\jonathan-moletta\test_mt5.py`
- `C:\Users\jonathan-moletta\.env`
- `C:\Users\jonathan-moletta\run_mt5_test.bat`

---

## 🆘 Precisa de Ajuda?

Se encontrar algum erro:

1. **Tire um print da tela de erro**
2. **Copie a mensagem completa**
3. **Verifique se:**
   - Python está instalado no Windows
   - MT5 está instalado e funcional
   - As credenciais no `.env` estão corretas
   - Há conexão com internet

---

## ✅ Checklist

Antes de executar:
- [ ] MT5 está instalado no Windows
- [ ] Python está instalado no Windows (com PATH configurado)
- [ ] Credenciais no `.env` estão corretas
- [ ] Há conexão com a internet

Execute:
- [ ] Duplo clique em `run_mt5_test.bat` ou execute via CMD

Após sucesso:
- [ ] Anote o saldo/equity mostrado
- [ ] Verifique quais símbolos estão disponíveis
- [ ] Decida qual opção de desenvolvimento seguir (Gateway/Híbrido/Windows)

---

## 🚀 Boa sorte com seus testes!

> **Dica:** Se tudo funcionar bem, considere implementar a **Opção A (Gateway)** para máxima flexibilidade no desenvolvimento.
