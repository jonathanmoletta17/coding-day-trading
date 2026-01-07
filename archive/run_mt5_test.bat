@echo off
REM Script para testar conexão MT5 no Windows
REM Execute este arquivo dando duplo clique ou via CMD/PowerShell

echo ==========================================
echo MT5 Connection Test
echo ==========================================
echo.

REM Verifica se Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado!
    echo.
    echo Por favor, instale o Python de: https://www.python.org/downloads/
    echo Certifique-se de marcar "Add Python to PATH" durante a instalacao
    pause
    exit /b 1
)

echo [OK] Python encontrado!
echo.

REM Verifica/Instala dependências
echo Verificando dependencias...
pip show MetaTrader5 >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Instalando MetaTrader5...
    pip install MetaTrader5 python-dotenv
) else (
    echo [OK] MetaTrader5 ja instalado
)

pip show python-dotenv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Instalando python-dotenv...
    pip install python-dotenv
) else (
    echo [OK] python-dotenv ja instalado
)

echo.
echo ==========================================
echo Executando teste de conexao...
echo ==========================================
echo.

REM Executa o script de teste
python test_mt5.py

echo.
echo ==========================================
echo Pressione qualquer tecla para fechar...
pause >nul
