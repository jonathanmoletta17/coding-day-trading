#!/usr/bin/env python3
"""
Script para testar conexão MT5 - DEVE SER EXECUTADO NO WINDOWS
Caminho WSL: /mnt/c/Users/[SEU_USUARIO]/test_mt5.py
Execute no Windows: python C:\\Users\\[SEU_USUARIO]\\test_mt5.py
"""

import MetaTrader5 as mt5
import os
from dotenv import load_dotenv
from pathlib import Path

# Tenta carregar .env do projeto (ajuste o caminho se necessário)
load_dotenv()

def test_connection():
    """Testa a conexão com MT5 usando credenciais do .env"""
    
    print("=" * 60)
    print("TESTE DE CONEXÃO MT5")
    print("=" * 60)
    
    # Carrega credenciais
    mt5_login = os.getenv("MT5_LOGIN")
    mt5_password = os.getenv("MT5_PASSWORD")
    mt5_server = os.getenv("MT5_SERVER")
    mt5_path = os.getenv("MT5_PATH")
    
    print(f"\n📋 Configurações:")
    print(f"   Login: {mt5_login}")
    print(f"   Server: {mt5_server}")
    print(f"   Path: {mt5_path}")
    print(f"   Password: {'*' * len(mt5_password) if mt5_password else 'NÃO DEFINIDA'}")
    
    # Prepara argumentos de inicialização
    init_args = {}
    
    if mt5_path and Path(mt5_path).exists():
        init_args['path'] = mt5_path
        print(f"\n✅ Terminal encontrado em: {mt5_path}")
    else:
        print(f"\n⚠️  Path do terminal não encontrado ou inválido")
        print("   Tentando auto-detectar...")
    
    # Tenta inicializar
    print("\n🔄 Inicializando MT5...")
    
    if not mt5.initialize(**init_args):
        error_code, error_desc = mt5.last_error()
        print(f"\n❌ FALHA na inicialização")
        print(f"   Código: {error_code}")
        print(f"   Descrição: {error_desc}")
        print("\n💡 Certifique-se de que:")
        print("   1. O MetaTrader 5 está instalado")
        print("   2. O terminal pode ser executado (não está bloqueado)")
        print("   3. As credenciais estão corretas no arquivo .env")
        return False
    
    print("✅ MT5 inicializado com sucesso!")
    
    # Tenta fazer login se temos credenciais
    if mt5_login and mt5_password and mt5_server:
        print(f"\n🔐 Tentando login na conta {mt5_login}...")
        
        try:
            login_int = int(mt5_login)
            if mt5.login(login_int, password=mt5_password, server=mt5_server):
                print("✅ Login realizado com sucesso!")
            else:
                error_code, error_desc = mt5.last_error()
                print(f"❌ FALHA no login")
                print(f"   Código: {error_code}")
                print(f"   Descrição: {error_desc}")
                mt5.shutdown()
                return False
        except ValueError:
            print(f"❌ Login inválido (deve ser numérico): {mt5_login}")
            mt5.shutdown()
            return False
    
    # Informações do terminal
    print("\n📊 Informações do Terminal:")
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"   Nome: {terminal_info.name}")
        print(f"   Empresa: {terminal_info.company}")
        print(f"   Path: {terminal_info.path}")
        print(f"   Versão: {terminal_info.build}")
        print(f"   Conectado: {'SIM ✅' if terminal_info.connected else 'NÃO ❌'}")
        print(f"   Trade Allowed: {'SIM ✅' if terminal_info.trade_allowed else 'NÃO ⚠️'}")
    else:
        print("   ❌ Não foi possível obter informações do terminal")
    
    # Informações da conta
    print("\n💼 Informações da Conta:")
    account_info = mt5.account_info()
    if account_info:
        print(f"   Login: {account_info.login}")
        print(f"   Servidor: {account_info.server}")
        print(f"   Nome: {account_info.name}")
        print(f"   Moeda: {account_info.currency}")
        print(f"   Alavancagem: 1:{account_info.leverage}")
        print(f"   Saldo: {account_info.balance:.2f}")
        print(f"   Equity: {account_info.equity:.2f}")
        print(f"   Margem Livre: {account_info.margin_free:.2f}")
    else:
        print("   ❌ Não foi possível obter informações da conta")
    
    # Testa obtenção de símbolos
    print("\n📈 Testando acesso a símbolos:")
    symbols_total = mt5.symbols_total()
    print(f"   Total de símbolos disponíveis: {symbols_total}")
    
    if symbols_total > 0:
        # Tenta pegar alguns símbolos comuns
        test_symbols = ["EURUSD", "GBPUSD", "USDJPY", "WIN$", "WDO$"]
        print(f"\n   Testando símbolos específicos:")
        
        for symbol in test_symbols:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info:
                print(f"      ✅ {symbol}: Disponível (Spread: {symbol_info.spread})")
            else:
                print(f"      ❌ {symbol}: Não disponível")
    
    # Testa obtenção de dados (tick)
    print("\n🎯 Testando obtenção de dados:")
    # Tenta pegar o último tick de EURUSD (símbolo universal)
    tick = mt5.symbol_info_tick("EURUSD")
    if tick:
        print(f"   ✅ Último tick EURUSD:")
        print(f"      Bid: {tick.bid}")
        print(f"      Ask: {tick.ask}")
        print(f"      Time: {tick.time}")
    else:
        print(f"   ⚠️  Não foi possível obter tick do EURUSD")
        print(f"   Tentando com WIN$ (B3)...")
        tick = mt5.symbol_info_tick("WIN$")
        if tick:
            print(f"   ✅ Último tick WIN$:")
            print(f"      Bid: {tick.bid}")
            print(f"      Ask: {tick.ask}")
            print(f"      Time: {tick.time}")
    
    # Finaliza
    print("\n" + "=" * 60)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("=" * 60)
    print("\n💡 Próximos passos:")
    print("   1. Configurar bridge/gateway para acesso via WSL")
    print("   2. Implementar coleta de dados em tempo real")
    print("   3. Testar estratégias de trading")
    
    mt5.shutdown()
    return True

if __name__ == "__main__":
    try:
        success = test_connection()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
