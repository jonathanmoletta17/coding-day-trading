import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.collectors.crypto_market_data import BinanceCollector
from src.visualization.orderbook_viz import OrderBookVisualizer
from src.analysis.indicators import TechnicalIndicators
from src.analysis.alerts import AlertSystem
from src.analysis.patterns import PatternRecognizer

st.set_page_config(layout="wide", page_title="Day Trading Dashboard")

st.title("Day Trading Dashboard")

# Sidebar
st.sidebar.header("Configuration")
mode = st.sidebar.radio("Mode", ["Crypto (Binance)", "MT5 (MetaTrader5)"], index=0)

if "crypto_collector" not in st.session_state:
    st.session_state.crypto_collector = BinanceCollector()

if "crypto_streaming" not in st.session_state:
    st.session_state.crypto_streaming = False

if "orderbook_viz" not in st.session_state:
    st.session_state.orderbook_viz = OrderBookVisualizer(max_history=120, price_levels=50)

if mode == "Crypto (Binance)":
    symbol = st.sidebar.text_input("Symbol", "BTCUSDT").upper()

    col_a, col_b = st.sidebar.columns(2)
    start_clicked = col_a.button("▶️ Iniciar Stream", use_container_width=True)
    stop_clicked = col_b.button("⏹️ Parar Stream", use_container_width=True)

    if start_clicked:
        st.session_state.crypto_collector.start_stream(symbol)
        st.session_state.crypto_streaming = True
        time.sleep(0.2)

    if stop_clicked:
        st.session_state.crypto_collector.stop_stream()
        st.session_state.crypto_streaming = False
        time.sleep(0.2)

    snapshot = st.session_state.crypto_collector.get_orderbook_snapshot(symbol)
    if not snapshot:
        st.warning("Nenhum snapshot disponível ainda.")
        st.stop()

    bids = snapshot["bids"]
    asks = snapshot["asks"]

    best_bid = float(bids[0][0]) if len(bids) else 0.0
    best_ask = float(asks[0][0]) if len(asks) else 0.0
    spread = best_ask - best_bid if best_bid and best_ask else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("Best Bid", f"{best_bid:.2f}")
    m2.metric("Best Ask", f"{best_ask:.2f}")
    m3.metric("Spread", f"{spread:.2f}")

    st.session_state.orderbook_viz.update(snapshot)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("Depth Chart")
        st.plotly_chart(st.session_state.orderbook_viz.generate_depth_chart(snapshot), use_container_width=True)

        st.subheader("Order Book Heatmap")
        st.plotly_chart(st.session_state.orderbook_viz.generate_heatmap_fig(), use_container_width=True)

    with col2:
        st.subheader("Order Book (Top Levels)")
        top_levels = min(len(bids), len(asks), 10)
        df_levels = []
        for i in range(top_levels):
            df_levels.append(
                {
                    "Bid Price": float(bids[i][0]),
                    "Bid Vol": float(bids[i][1]),
                    "Ask Price": float(asks[i][0]),
                    "Ask Vol": float(asks[i][1]),
                }
            )
        st.dataframe(df_levels, use_container_width=True)

elif mode == "MT5 (MetaTrader5)":
    symbol = st.sidebar.text_input("Symbol", "EURUSD").upper()
    try:
        import MetaTrader5 as mt5
        from src.collectors.mt5_candles import MT5CandleCollector
    except Exception:
        st.error("MetaTrader5 não está disponível neste ambiente.")
        st.stop()

    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "D1": mt5.TIMEFRAME_D1,
    }
    timeframe_str = st.sidebar.selectbox("Timeframe", list(timeframe_map.keys()), index=1)
    timeframe = timeframe_map[timeframe_str]

    if st.sidebar.button("Fetch Data"):
        collector = MT5CandleCollector()
        df = collector.get_historical_data(symbol, timeframe, num_candles=500)
        collector.shutdown()

        if df.empty:
            st.error("Failed to fetch data. Ensure MetaTrader 5 is running.")
            st.stop()

        ti = TechnicalIndicators(use_talib=False)
        df = ti.add_all_indicators(df)

        pr = PatternRecognizer()
        df = pr.add_all_patterns(df)

        alerts_system = AlertSystem()
        alerts = alerts_system.check_signals(df, symbol)

        col1, col2 = st.columns([3, 1])
        with col1:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])

            fig.add_trace(
                go.Candlestick(
                    x=df["time"],
                    open=df["open"],
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    name="Price",
                ),
                row=1,
                col=1,
            )

            hammer_mask = df["HAMMER"]
            if hammer_mask.any():
                fig.add_trace(
                    go.Scatter(
                        x=df[hammer_mask]["time"],
                        y=df[hammer_mask]["low"],
                        mode="markers",
                        marker=dict(symbol="triangle-up", size=10, color="lime"),
                        name="Hammer",
                    ),
                    row=1,
                    col=1,
                )

            eng_bull_mask = df["ENGULFING_BULLISH"]
            if eng_bull_mask.any():
                fig.add_trace(
                    go.Scatter(
                        x=df[eng_bull_mask]["time"],
                        y=df[eng_bull_mask]["low"],
                        mode="markers",
                        marker=dict(symbol="arrow-up", size=10, color="green"),
                        name="Engulfing Bull",
                    ),
                    row=1,
                    col=1,
                )

            eng_bear_mask = df["ENGULFING_BEARISH"]
            if eng_bear_mask.any():
                fig.add_trace(
                    go.Scatter(
                        x=df[eng_bear_mask]["time"],
                        y=df[eng_bear_mask]["high"],
                        mode="markers",
                        marker=dict(symbol="arrow-down", size=10, color="red"),
                        name="Engulfing Bear",
                    ),
                    row=1,
                    col=1,
                )

            fig.add_trace(
                go.Scatter(x=df["time"], y=df["BB_UPPER_20"], line=dict(color="gray", width=1), name="BB Upper"),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(x=df["time"], y=df["BB_LOWER_20"], line=dict(color="gray", width=1), name="BB Lower"),
                row=1,
                col=1,
            )
            fig.add_trace(go.Scatter(x=df["time"], y=df["EMA_9"], line=dict(color="blue", width=1), name="EMA 9"), row=1, col=1)
            fig.add_trace(
                go.Scatter(x=df["time"], y=df["EMA_21"], line=dict(color="orange", width=1), name="EMA 21"),
                row=1,
                col=1,
            )

            fig.add_trace(go.Scatter(x=df["time"], y=df["RSI_14"], line=dict(color="purple", width=2), name="RSI"), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

            fig.update_layout(height=800, title=f"{symbol} Analysis", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Data")
            st.dataframe(df.tail())

        with col2:
            st.subheader("Alerts")
            if alerts:
                for alert in alerts:
                    if alert.severity == "CRITICAL":
                        st.error(f"{alert.timestamp.time()} - {alert.message}")
                    elif alert.severity == "WARNING":
                        st.warning(f"{alert.timestamp.time()} - {alert.message}")
                    else:
                        st.info(f"{alert.timestamp.time()} - {alert.message}")
            else:
                st.write("No active alerts.")

            st.subheader("Statistics")
            st.write(f"Current Price: {df.iloc[-1]['close']:.5f}")
            st.write(f"RSI: {df.iloc[-1]['RSI_14']:.2f}")
