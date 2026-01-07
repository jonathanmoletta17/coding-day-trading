"""
@category: production
@impact: low
@description: Componente de indicador LIVE streaming com animação pulsante
"""
import streamlit as st
from src.visualization.design_system import COLORS, BORDER_RADIUS

def render_live_indicator(is_streaming: bool = True, label: str = "LIVE Streaming"):
    """
    Renderiza indicador de streaming ao vivo com animação pulsante.
    
    Args:
        is_streaming: Se está transmitindo ao vivo
        label: Texto do indicador
    """
    if is_streaming:
        color = COLORS["error"]  # Vermelho para "LIVE"
        bg_color = COLORS["success"]
        status_text = label
    else:
        color = COLORS["text_muted"]
        bg_color = COLORS["background_tertiary"]
        status_text = "⏸️ Offline"
    
    st.markdown(f"""
    <div style="
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 16px;
        background: {bg_color}15;
        border-radius: {BORDER_RADIUS['md']};
        margin-bottom: 16px;
        border: 1px solid {bg_color}40;
        animation: {'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' if is_streaming else 'none'};
    ">
        <span style="
            width: 12px;
            height: 12px;
            background: {color};
            border-radius: 50%;
            box-shadow: 0 0 8px {color}, 0 0 16px {color}80;
            animation: {'glow 1.5s ease-in-out infinite' if is_streaming else 'none'};
        "></span>
        <strong style="
            color: {color if is_streaming else COLORS['text_muted']};
            font-size: 14px;
            letter-spacing: 0.5px;
        ">{status_text}</strong>
    </div>
    
    <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        
        @keyframes glow {{
            0%, 100% {{ 
                box-shadow: 0 0 8px {color}, 0 0 16px {color}80;
            }}
            50% {{ 
                box-shadow: 0 0 12px {color}, 0 0 24px {color};
            }}
        }}
    </style>
    """, unsafe_allow_html=True)
