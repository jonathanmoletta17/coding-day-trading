import pandas as pd
from dataclasses import dataclass
from typing import List
from datetime import datetime

@dataclass
class Alert:
    timestamp: datetime
    symbol: str
    alert_type: str
    message: str
    severity: str # 'INFO', 'WARNING', 'CRITICAL'

class AlertSystem:
    def check_signals(self, df: pd.DataFrame, symbol: str) -> List[Alert]:
        """
        Checks for trading signals in the latest data points.
        """
        alerts = []
        if df.empty or len(df) < 2:
            return alerts

        # Get latest and previous row
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Timestamp
        ts = current.name if isinstance(current.name, datetime) else datetime.now()

        # 1. RSI Alerts
        if 'RSI_14' in df.columns:
            if current['RSI_14'] > 70 and previous['RSI_14'] <= 70:
                alerts.append(Alert(ts, symbol, 'RSI_OVERBOUGHT', f"RSI crossed above 70 ({current['RSI_14']:.2f})", 'WARNING'))
            elif current['RSI_14'] < 30 and previous['RSI_14'] >= 30:
                alerts.append(Alert(ts, symbol, 'RSI_OVERSOLD', f"RSI crossed below 30 ({current['RSI_14']:.2f})", 'WARNING'))

        # 2. MACD Alerts
        if 'MACD' in df.columns and 'MACD_SIGNAL' in df.columns:
            # Bullish Crossover
            if current['MACD'] > current['MACD_SIGNAL'] and previous['MACD'] <= previous['MACD_SIGNAL']:
                alerts.append(Alert(ts, symbol, 'MACD_CROSS_BULLISH', "MACD crossed above Signal", 'INFO'))
            # Bearish Crossover
            elif current['MACD'] < current['MACD_SIGNAL'] and previous['MACD'] >= previous['MACD_SIGNAL']:
                alerts.append(Alert(ts, symbol, 'MACD_CROSS_BEARISH', "MACD crossed below Signal", 'INFO'))

        # 3. Bollinger Bands Alerts
        if 'BB_UPPER_20' in df.columns and 'BB_LOWER_20' in df.columns:
            if current['close'] > current['BB_UPPER_20']:
                alerts.append(Alert(ts, symbol, 'BB_BREAKOUT_UP', f"Price closed above Upper Bollinger Band ({current['close']:.2f})", 'INFO'))
            elif current['close'] < current['BB_LOWER_20']:
                alerts.append(Alert(ts, symbol, 'BB_BREAKOUT_DOWN', f"Price closed below Lower Bollinger Band ({current['close']:.2f})", 'INFO'))

        # 4. EMA Crossover (9 vs 21)
        if 'EMA_9' in df.columns and 'EMA_21' in df.columns:
             if current['EMA_9'] > current['EMA_21'] and previous['EMA_9'] <= previous['EMA_21']:
                 alerts.append(Alert(ts, symbol, 'EMA_CROSS_GOLDEN', "EMA 9 crossed above EMA 21", 'CRITICAL'))
             elif current['EMA_9'] < current['EMA_21'] and previous['EMA_9'] >= previous['EMA_21']:
                 alerts.append(Alert(ts, symbol, 'EMA_CROSS_DEATH', "EMA 9 crossed below EMA 21", 'CRITICAL'))

        return alerts
