@echo off
TITLE CODING DAY TRADING - MT5 BRIDGE
COLOR 0A

:: Entra na pasta do script (suporta caminho de rede \\wsl.localhost via disco temporário)
:: Entra na pasta do script e volta para o root (..\..)
pushd "%~dp0..\.."

echo ===============================================================
echo  INICIANDO PONTE METATRADER 5 (WINDOWS HOST)
echo ===============================================================
echo.
echo [*] Diretório de trabalho: %CD%

:: Tenta Liberar Firewall (Requer Admin - Falha silenciosa se não for)
echo [*] Configurando Firewall (Porta 8000)...
netsh advfirewall firewall add rule name="Allow MT5 Bridge Python" dir=in action=allow protocol=TCP localport=8000 profile=private,public >nul 2>&1
if %errorlevel% equ 0 (
    echo     [OK] Regra de Firewall adicionada/atualizada.
) else (
    echo     [!] Aviso: Nao foi possivel configurar Firewall (Execute como Admin se falhar conexao).
)

:: Verifica Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] ERRO: Python nao encontrado no PATH!
    pause
    exit /b
)

echo [*] Iniciando servico...
echo.

:: Executa
python infrastructure/mt5_bridge_service.py

if %errorlevel% neq 0 (
    echo.
    echo [X] FALHA CRITICA: O servico nao rodou.
    echo     Verifique se existe: infrastructure/mt5_bridge_service.py
    dir infrastructure\mt5_bridge_service.py
    pause
) else (
    popd
)
