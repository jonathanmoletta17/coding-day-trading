import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """
    Calculates technical indicators for a given DataFrame.
    Expects DataFrame to have columns: 'open', 'high', 'low', 'close', 'volume' (case insensitive).
    """

    def __init__(self, use_talib=True):
        self.use_talib = use_talib
        if self.use_talib:
            try:
                import talib
                self.talib = talib
                logger.info("Using TA-Lib for indicator calculations.")
            except ImportError:
                self.use_talib = False
                logger.warning("TA-Lib not found. Falling back to pandas/numpy implementations.")

    def _get_column(self, df, name):
        """Helper to get column case-insensitively."""
        col = next((c for c in df.columns if c.lower() == name.lower()), None)
        if col is None:
            raise ValueError(f"Column '{name}' not found in DataFrame.")
        return df[col]

    def add_all_indicators(self, df):
        """Adds all available indicators to the DataFrame."""
        df = df.copy()
        df = self.add_ma(df, period=9, ma_type='ema')
        df = self.add_ma(df, period=21, ma_type='ema')
        df = self.add_ma(df, period=200, ma_type='sma')
        df = self.add_rsi(df, period=14)
        df = self.add_bollinger_bands(df, period=20, std_dev=2)
        df = self.add_macd(df)
        df = self.add_vwap(df)
        df = self.add_atr(df)
        return df

    def add_ma(self, df, period=14, ma_type='sma'):
        """Adds Moving Average."""
        close = self._get_column(df, 'close')
        col_name = f"{ma_type.upper()}_{period}"
        
        if self.use_talib:
            if ma_type.lower() == 'sma':
                df[col_name] = self.talib.SMA(close.values, timeperiod=period)
            elif ma_type.lower() == 'ema':
                df[col_name] = self.talib.EMA(close.values, timeperiod=period)
        else:
            if ma_type.lower() == 'sma':
                df[col_name] = close.rolling(window=period).mean()
            elif ma_type.lower() == 'ema':
                df[col_name] = close.ewm(span=period, adjust=False).mean()
        
        return df

    def add_rsi(self, df, period=14):
        """Adds Relative Strength Index."""
        close = self._get_column(df, 'close')
        col_name = f"RSI_{period}"

        if self.use_talib:
            df[col_name] = self.talib.RSI(close.values, timeperiod=period)
        else:
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df[col_name] = 100 - (100 / (1 + rs))
        return df

    def add_bollinger_bands(self, df, period=20, std_dev=2):
        """Adds Bollinger Bands (Upper, Middle, Lower)."""
        close = self._get_column(df, 'close')
        
        if self.use_talib:
            upper, middle, lower = self.talib.BBANDS(close.values, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev, matype=0)
            df[f'BB_UPPER_{period}'] = upper
            df[f'BB_MIDDLE_{period}'] = middle
            df[f'BB_LOWER_{period}'] = lower
        else:
            middle = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            df[f'BB_MIDDLE_{period}'] = middle
            df[f'BB_UPPER_{period}'] = middle + (std * std_dev)
            df[f'BB_LOWER_{period}'] = middle - (std * std_dev)
        return df

    def add_macd(self, df, fast_period=12, slow_period=26, signal_period=9):
        """Adds MACD, MACD Signal, and MACD Histogram."""
        close = self._get_column(df, 'close')
        
        if self.use_talib:
            macd, signal, hist = self.talib.MACD(close.values, fastperiod=fast_period, slowperiod=slow_period, signalperiod=signal_period)
            df['MACD'] = macd
            df['MACD_SIGNAL'] = signal
            df['MACD_HIST'] = hist
        else:
            fast_ema = close.ewm(span=fast_period, adjust=False).mean()
            slow_ema = close.ewm(span=slow_period, adjust=False).mean()
            df['MACD'] = fast_ema - slow_ema
            df['MACD_SIGNAL'] = df['MACD'].ewm(span=signal_period, adjust=False).mean()
            df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']
        return df

    def add_vwap(self, df):
        """Adds Volume Weighted Average Price."""
        try:
            close = self._get_column(df, 'close')
            high = self._get_column(df, 'high')
            low = self._get_column(df, 'low')
            volume = self._get_column(df, 'volume')
            
            typical_price = (high + low + close) / 3
            # Cumulative VWAP
            df['VWAP'] = (typical_price * volume).cumsum() / volume.cumsum()
        except ValueError:
             logger.warning("Could not calculate VWAP, missing columns.")
        return df

    def add_atr(self, df, period=14):
        """Adds Average True Range."""
        if self.use_talib:
            high = self._get_column(df, 'high').values
            low = self._get_column(df, 'low').values
            close = self._get_column(df, 'close').values
            df[f'ATR_{period}'] = self.talib.ATR(high, low, close, timeperiod=period)
        else:
            high = self._get_column(df, 'high')
            low = self._get_column(df, 'low')
            close = self._get_column(df, 'close')
            
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df[f'ATR_{period}'] = tr.rolling(window=period).mean()
        return df
