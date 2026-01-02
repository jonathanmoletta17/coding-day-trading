@echo off
cls
echo ============================================
echo MT5 Bridge - Diagnostico e Reinicio
echo ============================================
echo.

echo [1/4] Parando processos Python existentes na porta 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo    Matando PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [2/4] Verificando se porta esta liberada...
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo    [ERRO] Porta 8000 ainda em uso
    echo    Execute este script novamente
    pause
    exit /b 1
) else (
    echo    [OK] Porta 8000 livre
)

echo [3/4] Verificando dependencias Python...
python -c "import fastapi, uvicorn, MetaTrader5, dotenv" 2>nul
if errorlevel 1 (
    echo    [AVISO] Instalando dependencias faltantes...
    pip install -q fastapi uvicorn MetaTrader5 python-dotenv
)
echo    [OK] Dependencias OK

echo [4/4] Iniciando MT5 Bridge Service...
echo.
echo ============================================
echo AGUARDE: MT5 Bridge inicializando...
echo Voce devera ver: [OK] MT5 inicializado
echo ============================================
echo.

cd /d C:\Users\jonathan-moletta
python mt5_bridge_service.py

echo.
echo ============================================
echo Servidor encerrado
echo ============================================
pause
