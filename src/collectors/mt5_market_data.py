import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import os
import winreg
import logging
from typing import Optional, Tuple, Dict, List
from datetime import datetime
from src.database.db_handler import DatabaseHandler
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MT5MarketCollector:
    """
    Coletor de dados de alta frequência via MetaTrader 5.
    Gerencia conexão, assinatura de livro de ofertas e normalização de dados.
    """
    
    def __init__(self):
        self.connected = False
        self.subscribed_symbols = set()
        self.db = DatabaseHandler()
        self._initialize_connection()

    def _find_mt5_path(self) -> Optional[str]:
        """
        Busca automática do executável terminal64.exe no sistema.
        """
        # Prioridade 0: Verifica variável de ambiente
        env_path = os.getenv("MT5_PATH")
        if env_path and os.path.exists(env_path):
            logging.info(f"🔍 Usando MT5_PATH do ambiente: {env_path}")
            return env_path

        logging.info("🔍 Buscando MT5 no sistema...")
        
        # 1. Tenta Registro do Windows
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        for reg_view in [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ | reg_view) as key:
                    for i in range(0, winreg.QueryInfoKey(key)[0]):
                        try:
                            sub_key_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sub_key_name) as sub_key:
                                try:
                                    display_name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                                    if "MetaTrader 5" in display_name:
                                        install_location = winreg.QueryValueEx(sub_key, "InstallLocation")[0]
                                        exe_path = os.path.join(install_location, "terminal64.exe")
                                        if os.path.exists(exe_path):
                                            return exe_path
                                except FileNotFoundError:
                                    pass
                        except OSError:
                            continue
            except OSError:
                continue

        # 2. Busca em caminhos comuns (Fallback)
        common_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
            r"C:\Program Files\XP MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Genial MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Rico MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Clear MetaTrader 5\terminal64.exe",
            r"C:\Program Files\BTG Pactual MetaTrader 5\terminal64.exe",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
                
        return None

    def _initialize_connection(self) -> bool:
        """
        Inicializa a conexão com o terminal MT5.
        """
        # Tenta pegar credenciais do .env
        mt5_login = os.getenv("MT5_LOGIN")
        mt5_password = os.getenv("MT5_PASSWORD")
        mt5_server = os.getenv("MT5_SERVER")
        mt5_path = self._find_mt5_path()

        init_kwargs = {}
        if mt5_path:
            init_kwargs['path'] = mt5_path
        
        if mt5_login and mt5_password and mt5_server:
            try:
                init_kwargs['login'] = int(mt5_login)
                init_kwargs['password'] = mt5_password
                init_kwargs['server'] = mt5_server
            except ValueError:
                logging.error("MT5_LOGIN deve ser numérico.")

        if mt5.initialize(**init_kwargs):
            self.connected = True
            logging.info(f"✅ Conectado ao MT5: {mt5.terminal_info()}")
            return True
        
        # Se falhar com argumentos, tenta sem (auto-detect padrão)
        if not self.connected and not init_kwargs:
             if mt5.initialize():
                self.connected = True
                logging.info(f"✅ Conectado ao MT5 (Auto): {mt5.terminal_info()}")
                return True

        logging.error(f"❌ Falha ao inicializar MT5: {mt5.last_error()}")
        return False

    def subscribe_book(self, symbol: str) -> bool:
        """
        Assina o livro de ofertas para um ativo.
        """
        if not self.connected:
            if not self._initialize_connection():
                return False

        if symbol in self.subscribed_symbols:
            return True

        if mt5.symbol_select(symbol, True):
            if mt5.market_book_add(symbol):
                self.subscribed_symbols.add(symbol)
                logging.info(f"✅ Livro assinado para {symbol}")
                return True
            else:
                logging.error(f"❌ Falha no market_book_add({symbol}): {mt5.last_error()}")
        else:
            logging.error(f"❌ Símbolo {symbol} não encontrado no MT5.")
            
        return False

    def get_orderbook_snapshot(self, symbol: str, depth: int = 20) -> Optional[Dict[str, np.ndarray]]:
        """
        Retorna um snapshot do livro formatado para Heatmap e Análise.
        
        Retorna:
            Dict com:
            - bids: array [[price, vol], ...]
            - asks: array [[price, vol], ...]
            - timestamp: float
        """
        # Garante assinatura
        if symbol not in self.subscribed_symbols:
            if not self.subscribe_book(symbol):
                return None

        # Obtém book
        book = mt5.market_book_get(symbol)
        if book is None:
            return None
            
        # Processamento rápido com NumPy
        # book é uma tupla de tuplas. Convertendo para array estruturado ou direto para float.
        # Estrutura do item: (type, price, volume, volume_real)
        
        # Filtrar Bids (type=2) e Asks (type=1)
        # Otimização: Iterar uma vez só ou usar list comprehension rápida
        
        bids = []
        asks = []
        
        for item in book:
            # item.type: 1=Sell(Ask), 2=Buy(Bid)
            # Tenta obter volume real (float), fallback para volume (int)
            if hasattr(item, 'volume_real'):
                vol = item.volume_real
            elif hasattr(item, 'volume_dbl'):
                vol = item.volume_dbl
            else:
                vol = float(item.volume)
            
            if item.type == 2: # Bid
                bids.append([item.price, vol])
            elif item.type == 1: # Ask
                asks.append([item.price, vol])

        # Ordenação
        # Bids: Maior preço primeiro
        bids.sort(key=lambda x: x[0], reverse=True)
        # Asks: Menor preço primeiro
        asks.sort(key=lambda x: x[0])

        # Limitar profundidade
        bids = bids[:depth]
        asks = asks[:depth]
        
        # Converte para numpy arrays
        bids_np = np.array(bids, dtype=np.float64) if bids else np.empty((0, 2))
        asks_np = np.array(asks, dtype=np.float64) if asks else np.empty((0, 2))
        ts = datetime.now().timestamp()

        # Persistência no Banco de Dados (Assíncrona)
        if self.db:
             self.db.insert_snapshot(symbol, bids_np, asks_np, ts)

        return {
            "bids": bids_np,
            "asks": asks_np,
            "timestamp": ts
        }

    def get_latest_tick(self, symbol: str):
        """
        Retorna dados de último negócio (L1).
        """
        if not self.connected: return None
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return tick._asdict()
        return None

    def disconnect(self):
        """
        Limpa assinaturas e desconecta.
        """
        for s in self.subscribed_symbols:
            mt5.market_book_release(s)
        mt5.shutdown()
        self.connected = False
        logging.info("MT5 Desconectado.")

if __name__ == "__main__":
    # Teste rápido
    collector = MT5MarketCollector()
    sym = "PETR4"
    print(f"Testando coleta para {sym}...")
    
    snapshot = collector.get_orderbook_snapshot(sym)
    if snapshot:
        print(f"Snapshot recebido!")
        print(f"Top Bid: {snapshot['bids'][0] if len(snapshot['bids']) > 0 else 'N/A'}")
        print(f"Top Ask: {snapshot['asks'][0] if len(snapshot['asks']) > 0 else 'N/A'}")
    else:
        print("Falha ao obter snapshot (mercado fechado?)")
    
    collector.disconnect()
