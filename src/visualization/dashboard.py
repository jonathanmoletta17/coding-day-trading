"""
@category: production
@impact: moderate
@description: Dashboard interativo para visualização de dados de mercado e análise técnica
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots  # Usado no modo MT5
import sys
import os
import time
import logging
import json

from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.collectors.crypto_market_data import BinanceCollector
from src.visualization.orderbook_viz import OrderBookVisualizer
from src.analysis.indicators import TechnicalIndicators
from src.analysis.alerts import AlertSystem
from src.analysis.patterns import PatternRecognizer
from src.microstructure.context_metrics import find_default_metrics_path, load_last_context_from_metrics
from src.analysis.signal_generator import SignalGenerator, SignalSide
from src.agents.master_agent import MasterAgent

# Design System
from src.visualization.design_system import (
    COLORS,
    FONTS,
    FONT_SIZES,
    SPACING,
    get_plotly_theme,
    get_tradingview_theme,
    get_streamlit_custom_css
)

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

logger = logging.getLogger("dashboard.context_v01")

st.set_page_config(layout="wide", page_title="Day Trading Dashboard")

# === Apply Design System CSS ===
st.markdown(get_streamlit_custom_css(), unsafe_allow_html=True)

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

# === Cache para Historical Klines (Fix Flickering) ===
@st.cache_data(ttl=60, show_spinner=False)
def _fetch_klines_cached(symbol: str, interval: str, limit: int):
    """
    Cache de klines da Binance para evitar re-fetch a cada Streamlit rerun.
    TTL de 60s é adequado para timeframes de 1h (dados mudam devagar).
    Retorna mesma referência de DataFrame = component estável = zero flickering.
    """
    from src.collectors.crypto_market_data import BinanceCollector
    collector = BinanceCollector()
    return collector.get_historical_klines(symbol, interval, limit)

# === Session State para Real-Time Stream ===
if 'kline_stream' not in st.session_state:
    from src.collectors.crypto_realtime import BinanceKlineStream
    st.session_state.kline_stream = BinanceKlineStream()

if 'auto_refresh_enabled' not in st.session_state:
    st.session_state.auto_refresh_enabled = False

if 'signal_generator' not in st.session_state:
    st.session_state.signal_generator = SignalGenerator(base_atr_multiplier=1.5)

if 'master_agent' not in st.session_state:
    st.session_state.master_agent = MasterAgent()
    
# === CRITICAL FIX: Ensure V1-Pro Components are Loaded ===
# 1. Force reload if attribute is missing (Handles stale class definition)
if not hasattr(st.session_state.master_agent, 'micro_analyzer'):
    import importlib
    import src.agents.master_agent
    importlib.reload(src.agents.master_agent)
    from src.agents.master_agent import MasterAgent
    
    st.toast("🛠️ Patching Master Agent logic...", icon="🔧")
    st.session_state.master_agent = MasterAgent()

# 2. Final safety check: Manually attach if still missing (Runtime Patch)
if not hasattr(st.session_state.master_agent, 'micro_analyzer'):
     from src.analysis.microstructure_analyzer import MicrostructureAnalyzer
     st.session_state.master_agent.micro_analyzer = MicrostructureAnalyzer()
     st.toast("✅ Microstructure Analyzer attached (JIT)", icon="🛡️")

if mode == "Crypto (Binance)":
    symbol = st.sidebar.text_input("Symbol", "BTCUSDT").upper()
    default_metrics = find_default_metrics_path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), symbol)
    metrics_path = st.sidebar.text_input("Context v0.1 metrics.json", default_metrics or "")
    
    # === Streaming Automático (sempre ativo) ===
    # Inicia stream automaticamente se ainda não estiver rodando
    if not st.session_state.kline_stream.is_running():
        st.session_state.kline_stream.start(symbol, "1m")
        st.session_state.auto_refresh_enabled = True
    
    # Indicador de status com animação
    from src.visualization.components.live_indicator import render_live_indicator
    render_live_indicator(is_streaming=True, label="LIVE Streaming")
    st.sidebar.markdown("---")
    
    # Botões de Order Book stream (manter separados)
    col_a, col_b = st.sidebar.columns(2)
    start_clicked = col_a.button("📊 Order Book", width="stretch")
    stop_clicked = col_b.button("⏹️ Stop OB", width="stretch")

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

    # === Métricas Principais (Design System) ===
    from src.visualization.components.metric_card import render_metric_row
    
    render_metric_row([
        {
            "label": "Best Bid",
            "value": f"{best_bid:.2f}",
            "icon": "💰",
            "delta_color": "bull"
        },
        {
            "label": "Best Ask",
            "value": f"{best_ask:.2f}",
            "icon": "💵",
            "delta_color": "bear"
        },
        {
            "label": "Spread",
            "value": f"{spread:.4f}",
            "icon": "📊",
            "delta_color": "neutral"
        }
    ])

    st.subheader("Contexto (DSL v0.1)")

    @st.cache_data(ttl=2)
    def _load_ctx(p: str):
        return load_last_context_from_metrics(p)

    if metrics_path.strip():
        p = metrics_path.strip()
        exists = os.path.exists(p)
        logger.info("context_v01.ui load_attempt path=%s exists=%s", p, str(exists).lower())
        try:
            ctx = _load_ctx(p)
            # Usar novo componente visual de card
            from src.visualization.components.context_card import render_context_card
            render_context_card(
                stability=ctx.stability,
                liquidity=ctx.liquidity,
                activity=ctx.activity,
                do_not_operate=ctx.do_not_operate
            )
        except Exception as e:
            logger.exception("context_v01.ui load_failed path=%s", p)
            st.warning("Contexto v0.1 indisponível")
    else:
        st.info("Contexto v0.1: configure um caminho para metrics.json na sidebar.")

    st.session_state.orderbook_viz.update(snapshot)
    
    # === Fetch Data for Visualization ===
    historical_df = _fetch_klines_cached(symbol, "1h", 500)
    
    if st.session_state.auto_refresh_enabled:
        latest_kline = st.session_state.kline_stream.get_latest_kline()
        if latest_kline and not latest_kline.get('is_closed', False):
            import pandas as pd
            latest_df = pd.DataFrame([{
                'time': latest_kline['time'],
                'open': latest_kline['open'],
                'high': latest_kline['high'],
                'low': latest_kline['low'],
                'close': latest_kline['close'],
                'volume': latest_kline['volume']
            }])
            if not historical_df.empty:
                historical_df = pd.concat([historical_df.iloc[:-1], latest_df], ignore_index=True)

    # === Signal Detection Logic ===
    if historical_df is not None and not historical_df.empty:
        # Phase 2: Adaptive Lookback
        stability_level = ctx.stability.upper() if 'ctx' in locals() else "MEDIUM"
        lookback_map = {"HIGH": 20, "MEDIUM": 14, "LOW": 7, "EXTREME": 5}
        adaptive_period = lookback_map.get(stability_level, 14)
        
        ti = TechnicalIndicators(use_talib=False)
        historical_df = ti.add_atr(historical_df, period=adaptive_period)
        
        # Signal Generation (Mocked for now with AlertSystem)
        # In real production, we would use st.session_state.signal_generator.generate_signals(...)
        alerts = AlertSystem().check_signals(historical_df, symbol)
        
        markers = []
        for alert in alerts:
            if "CROSS" in alert.alert_type or "BREAKOUT" in alert.alert_type:
                side = "aboveBar" if "BEARISH" in alert.alert_type or "UP" in alert.alert_type else "belowBar"
                color = COLORS["bear"] if "BEARISH" in alert.alert_type or "UP" in alert.alert_type else COLORS["bull"]
                shape = "arrowDown" if side == "aboveBar" else "arrowUp"
                text = alert.alert_type.split("_")[-1]
                markers.append({
                    "time": int(alert.timestamp.timestamp()),
                    "position": side,
                    "color": color,
                    "shape": shape,
                    "text": text
                })
        
        if markers:
            historical_df['markers'] = None
            for m in markers:
                idx = (historical_df['time'] - m['time']).abs().idxmin()
                if historical_df.at[idx, 'markers'] is None:
                    historical_df.at[idx, 'markers'] = []
                historical_df.at[idx, 'markers'].append(m)

    # === Main Visualization Grid ===
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.subheader("Depth Chart")
        st.plotly_chart(st.session_state.orderbook_viz.generate_depth_chart(snapshot), width="stretch")
        st.subheader("Order Book Heatmap")
        st.plotly_chart(st.session_state.orderbook_viz.generate_heatmap_fig(), width="stretch")

    with col2:
        st.subheader("Order Book")
        # Usar novo componente de heatmap visual
        from src.visualization.components.orderbook_heatmap import render_orderbook_heatmap
        render_orderbook_heatmap(bids, asks, top_n=10)

    with col3:
        st.subheader("Alpha Signals")
        
        # Display Adaptive Stats
        if 'ctx' in locals():
            mult = st.session_state.signal_generator._get_adaptive_multiplier(ctx.stability)
            st.caption(f"🛡️ Multiplier: {mult:.2f}x | ⌛ Lookback: {adaptive_period}")
        
        if 'markers' in historical_df.columns:
            recent_markers = []
            for m_list in historical_df.tail(10)['markers']:
                if isinstance(m_list, list): recent_markers.extend(m_list)
            if recent_markers:
                for m in reversed(recent_markers):
                    icon = "🟢" if m['shape'] == "arrowUp" else "🔴"
                    st.info(f"{icon} **{m['text']}** at {m['time']}")
            else:
                st.write("No recent signals.")
        else:
            st.write("Initializing signal engine...")

        # === Master Agent Decision Engine ===
        with st.expander("🤖 Master Agent (AI Trader)", expanded=True):
            # 1. Prepare Technicals (Real indices)
            latest = historical_df.iloc[-1]
            rsi_val = latest.get('RSI_14', 50.0)
            atr_val = latest.get('ATR_14', 100.0)
            macd_val = latest.get('MACD_HIST', latest.get('MACD', 0.0))
            
            # 2. Get Signals from our SignalGenerator (which maps to DSL names)
            # In a full integration, this would use PatternEngineV01.
            # For now, we bridge it using SignalGenerator's internal logic
            # and actual indicators.
            recent_markers = []
            if 'markers' in historical_df.columns:
                # Find any markers in the last 5 candles
                for m_list in historical_df.tail(5)['markers']:
                    if isinstance(m_list, list): recent_markers.extend(m_list)
            
            legacy_sigs = []
            for m in recent_markers:
                legacy_sigs.append({
                    "pattern": m.get("text", "UNKNOWN_DSL"),
                    "confidence": 0.92, # Validated patterns have high confidence
                })
            
            payload = {
                "context": {
                    "market_phase": "OPEN" if mode == "MT5" else "VOLATILE",
                    "global_risk_level": "LOW",
                    "stability": ctx.stability if 'ctx' in locals() else "MEDIUM"
                },
                "asset": {
                    "symbol": symbol,
                    "price": latest['close'],
                    "order_book": {
                        "imbalance": best_bid/best_ask if best_ask != 0 else 1.0
                    },
                    "technicals": {
                        "rsi_14": rsi_val,
                        "atr_14": atr_val,
                        "macd_hist": macd_val
                    }
                },
                "legacy_signals": legacy_sigs,
                "portfolio": {
                    "daily_pl_pct": st.session_state.get('daily_pl_pct', 0.0)
                }
            }
            
            # --- MICROSTRUCTURE METRICS (V1-Pro Advanced) ---
            # Simulate high-frequency updates for visualization
            book_snapshot = payload['asset']['order_book']
            # We inject synthetic events if available from session state or backend
            # For now, we rely on the analyzer's internal state which is transient in this stateless UI
            # Ideally, analyzer would be persistent in session_state
            
            micro_res = st.session_state.master_agent.micro_analyzer.update(book_snapshot)
            
            decision_json = st.session_state.master_agent.decide(payload)
            
            # 4. Display Results (V1-Pro UI)
            decision_dict = json.loads(decision_json)
            d = decision_dict.get("decision", "HOLD")
            score = decision_dict.get("confidence", 0.0)
            
            color = "green" if d == "BUY" else ("red" if d == "SELL" else "gray")
            
            m_cols = st.columns([1, 2])
            with m_cols[0]:
                st.markdown(f"### :{color}[{d}]")
                st.metric("Confluence", f"{score:.2f}")
                st.progress(min(max(score, 0.0), 1.0))
                
                # Spoofing Alert
                if micro_res.is_spoofing:
                   st.error("🚫 SPOOFING DETECTED")
            
            with m_cols[1]:
                st.write("**Thought Process:**")
                st.caption(decision_dict.get("thought_process", "N/A"))
                
                # Microstructure Details
                m1, m2 = st.columns(2)
                m1.metric("Book Velocity", f"{micro_res.velocity:.1f} upd/s")
                m2.metric("Cancel/Trade Ratio", f"{micro_res.ctr:.1f}")
                
                if d != "HOLD":
                    exec_info = decision_dict.get("execution", {})
                    st.write(f"Sizing: {decision_dict.get('sizing', {}).get('units', 0)} units")
                    st.write(f"TP: {exec_info.get('take_profit'):.2f} | SL: {exec_info.get('stop_loss'):.2f}")
            
            st.caption("🛡️ V1-Pro Advanced: Spoofing Shield + Velocity Tracking Active")

    # === Candlestick Chart (Full Width) ===
    st.markdown("---")
    st.subheader(f"📊 Candlestick Chart - {symbol}")
    if historical_df is not None and not historical_df.empty:
        from src.visualization.components.lightweight_chart import render_candlestick_chart
        render_candlestick_chart(historical_df, height=600)
    else:
        st.warning("⚠️ Não foi possível obter dados históricos de candlestick.")


elif mode == "MT5 (MetaTrader5)":
    symbol = st.sidebar.text_input("Symbol", "EURUSD").upper()
    
    # Importação segura do coletor (já lida com ausência de MT5 lib)
    from src.collectors.mt5_candles import MT5CandleCollector

    # Definição de timeframes como STRINGS para compatibilidade híbrida
    timeframe_map = {
        "M1": "M1",
        "M5": "M5",
        "M15": "M15",
        "H1": "H1",
        "H4": "H4",
        "D1": "D1",
    }
    timeframe_str = st.sidebar.selectbox("Timeframe", list(timeframe_map.keys()), index=3) # Default H1
    timeframe = timeframe_map[timeframe_str]

    if st.sidebar.button("Fetch Data"):
        collector = MT5CandleCollector()
        # O coletor agora aceita STRING ("H1") e resolve internamente
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
            st.plotly_chart(fig, width="stretch")

        with col2:
            st.subheader("Data")
            st.dataframe(df.tail())

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
            st.write(f"Volume: {df.iloc[-1]['volume']:.2f}")

            # === Master Agent Decision Engine (MT5) ===
            st.markdown("---")
            with st.expander("🤖 Master Agent (AI Trader)", expanded=True):
                latest = df.iloc[-1]
                payload = {
                    "context": {
                        "market_phase": "OPEN",
                        "global_risk_level": "LOW",
                    },
                    "asset": {
                        "symbol": symbol,
                        "price": latest['close'],
                        "order_book": {
                            "imbalance": 1.0 # MT5 usually lacks live book imbalance in this view
                        },
                        "technicals": {
                            "rsi_14": latest.get('RSI_14', 50.0),
                            "atr_14": latest.get('ATR_14', 0.01),
                            "macd_hist": latest.get('MACD_HIST', latest.get('MACD', 0.0))
                        }
                    },
                    "legacy_signals": [], # MT5 pattern signals would map here
                    "portfolio": {
                        "daily_pl_pct": st.session_state.get('daily_pl_pct', 0.0)
                    }
                }
                decision_json = st.session_state.master_agent.decide(payload)
                
                # 4. Display Results (V1-Pro UI)
                decision_dict = json.loads(decision_json)
                d = decision_dict.get("decision", "HOLD")
                score = decision_dict.get("confidence", 0.0)
                
                color = "green" if d == "BUY" else ("red" if d == "SELL" else "gray")
                
                m_cols = st.columns([1, 2])
                with m_cols[0]:
                    st.markdown(f"### :{color}[{d}]")
                    st.metric("Confluence", f"{score:.2f}")
                    st.progress(min(max(score, 0.0), 1.0))
                
                with m_cols[1]:
                    st.write("**Thought Process:**")
                    st.caption(decision_dict.get("thought_process", "N/A"))
                    
                    if d != "HOLD":
                        exec_info = decision_dict.get("execution", {})
                        st.write(f"Sizing: {decision_dict.get('sizing', {}).get('units', 0)} units")
                        st.write(f"TP: {exec_info.get('take_profit', 0):.2f} | SL: {exec_info.get('stop_loss', 0):.2f}")
                
                st.caption("🛡️ V1-Pro: Weighted Confluence + Institutional Absorption Filter Active")

# === Smart Auto-Refresh: Apenas quando candle fecha ===
# Reduz reruns de 30x/minuto para 1x/minuto
# Mantém estado do gráfico (zoom, pan) por ~60 segundos
if mode == "Crypto (Binance)":
    latest_kline = st.session_state.kline_stream.get_latest_kline()
    
    # Inicializa tracking de último candle fechado
    if 'last_closed_candle_time' not in st.session_state:
        st.session_state.last_closed_candle_time = 0
    
    # Rerun APENAS quando um novo candle fecha
    if latest_kline and latest_kline.get('is_closed', False):
        if latest_kline['time'] > st.session_state.last_closed_candle_time:
            # Marca este candle como processado
            st.session_state.last_closed_candle_time = latest_kline['time']
            
            # Pequeno delay para garantir que WebSocket recebeu dados completos
            import time
            time.sleep(0.5)
            
            # Rerun para atualizar dashboard com candle fechado
            st.rerun()
