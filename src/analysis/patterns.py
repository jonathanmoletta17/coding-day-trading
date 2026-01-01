import pandas as pd
import numpy as np


class PatternRecognizer:
    def __init__(self):
        pass

    def add_all_patterns(self, df: pd.DataFrame):
        df = df.copy()
        df = self.detect_doji(df)
        df = self.detect_hammer(df)
        df = self.detect_engulfing(df)
        return df

    def detect_doji(self, df: pd.DataFrame, threshold=0.03):
        df["DOJI"] = np.where(
            abs(df["open"] - df["close"]) <= (df["high"] - df["low"]) * threshold,
            True,
            False,
        )
        return df

    def detect_hammer(self, df: pd.DataFrame):
        body = abs(df["open"] - df["close"])
        lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
        upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)
        condition = (lower_shadow >= 2 * body) & (upper_shadow <= body * 0.5)
        df["HAMMER"] = condition
        return df

    def detect_engulfing(self, df: pd.DataFrame):
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        curr_open = df["open"]
        curr_close = df["close"]
        bullish_cond = (
            (prev_close < prev_open)
            & (curr_close > curr_open)
            & (curr_open < prev_close)
            & (curr_close > prev_open)
        )
        bearish_cond = (
            (prev_close > prev_open)
            & (curr_close < curr_open)
            & (curr_open > prev_close)
            & (curr_close < prev_open)
        )
        df["ENGULFING_BULLISH"] = bullish_cond
        df["ENGULFING_BEARISH"] = bearish_cond
        return df
