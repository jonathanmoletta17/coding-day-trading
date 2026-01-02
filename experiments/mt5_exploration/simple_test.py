"""
@category: experiment
@impact: low
@description: Teste didático inicial
"""

#!/usr/bin/env python3
"""
Script simplificado para testar conexão MT5 - SEM EMOJIS (compatível com Windows CMD)
"""

import MetaTrader5 as mt5
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timedelta
import traceback

# Carrega .env
load_dotenv()

def test_connection():
    """Testa a conexão com MT5 usando credenciais do .env"""
    
    print("=" * 70)
    print("TESTE DE CONEXAO MT5")
    print("=" * 70)
    
    # Carrega credenciais
    mt5_login = os.getenv("MT5_LOGIN")
    mt5_password = os.getenv("MT5_PASSWORD")
    mt5_server = os.getenv("MT5_SERVER")
    mt5_path = os.getenv("MT5_PATH")
    
    print("\n[CONFIG] Configuracoes:")
    print(f"   Login: {mt5_login}")
    print(f"   Server: {mt5_server}")
    print(f"   Path: {mt5_path}")
    print(f"   Password: {'*' * len(mt5_password) if mt5_password else 'NAO DEFINIDA'}")
    
    # Prepara argumentos de inicialização
    init_args = {}
    
    if mt5_path and Path(mt5_path).exists():
        init_args['path'] = mt5_path
        print(f"\n[OK] Terminal encontrado em: {mt5_path}")
    else:
        print(f"\n[WARN] Path do terminal nao encontrado ou invalido")
        print("   Tentando auto-detectar...")
    
    # Tenta inicializar
    print("\n[INFO] Inicializando MT5...")
    
    if not mt5.initialize(**init_args):
        error_code, error_desc = mt5.last_error()
        print(f"\n[ERRO] FALHA na inicializacao")
        print(f"   Codigo: {error_code}")
        print(f"   Descricao: {error_desc}")
        print("\n[HELP] Certifique-se de que:")
        print("   1. O MetaTrader 5 esta instalado")
        print("   2. O terminal pode ser executado (nao esta bloqueado)")
        print("   3. As credenciais estao corretas no arquivo .env")
        return False
    
    print("[OK] MT5 inicializado com sucesso!")
    
    # Tenta fazer login se temos credenciais
    if mt5_login and mt5_password and mt5_server:
        print(f"\n[INFO] Tentando login na conta {mt5_login}...")
        
        try:
            login_int = int(mt5_login)
            if mt5.login(login_int, password=mt5_password, server=mt5_server):
                print("[OK] Login realizado com sucesso!")
            else:
                error_code, error_desc = mt5.last_error()
                print(f"[ERRO] FALHA no login")
                print(f"   Codigo: {error_code}")
                print(f"   Descricao: {error_desc}")
                mt5.shutdown()
                return False
        except ValueError:
            print(f"[ERRO] Login invalido (deve ser numerico): {mt5_login}")
            mt5.shutdown()
            return False
    
    # Informações do terminal
    print("\n" + "=" * 70)
    print("INFORMACOES DO TERMINAL")
    print("=" * 70)
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"   Nome: {terminal_info.name}")
        print(f"   Empresa: {terminal_info.company}")
        print(f"   Path: {terminal_info.path}")
        print(f"   Versao (build): {terminal_info.build}")
        print(f"   Conectado ao servidor: {'SIM' if terminal_info.connected else 'NAO'}")
        print(f"   Trade permitido: {'SIM' if terminal_info.trade_allowed else 'NAO'}")
    else:
        print("   [ERRO] Nao foi possivel obter informacoes do terminal")
    
    # Informações da conta
    print("\n" + "=" * 70)
    print("INFORMACOES DA CONTA")
    print("=" * 70)
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
        print(f"   Margem Usada: {account_info.margin:.2f}")
        print(f"   Lucro: {account_info.profit:.2f}")
    else:
        print("   [ERRO] Nao foi possivel obter informacoes da conta")
    
    # Testa obtenção de símbolos
    print("\n" + "=" * 70)
    print("SIMBOLOS DISPONIVEIS")
    print("=" * 70)
    symbols_total = mt5.symbols_total()
    print(f"   Total de simbolos disponiveis: {symbols_total}")
    
    if symbols_total > 0:
        # Tenta pegar alguns símbolos comuns
        test_symbols = ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "XAUUSD", "WIN$", "WDO$"]
        print(f"\n   Testando simbolos especificos:")
        
        found_symbols = []
        for symbol in test_symbols:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info:
                print(f"      [OK] {symbol}: Disponivel")
                print(f"           Spread: {symbol_info.spread}")
                print(f"           Digits: {symbol_info.digits}")
                print(f"           Tipo: {symbol_info.description}")
                found_symbols.append(symbol)
            else:
                print(f"      [--] {symbol}: Nao disponivel")
        
        # Testa obtenção de dados com o primeiro símbolo encontrado
        if found_symbols:
            test_symbol = found_symbols[0]
            print(f"\n" + "=" * 70)
            print(f"TESTE DE OBTENCAO DE DADOS - {test_symbol}")
            print("=" * 70)
            
            # Último tick
            tick = mt5.symbol_info_tick(test_symbol)
            if tick:
                print(f"\n[OK] Ultimo tick de {test_symbol}:")
                print(f"   Bid (Venda): {tick.bid}")
                print(f"   Ask (Compra): {tick.ask}")
                print(f"   Spread: {tick.ask - tick.bid:.5f}")
                print(f"   Volume: {tick.volume}")
                print(f"   Time: {datetime.fromtimestamp(tick.time)}")
            else:
                print(f"[ERRO] Nao foi possivel obter tick de {test_symbol}")
            
            # Tenta pegar algumas barras (candles)
            print(f"\n[INFO] Obtendo ultimas 10 barras (1 hora) de {test_symbol}...")
            rates = mt5.copy_rates_from_pos(test_symbol, mt5.TIMEFRAME_H1, 0, 10)
            
            if rates is not None and len(rates) > 0:
                print(f"[OK] {len(rates)} barras obtidas com sucesso!")
                print("\nExemplo (ultimas 3 barras):")
                print(f"{'Time':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12} {'Volume':<10}")
                print("-" * 80)
                for rate in rates[-3:]:
                    time_str = datetime.fromtimestamp(rate['time']).strftime('%Y-%m-%d %H:%M')
                    print(f"{time_str:<20} {rate['open']:<12.5f} {rate['high']:<12.5f} "
                          f"{rate['low']:<12.5f} {rate['close']:<12.5f} {rate['tick_volume']:<10}")
            else:
                print(f"[ERRO] Nao foi possivel obter barras de {test_symbol}")
    
    # Informações adicionais
    print("\n" + "=" * 70)
    print("ESTATISTICAS ADICIONAIS")
    print("=" * 70)
    
    # Número de ordens abertas
    orders = mt5.orders_total()
    print(f"   Ordens abertas: {orders}")
    
    # Número de posições abertas
    positions = mt5.positions_total()
    print(f"   Posicoes abertas: {positions}")
    
    # Histórico de deals (últimas 10 operações)
    from_date = datetime.now() - timedelta(days=30)
    deals = mt5.history_deals_get(from_date, datetime.now())
    if deals is not None:
        print(f"   Deals nos ultimos 30 dias: {len(deals)}")
    
    # Finaliza
    print("\n" + "=" * 70)
    print("TESTE CONCLUIDO COM SUCESSO!")
    print("=" * 70)
    print("\nPROXIMOS PASSOS:")
    print("   1. Configurar bridge/gateway para acesso via WSL")
    print("   2. Implementar coleta de dados em tempo real")
    print("   3. Desenvolver estrategias de trading")
    print("   4. Integrar com banco de dados PostgreSQL")
    
    mt5.shutdown()
    return True

if __name__ == "__main__":
    try:
        success = test_connection()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n[ERRO CRITICO] Excecao inesperada: {e}")
        traceback.print_exc()
        exit(1)
