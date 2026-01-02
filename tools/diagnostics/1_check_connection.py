"""
@category: tool
@impact: low
@description: Diagnóstico: Checa conexão e login
"""

import MetaTrader5 as mt5
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env na raiz do projeto
# O script está em scripts/mt5_validation/, então o .env está em ../../.env
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(dotenv_path)

def check_connection():
    print("=== VERIFICAÇÃO DE CONEXÃO COM METATRADER 5 ===")
    
    # 1. Tenta inicializar
    print("\n1. Tentando inicializar conexão com o terminal MT5...")
    
    # Tenta obter configurações do .env
    mt5_path = os.getenv("MT5_PATH")
    mt5_login = os.getenv("MT5_LOGIN")
    mt5_password = os.getenv("MT5_PASSWORD")
    mt5_server = os.getenv("MT5_SERVER")
    
    # Fallback para o arquivo gerado pelo script 0 se não houver no .env
    if not mt5_path:
        path_file = "scripts/mt5_validation/mt5_path.txt"
        if os.path.exists(path_file):
            with open(path_file, "r") as f:
                mt5_path = f.read().strip()
    
    print(f"   ℹ️ Path configurado: {mt5_path}")
    
    initialized = False
    
    # Prepara argumentos para initialize
    init_kwargs = {}
    if mt5_path and os.path.exists(mt5_path):
        init_kwargs['path'] = mt5_path
        
    # Se tivermos credenciais, podemos tentar fazer login após inicializar, 
    # ou confiar que o initialize com path vai abrir o terminal correto que já tem login salvo.
    # Nota: mt5.initialize(**kwargs) aceita login, password, server também.
    if mt5_login and mt5_password and mt5_server:
        try:
            init_kwargs['login'] = int(mt5_login)
            init_kwargs['password'] = mt5_password
            init_kwargs['server'] = mt5_server
            print("   ℹ️ Usando credenciais do .env")
        except ValueError:
            print("   ⚠️ Credenciais inválidas no .env (Login deve ser numérico)")

    try:
        if mt5.initialize(**init_kwargs):
            initialized = True
        else:
            # Tenta sem argumentos se falhar (auto-detect)
             if not initialized and not init_kwargs:
                print("   Tentando detecção automática...")
                if mt5.initialize():
                    initialized = True
    except Exception as e:
        print(f"   Erro ao inicializar: {e}")

    if not initialized:
        print("❌ Falha ao inicializar o MT5")
        print(f"Código de erro: {mt5.last_error()}")
        print("\nSOLUÇÃO:")
        print("Execute o script '0_find_mt5.py' para localizar sua instalação automaticamente.")
        return False
    else:
        print("✅ MT5 inicializado com sucesso!")

    # 2. Verifica informações do terminal
    print("\n2. Obtendo informações do terminal...")
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        print("❌ Falha ao obter informações do terminal")
    else:
        print(f"✅ Terminal conectado: {terminal_info.name}")
        print(f"   Caminho: {terminal_info.path}")
        print(f"   Conectado ao servidor: {'SIM' if terminal_info.connected else 'NÃO'}")
        if not terminal_info.connected:
            print("⚠️  ATENÇÃO: O terminal não está conectado ao servidor da corretora.")
            print("   Verifique sua conexão com a internet e se fez login na conta.")

    # 3. Verifica informações da conta
    print("\n3. Obtendo informações da conta...")
    account_info = mt5.account_info()
    if account_info is None:
        print("❌ Falha ao obter informações da conta. Você está logado?")
    else:
        print(f"✅ Conta logada: {account_info.login}")
        print(f"   Servidor: {account_info.server}")
        print(f"   Moeda: {account_info.currency}")
        print(f"   Alavancagem: 1:{account_info.leverage}")
        print(f"   Saldo: {account_info.balance}")
        print(f"   Algo Trading Ativado: {'SIM' if terminal_info.trade_allowed else 'NÃO (Necessário para operar, não para ler dados)'}")

    # 4. Verifica número de símbolos disponíveis
    symbols_count = mt5.symbols_total()
    print(f"\n4. Símbolos disponíveis no terminal: {symbols_count}")
    
    if symbols_count > 0:
        print("✅ Símbolos encontrados. A conexão de dados parece funcional.")
    else:
        print("⚠️  Nenhum símbolo encontrado. Verifique se o Market Watch (Observação de Mercado) está ativo e com ativos listados.")

    mt5.shutdown()
    return True

if __name__ == "__main__":
    check_connection()
