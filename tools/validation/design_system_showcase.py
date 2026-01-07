"""
@category: tool
@impact: low
@description: Showcase do Design System - Demonstra todos os componentes visuais com tema aplicado
"""
import streamlit as st
import sys
import os

# Add project root to path
sys.path.insert(0, '/home/workbench/projects/coding-day-trading')

from src.visualization.design_system import (
    COLORS, FONTS, FONT_SIZES, SPACING, BORDER_RADIUS, SHADOWS,
    get_streamlit_custom_css
)

st.set_page_config(layout="wide", page_title="Design System Showcase")

# Apply custom CSS
st.markdown(get_streamlit_custom_css(), unsafe_allow_html=True)

# === Header ===
st.title("🎨 Trading Dashboard - Design System Showcase")
st.markdown("Demonstração visual de todos os tokens de design e componentes.")

st.markdown("---")

# === Color Palette ===
st.header("1. Paleta de Cores")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Backgrounds")
    for name, color in [(k, v) for k, v in COLORS.items() if 'background' in k]:
        st.markdown(f"""
        <div style="
            background: {color};
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 8px;
            border: 1px solid {COLORS['border']};
        ">
            <strong>{name}</strong><br>
            <code>{color}</code>
        </div>
        """, unsafe_allow_html=True)

with col2:
    st.subheader("Text Colors")
    for name, color in [(k, v) for k, v in COLORS.items() if 'text' in k]:
        st.markdown(f"""
        <div style="
            background: {COLORS['background_secondary']};
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 8px;
        ">
            <span style="color: {color}; font-weight: 600;">{name}</span><br>
            <code>{color}</code>
        </div>
        """, unsafe_allow_html=True)

with col3:
    st.subheader("Status & Trading")
    for name, color in [(k, v) for k, v in COLORS.items() if any(x in k for x in ['bull', 'bear', 'success', 'error', 'warning', 'info', 'accent'])]:
        st.markdown(f"""
        <div style="
            background: {COLORS['background_secondary']};
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 8px;
            border-left: 4px solid {color};
        ">
            <strong style="color: {color};">{name}</strong><br>
            <code>{color}</code>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# === Typography ===
st.header("2. Tipografia")

st.markdown(f"""
<div style="background: {COLORS['background_secondary']}; padding: 24px; border-radius: 8px;">
    <h1>Heading 1 - {FONT_SIZES['h1']} (Bold)</h1>
    <h2>Heading 2 - {FONT_SIZES['h2']} (Semibold)</h2>
    <h3>Heading 3 - {FONT_SIZES['h3']} (Medium)</h3>
    <p style="font-size: {FONT_SIZES['body']};">Body Text - {FONT_SIZES['body']} (Regular)</p>
    <p style="font-size: {FONT_SIZES['caption']}; color: {COLORS['text_secondary']};">
        Caption Text - {FONT_SIZES['caption']} (Regular)
    </p>
    <code style="font-family: {FONTS['monospace']}; font-size: {FONT_SIZES['code']};">
        Monospace: 91728.19 USDT
    </code>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# === Spacing ===
st.header("3. Espaçamento (8pt Grid)")

spacing_demo = ""
for name, value in SPACING.items():
    spacing_demo += f"""
    <div style="
        display: flex;
        align-items: center;
        margin-bottom: 16px;
        background: {COLORS['background_secondary']};
        padding: 16px;
        border-radius: 8px;
    ">
        <div style="
            width: {value}px;
            height: 32px;
            background: {COLORS['accent']};
            margin-right: 16px;
        "></div>
        <span><strong>{name.upper()}</strong>: {value}px</span>
    </div>
    """

st.markdown(spacing_demo, unsafe_allow_html=True)

st.markdown("---")

# === Components ===
st.header("4. Componentes de Exemplo")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Best Bid", "91728.19", "+0.02%")

with col2:
    st.metric("Best Ask", "91728.20", "-0.01%", delta_color="inverse")

with col3:
    st.metric("Spread", "0.01", None)

st.markdown("---")

# === Buttons ===
st.header("5. Botões")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.button("▶️ Iniciar Stream", use_container_width=True)
with col2:
    st.button("⏹️ Parar Stream", use_container_width=True)
with col3:
    st.button("🔄 Refresh", use_container_width=True)
with col4:
    st.button("⚙️ Settings", use_container_width=True)

st.markdown("---")

# === Status Messages ===
st.header("6. Mensagens de Status")
st.success("✅ Operação bem-sucedida! 500 candles carregados.")
st.info("ℹ️ WebSocket conectado ao stream da Binance.")
st.warning("⚠️ Latência elevada detectada (250ms).")
st.error("❌ Erro ao conectar com MT5 Bridge.")

st.markdown("---")

# === Code Block ===
st.header("7. Blocos de Código")
st.code("""
from src.visualization.design_system import COLORS

# Aplicar cor de candlestick
candle_color

 = COLORS["bull"] if close > open else COLORS["bear"]
""", language="python")

st.markdown("---")

# === Footer ===
st.caption(f"Design System v1.0 | Última atualização: 04 Jan 2026")
