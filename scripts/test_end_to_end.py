#!/usr/bin/env python3
"""
Script de Teste End-to-End do Sistema MT5
Testa toda a pipeline: MT5 -> Bridge API -> Collector -> PostgreSQL
"""

import asyncio
import httpx
import sys
from sqlalchemy import create_engine, text
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Cores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{text}{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓{Colors.END} {text}")

def print_error(text):
    print(f"{Colors.RED}✗{Colors.END} {text}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ{Colors.END} {text}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠{Colors.END} {text}")

# =============================================================================
# TESTES
# =============================================================================

async def test_postgresql_connection():
    """Testa conexão com PostgreSQL"""
    print_header("TESTE 1: Conexão PostgreSQL")
    
    try:
        db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            
        print_success(f"Conectado ao PostgreSQL")
        print_info(f"  Versão: {version[:50]}...")
        return True
        
    except Exception as e:
        print_error(f"Falha na conexão: {e}")
        return False

async def test_database_schema():
    """Testa se o schema foi criado corretamente"""
    print_header("TESTE 2: Schema do Banco de Dados")
    
    try:
        db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        engine = create_engine(db_url)
        
        expected_tables = ['symbols', 'ticks', 'candles', 'orders', 'positions', 'deals', 'indicators', 'trade_signals', 'backtests']
        
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename
            """))
            
            existing_tables = [row[0] for row in result]
        
        missing = set(expected_tables) - set(existing_tables)
        extra = [t for t in existing_tables if t not in expected_tables and not t.startswith('pg_')]
        
        if not missing:
            print_success("Todas as tabelas esperadas existem")
            for table in expected_tables:
                print_info(f"  ✓ {table}")
        else:
            print_error(f"Tabelas faltando: {', '.join(missing)}")
            return False
        
        if extra:
            print_warning(f"Tabelas extras encontradas: {', '.join(extra)}")
        
        return True
        
    except Exception as e:
        print_error(f"Erro ao verificar schema: {e}")
        return False

async def test_mt5_bridge_api():
    """Testa conexão com MT5 Bridge API"""
    print_header("TESTE 3: MT5 Bridge API")
    
    bridge_url = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test health endpoint
            response = await client.get(f"{bridge_url}/health")
            
            if response.status_code == 200:
                data = response.json()
                print_success("MT5 Bridge API está online")
                print_info(f"  Status: {data['status']}")
                print_info(f"  MT5 Conectado: {data['mt5_connected']}")
                print_info(f"  Terminal Build: {data['terminal_build']}")
                print_info(f"  Conta: {data['account_login']}")
                print_info(f"  Servidor: {data['server']}")
                return True
            else:
                print_error(f"Status HTTP: {response.status_code}")
                return False
                
    except httpx.ConnectError:
        print_error("Não foi possível conectar ao MT5 Bridge API")
        print_warning(f"  Certifique-se de que mt5_bridge_service.py está rodando")
        print_warning(f"  URL esperada: {bridge_url}")
        return False
    except Exception as e:
        print_error(f"Erro ao testar API: {e}")
        return False

async def test_mt5_account_info():
    """Testa obtenção de informações da conta via API"""
    print_header("TESTE 4: Informações da Conta MT5")
    
    bridge_url = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{bridge_url}/account")
            
            if response.status_code == 200:
                account = response.json()
                print_success("Informações da conta obtidas")
                print_info(f"  Login: {account['login']}")
                print_info(f"  Nome: {account['name']}")
                print_info(f"  Servidor: {account['server']}")
                print_info(f"  Moeda: {account['currency']}")
                print_info(f"  Saldo: ${account['balance']:,.2f}")
                print_info(f"  Equity: ${account['equity']:,.2f}")
                print_info(f"  Alavancagem: 1:{account['leverage']}")
                return True
            else:
                print_error(f"Falha ao obter conta: {response.status_code}")
                return False
                
    except Exception as e:
        print_error(f"Erro: {e}")
        return False

async def test_mt5_tick_data():
    """Testa obtenção de ticks via API"""
    print_header("TESTE 5: Obtenção de Ticks")
    
    bridge_url = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
    test_symbol = "EURUSD"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{bridge_url}/tick/{test_symbol}")
            
            if response.status_code == 200:
                tick = response.json()
                print_success(f"Tick de {test_symbol} obtido")
                print_info(f"  Time: {tick['time']}")
                print_info(f"  Bid: {tick['bid']}")
                print_info(f"  Ask: {tick['ask']}")
                print_info(f"  Spread: {tick['ask'] - tick['bid']:.5f}")
                return True
            else:
                print_error(f"Falha ao obter tick: {response.status_code}")
                return False
                
    except Exception as e:
        print_error(f"Erro: {e}")
        return False

async def test_mt5_candle_data():
    """Testa obtenção de candles via API"""
    print_header("TESTE 6: Obtenção de Candles")
    
    bridge_url = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
    test_symbol = "EURUSD"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{bridge_url}/candles/{test_symbol}",
                params={"timeframe": "H1", "count": 5}
            )
            
            if response.status_code == 200:
                candles = response.json()
                print_success(f"{len(candles)} candles de {test_symbol} H1 obtidos")
                
                if candles:
                    latest = candles[-1]
                    print_info(f"  Última candle:")
                    print_info(f"    Time: {latest['time']}")
                    print_info(f"    Open: {latest['open']}")
                    print_info(f"    High: {latest['high']}")
                    print_info(f"    Low: {latest['low']}")
                    print_info(f"    Close: {latest['close']}")
                    print_info(f"    Volume: {latest['tick_volume']}")
                
                return True
            else:
                print_error(f"Falha ao obter candles: {response.status_code}")
                return False
                
    except Exception as e:
        print_error(f"Erro: {e}")
        return False

async def test_data_insertion():
    """Testa inserção de dados no PostgreSQL"""
    print_header("TESTE 7: Inserção de Dados no PostgreSQL")
    
    try:
        db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        engine = create_engine(db_url)
        bridge_url = os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
        test_symbol = "EURUSD"
        
        # Obter tick via API
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{bridge_url}/tick/{test_symbol}")
            tick = response.json()
        
        # Inserir no banco
        with engine.connect() as conn:
            # Criar/obter símbolo
            result = conn.execute(
                text("SELECT get_or_create_symbol(:symbol)"),
                {"symbol": test_symbol}
            )
            symbol_id = result.scalar()
            
            # Inserir tick
            conn.execute(
                text("""
                    INSERT INTO ticks (symbol_id, time, bid, ask, last, volume, flags)
                    VALUES (:symbol_id, :time, :bid, :ask, :last, :volume, :flags)
                """),
                {
                    "symbol_id": symbol_id,
                    "time": tick['time'],
                    "bid": tick['bid'],
                    "ask": tick['ask'],
                    "last": tick.get('last', 0),
                    "volume": tick.get('volume', 0),
                    "flags": tick.get('flags', 0)
                }
            )
            
            conn.commit()
            
            # Verificar inserção
            result = conn.execute(
                text("SELECT COUNT(*) FROM ticks WHERE symbol_id = :symbol_id"),
                {"symbol_id": symbol_id}
            )
            count = result.scalar()
        
        print_success(f"Tick inserido com sucesso")
        print_info(f"  Total de ticks de {test_symbol}: {count}")
        return True
        
    except Exception as e:
        print_error(f"Erro ao inserir dados: {e}")
        return False

async def test_database_statistics():
    """Mostra estatísticas do banco de dados"""
    print_header("TESTE 8: Estatísticas do Banco")
    
    try:
        db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # Total de símbolos
            result = conn.execute(text("SELECT COUNT(*) FROM symbols"))
            total_symbols = result.scalar()
            
            # Total de ticks
            result = conn.execute(text("SELECT COUNT(*) FROM ticks"))
            total_ticks = result.scalar()
            
            # Total de candles
            result = conn.execute(text("SELECT COUNT(*) FROM candles"))
            total_candles = result.scalar()
            
            # Símbolos com dados
            result = conn.execute(text("""
                SELECT s.symbol, COUNT(t.id) as tick_count
                FROM symbols s
                LEFT JOIN ticks t ON s.id = t.symbol_id
                GROUP BY s.symbol
                HAVING COUNT(t.id) > 0
                ORDER BY tick_count DESC
            """))
            symbols_with_data = list(result)
        
        print_success("Estatísticas obtidas")
        print_info(f"  Total de símbolos cadastrados: {total_symbols}")
        print_info(f"  Total de ticks armazenados: {total_ticks:,}")
        print_info(f"  Total de candles armazenadas: {total_candles:,}")
        
        if symbols_with_data:
            print_info(f"\n  Símbolos com dados:")
            for symbol, count in symbols_with_data[:10]:
                print_info(f"    {symbol}: {count:,} ticks")
        
        return True
        
    except Exception as e:
        print_error(f"Erro ao obter estatísticas: {e}")
        return False

# =============================================================================
# MAIN
# =============================================================================

async def run_all_tests():
    """Executa todos os testes"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}")
    print("TESTE END-TO-END DO SISTEMA MT5")
    print(f"{'=' * 70}{Colors.END}\n")
    
    print_info(f"Timestamp: {datetime.now().isoformat()}")
    print_info(f"MT5 Bridge URL: {os.getenv('MT5_BRIDGE_URL', 'http://localhost:8000')}")
    print_info(f"PostgreSQL: {os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}")
    
    tests = [
        ("PostgreSQL Connection", test_postgresql_connection),
        ("Database Schema", test_database_schema),
        ("MT5 Bridge API", test_mt5_bridge_api),
        ("MT5 Account Info", test_mt5_account_info),
        ("MT5 Tick Data", test_mt5_tick_data),
        ("MT5 Candle Data", test_mt5_candle_data),
        ("Data Insertion", test_data_insertion),
        ("Database Statistics", test_database_statistics),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Exceção em {name}: {e}")
            results.append((name, False))
    
    # Resumo
    print_header("RESUMO DOS TESTES")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = Colors.GREEN + "PASSOU" + Colors.END if result else Colors.RED + "FALHOU" + Colors.END
        print(f"  {name}: {status}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} testes passaram{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ TODOS OS TESTES PASSARAM!{Colors.END}")
        print(f"{Colors.GREEN}Sistema está funcionando corretamente end-to-end!{Colors.END}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ ALGUNS TESTES FALHARAM{Colors.END}")
        print(f"{Colors.YELLOW}Verifique os erros acima e corrija antes de continuar.{Colors.END}\n")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
