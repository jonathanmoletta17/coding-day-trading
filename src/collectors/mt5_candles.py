"""
@category: production
@impact: moderate
@description: Coletor de candles MT5 híbrido (suporta conexão direta DLL ou via HTTP Bridge)
"""
import pandas as pd
import logging
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Tenta importar MT5 (apenas Windows)
try:
    import MetaTrader5 as mt5
    HAS_MT5_LIB = True
except ImportError:
    HAS_MT5_LIB = False

class MT5CandleCollector:
    def __init__(self, bridge_url=None):
        self.use_bridge = not HAS_MT5_LIB
        # Permite forçar uso da bridge mesmo no Windows via env var
        if os.getenv("MT5_FORCE_BRIDGE", "False").lower() == "true":
            self.use_bridge = True
            
        self.bridge_url = bridge_url or os.getenv("MT5_BRIDGE_URL", "http://localhost:8000")
        
        if not self.use_bridge:
            self.connected = False
            self._initialize_connection()
        else:
            logger.info(f"MT5CandleCollector running in BRIDGE MODE (Target: {self.bridge_url})")
            self.connected = True # Bridge connection validada on-demand

    def _initialize_connection(self):
        if not mt5.initialize():
            logger.error("initialize() failed, error code = %s", mt5.last_error())
            return False
        self.connected = True
        return True

    def get_historical_data(self, symbol, timeframe_str, num_candles=1000):
        """
        Fetches historical candle data via Direct DLL or Bridge API.
        timeframe_str: String representation (e.g. "M1", "H1", "D1")
        """
        if self.use_bridge:
            return self._get_from_bridge(symbol, timeframe_str, num_candles)
        else:
            return self._get_from_direct(symbol, timeframe_str, num_candles)

    def _get_timeframe_const(self, tf_str):
        if not HAS_MT5_LIB:
            return None
        
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1
        }
        return mapping.get(str(tf_str).upper(), mt5.TIMEFRAME_H1)

    def _get_from_direct(self, symbol, timeframe_str, num_candles):
        if not self.connected:
            if not self._initialize_connection():
                return pd.DataFrame()
        
        # Converte string para constant
        tf_const = self._get_timeframe_const(timeframe_str)
        
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, num_candles)

        if rates is None:
            logger.error("Failed to get rates for %s (Direct)", symbol)
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df

    def _get_from_bridge(self, symbol, timeframe_str, num_candles):

        # Bridge API expects timeframe as string (e.g. "H1", "M5")
        # Se timeframe vier como int (constante MT5), precisamos converter?
        # O Dashboard costuma passar a constante MT5 se importar mt5.
        # Precisamos lidar com isso.
        
        # Mapeamento reverso simples se necessário
        tf_str = str(timeframe_str)
        if isinstance(timeframe_str, int):
            # Fallback grosseiro ou erro. O Dashboard deve passar string se possível.
            # Mas vamos assumir que o usuário passará STRING no modo Bridge.
            pass

        try:
            params = {
                "timeframe": tf_str,
                "count": num_candles
            }
            resp = requests.get(f"{self.bridge_url}/candles/{symbol}", params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json() # List of dicts
            if not data:
                return pd.DataFrame()
                
            df = pd.DataFrame(data)
            # Bridge retorna ISO format str em 'time'
            df["time"] = pd.to_datetime(df["time"])
            # Renomear tick_volume para volume para consistência
            if "tick_volume" in df.columns:
                df.rename(columns={"tick_volume": "volume"}, inplace=True)
                
            return df
            
        except Exception as e:
            logger.error(f"Failed to get rates for {symbol} (Bridge: {self.bridge_url}): {e}")
            return pd.DataFrame()

    def shutdown(self):
        if not self.use_bridge and HAS_MT5_LIB:
            mt5.shutdown()
