import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Optional, List

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MarketDataCollector:
    """
    Classe responsável pela coleta de dados de mercado.
    Atualmente suporta yfinance (Yahoo Finance) para dados históricos e atrasados.
    Pronta para extensão para APIs de tempo real (Websockets/MetaTrader5).
    """
    
    def __init__(self, symbols: List[str], interval: str = "1m"):
        """
        Inicializa o coletor.
        :param symbols: Lista de símbolos (ex: ['PETR4.SA', 'VALE3.SA', '^BVSP'])
        :param interval: Intervalo dos candles (ex: '1m', '5m', '1d')
        """
        self.symbols = symbols
        self.interval = interval
        self.data = {}

    def fetch_data(self, period: str = "1d") -> pd.DataFrame:
        """
        Coleta dados do Yahoo Finance.
        :param period: Período de dados para baixar (ex: '1d', '5d', '1mo')
        :return: DataFrame com dados de todos os símbolos
        """
        logging.info(f"Iniciando coleta para {self.symbols} com intervalo {self.interval}...")
        
        try:
            # Baixa dados em lote
            df = yf.download(
                tickers=self.symbols,
                period=period,
                interval=self.interval,
                group_by='ticker',
                auto_adjust=True,
                prepost=True,
                threads=True
            )
            
            if df.empty:
                logging.warning("Nenhum dado retornado.")
                return pd.DataFrame()
            
            logging.info("Dados coletados com sucesso.")
            return df
        
        except Exception as e:
            logging.error(f"Erro na coleta de dados: {e}")
            return pd.DataFrame()

    def get_latest_price(self, symbol: str) -> dict:
        """
        Obtém o último preço disponível e dados de livro (Best Bid/Ask) se disponível.
        """
        try:
            ticker = yf.Ticker(symbol)
            fast_info = ticker.fast_info
            
            # Dados básicos via fast_info (mais rápido)
            data = {
                "last_price": fast_info.last_price,
                "previous_close": fast_info.previous_close,
                "open": fast_info.open,
                "day_high": fast_info.day_high,
                "day_low": fast_info.day_low,
                "last_volume": fast_info.last_volume,
                "currency": fast_info.currency
            }

            # Tenta buscar dados de Bid/Ask via info (mais lento, mas necessário para Order Book)
            # Nota: yfinance para B3 muitas vezes retorna bidSize/askSize como 0, mas o preço costuma vir.
            try:
                info = ticker.info
                data["bid"] = info.get("bid", 0.0)
                data["ask"] = info.get("ask", 0.0)
                data["bid_size"] = info.get("bidSize", 0)
                data["ask_size"] = info.get("askSize", 0)
            except Exception as e:
                logging.warning(f"Não foi possível obter Bid/Ask para {symbol}: {e}")
                data["bid"] = 0.0
                data["ask"] = 0.0

            return data
        except Exception as e:
            logging.error(f"Erro ao obter preço para {symbol}: {e}")
            return {}

if __name__ == "__main__":
    # Teste rápido
    symbols = ["PETR4.SA", "VALE3.SA", "WDO=F"] # WDO=F é Mini Dólar Futuro no Yahoo (aproximado)
    collector = MarketDataCollector(symbols)
    df = collector.fetch_data()
    print(df.head())
