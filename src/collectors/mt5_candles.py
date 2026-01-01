import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MT5CandleCollector:
    def __init__(self):
        self.connected = False
        self._initialize_connection()

    def _initialize_connection(self):
        if not mt5.initialize():
            logger.error("initialize() failed, error code = %s", mt5.last_error())
            return False
        self.connected = True
        return True

    def get_historical_data(self, symbol, timeframe, num_candles=1000):
        """
        Fetches historical candle data.
        timeframe: mt5.TIMEFRAME_M1, mt5.TIMEFRAME_H1, etc.
        """
        if not self.connected:
            if not self._initialize_connection():
                return pd.DataFrame()

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_candles)

        if rates is None:
            logger.error("Failed to get rates for %s", symbol)
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        # Rename columns to match TechnicalIndicators expectation
        # MT5 columns: time, open, high, low, close, tick_volume, spread, real_volume
        df.rename(columns={"tick_volume": "volume"}, inplace=True)

        return df

    def shutdown(self):
        mt5.shutdown()
