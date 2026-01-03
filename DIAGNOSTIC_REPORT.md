# 🩺 Relatório de Diagnóstico de Conectividade

**Data:** 2026-01-02
**Status:** 🔴 FALHA DE CONEXÃO (Real Data)

## 1. O Problema
O usuário relatou que o sistema parou de funcionar com dados reais após um reinício do computador. A tentativa de conexão do Dashboard (Linux) para o Windows falha.

## 2. Diagnóstico Técnico
Executamos testes de conectividade profundos a partir do ambiente Linux:

1.  **Configuração de IP:** 
    - IP do Gateway Detectado: `172.17.96.1` (Correto, corresponde ao Host Windows).
    - Configuração `.env`: `MT5_BRIDGE_URL=http://172.17.96.1:8000` (Correto).
    
2.  **Teste de Porta (Curl):**
    - Comando: `curl ... http://172.17.96.1:8000/health`
    - Resultado: `Connection timed out` (Timeout após 2000ms).

## 3. Causa Raiz
**O Serviço de Ponte (Bridge) no Windows não está rodando.**
Como o computador foi reiniciado, o processo Python que servia a API do MT5 foi encerrado e não reiniciou automaticamente. O ambiente Linux está perfeito, mas "não tem com quem falar" do outro lado.

## 4. Solução Definitiva (Script de Inicialização)
Para evitar ter que abrir terminais e digitar comandos manualmente no Windows toda vez, criei este script `.bat`.

### Instruções:
1. Crie um arquivo chamado `START_TRADING_BRIDGE.bat` na sua Área de Trabalho no Windows.
2. Cole o conteúdo abaixo nele (ajuste o caminho se necessário).
3. **Sempre que reiniciar o PC**, dê dois cliques nesse arquivo.

```batch
@echo off
TITLE MT5 Bridge Service - CODING DAY TRADING
COLOR 0A

ECHO ========================================================
ECHO    INICIANDO SERVICO DE PONTE META TRADER 5
ECHO ========================================================
ECHO.

:: 1. Ative seu ambiente Python no Windows (Ajuste o caminho se usar Anaconda/Venv)
:: Exemplo: call C:\Users\SEU_USUARIO\anaconda3\Scripts\activate.bat base
:: Ou se o python estiver no PATH, apenas siga:

cd /d "C:\Caminho\Para\Seu\Projeto\coding-day-trading"

ECHO [*] Iniciando Bridge em infrastructure/mt5_bridge_service.py...
ECHO [*] Mantenha esta janela aberta enquanto opera!
ECHO.

python infrastructure/mt5_bridge_service.py

PAUSE
```

## 5. Próximos Passos
1. Execute esse script no Windows.
2. Assim que aparecer "Uvicorn running on...", volte para o Linux.
3. Execute `python3 tools/runners/start_dashboard.py`.
4. O sistema irá se conectar automaticamente e exibir dados reais.
