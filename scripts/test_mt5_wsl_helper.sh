#!/bin/bash
# Script helper para testar MT5 a partir do WSL

echo "=========================================="
echo "MT5 Connection Test - WSL Helper"
echo "=========================================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}⚠️  IMPORTANTE:${NC}"
echo "O pacote MetaTrader5 Python só funciona no Windows."
echo "Para testar a conexão do WSL, você tem algumas opções:"
echo ""

echo -e "${GREEN}OPÇÃO 1 - Executar script Python no Windows (RECOMENDADO):${NC}"
echo "==========================================================="
echo ""
echo "1. Copie o script para o Windows:"
WINDOWS_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')
SCRIPT_PATH="/mnt/c/Users/${WINDOWS_USER}/test_mt5.py"
echo "   cp scripts/test_mt5_connection_windows.py \"${SCRIPT_PATH}\""
echo ""
echo "2. Copie o arquivo .env para o mesmo local:"
echo "   cp .env \"/mnt/c/Users/${WINDOWS_USER}/.env\""
echo ""
echo "3. Abra o PowerShell ou CMD no Windows e execute:"
echo "   cd C:\\Users\\${WINDOWS_USER}"
echo "   python test_mt5.py"
echo ""
echo "   OU se usar Python3:"
echo "   python3 test_mt5.py"
echo ""

echo -e "${GREEN}OPÇÃO 2 - Instalar Python MetaTrader5 no Windows:${NC}"
echo "==========================================================="
echo ""
echo "1. Abra PowerShell no Windows como Administrador"
echo "2. Instale o pacote MetaTrader5:"
echo "   pip install MetaTrader5 python-dotenv"
echo ""
echo "3. Execute o script de teste:"
echo "   cd C:\\Users\\${WINDOWS_USER}"
echo "   python test_mt5.py"
echo ""

echo -e "${GREEN}OPÇÃO 3 - Criar MT5 API Gateway (Para desenvolvimento):${NC}"
echo "==========================================================="
echo "Se você planeja desenvolver no WSL/Linux, considere criar um"
echo "gateway/bridge HTTP que roda no Windows e expõe a API MT5"
echo "via REST ou WebSocket para o WSL acessar."
echo ""
echo "Exemplo de stack:"
echo "  - FastAPI/Flask rodando no Windows"
echo "  - Conecta ao MT5 via pacote MetaTrader5"
echo "  - Expõe endpoints HTTP (http://localhost:8000)"
echo "  - Scripts Python no WSL fazem requests HTTP"
echo ""

echo -e "${YELLOW}Deseja que eu execute a OPÇÃO 1 automaticamente? (s/n)${NC}"
read -p "> " choice

if [[ "$choice" == "s" || "$choice" == "S" ]]; then
    echo ""
    echo "Copiando arquivos para Windows..."
    
    cp scripts/test_mt5_connection_windows.py "${SCRIPT_PATH}"
    cp .env "/mnt/c/Users/${WINDOWS_USER}/.env"
    
    echo -e "${GREEN}✅ Arquivos copiados!${NC}"
    echo ""
    echo "Agora execute no PowerShell/CMD do Windows:"
    echo "   cd C:\\Users\\${WINDOWS_USER}"
    echo "   python test_mt5.py"
    echo ""
    echo "Para abrir PowerShell rapidamente, use:"
    echo "   cmd.exe /c start powershell"
else
    echo "Ok, quando estiver pronto, siga as instruções acima."
fi

echo ""
echo "=========================================="
