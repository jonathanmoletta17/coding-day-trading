"""
@category: production
@impact: low
@description: Metric Card Component - Card de métrica estilizado seguindo o design system
"""
import streamlit as st
from src.visualization.design_system import COLORS, SPACING, BORDER_RADIUS, SHADOWS, FONT_SIZES

def render_metric_card(
    label: str,
    value: str,
    delta: str = None,
    delta_color: str = "neutral",
    icon: str = None
):
    """
    Renderiza um card de métrica customizado com estilo do design system.
    
    Args:
        label: Título da métrica (ex: "Best Bid", "Volume 24h")
        value: Valor principal (ex: "91728.19", "1.2M BTC")
        delta: Variação opcional (ex: "+0.5%", "-2.3%")
        delta_color: Cor do delta - "success" | "error" | "neutral"
        icon: Emoji ou ícone opcional (ex: "📈", "💰")
    
    Example:
        >>> render_metric_card(
        ...     label="Best Bid",
        ...     value="91728.19",
        ...     delta="+0.02%",
        ...     delta_color="success",
        ...     icon="💰"
        ... )
    """
    # Mapeia delta_color para cores do design system
    color_map = {
        "success": COLORS["success"],
        "error": COLORS["error"],
        "neutral": COLORS["text_secondary"],
        "bull": COLORS["bull"],
        "bear": COLORS["bear"]
    }
    
    delta_display_color = color_map.get(delta_color, COLORS["text_secondary"])
    
    # Determina cor da borda lateral baseada no delta
    border_color = COLORS["accent"]
    if delta_color == "success" or delta_color == "bull":
        border_color = COLORS["bull"]
    elif delta_color == "error" or delta_color == "bear":
        border_color = COLORS["bear"]
    
    # Constrói HTML do card
    icon_html = f'<span style="font-size: 24px; margin-right: 8px;">{icon}</span>' if icon else ''
    delta_html = f'''
        <p style="
            color: {delta_display_color};
            font-size: {FONT_SIZES['caption']};
            font-weight: 600;
            margin: 4px 0 0 0;
        ">
            {delta}
        </p>
    ''' if delta else ''
    
    card_html = f'''
    <div style="
        background: {COLORS['background_secondary']};
        padding: {SPACING['sm']}px;
        border-radius: {BORDER_RADIUS['md']};
        border-left: 4px solid {border_color};
        box-shadow: {SHADOWS['sm']};
        transition: all 0.2s ease;
        cursor: default;
    " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='{SHADOWS['md']}';" 
       onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='{SHADOWS['sm']}';">
        <div style="display: flex; align-items: center; margin-bottom: 4px;">
            {icon_html}
            <p style="
                color: {COLORS['text_secondary']};
                font-size: {FONT_SIZES['caption']};
                margin: 0;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            ">
                {label}
            </p>
        </div>
        <h2 style="
            color: {COLORS['text_primary']};
            font-size: {FONT_SIZES['metric_large']};
            font-weight: 700;
            margin: 8px 0;
            font-family: 'Fira Code', monospace;
            text-shadow: 0 0 10px {border_color}40;
        ">
            {value}
        </h2>
        {delta_html}
    </div>
    '''
    
    st.markdown(card_html, unsafe_allow_html=True)

def render_metric_row(metrics: list):
    """
    Renderiza uma linha de múltiplos metric cards em colunas.
    
    Args:
        metrics: Lista de dicts com configurações de cada métrica
                 Cada dict deve ter: {label, value, delta?, delta_color?, icon?}
    
    Example:
        >>> render_metric_row([
        ...     {"label": "Best Bid", "value": "91728.19", "delta": "+0.02%", "delta_color": "success"},
        ...     {"label": "Best Ask", "value": "91728.20", "delta": "-0.01%", "delta_color": "error"},
        ...     {"label": "Spread", "value": "0.01"}
        ... ])
    """
    cols = st.columns(len(metrics))
    
    for i, metric in enumerate(metrics):
        with cols[i]:
            render_metric_card(
                label=metric.get("label", ""),
                value=metric.get("value", ""),
                delta=metric.get("delta"),
                delta_color=metric.get("delta_color", "neutral"),
                icon=metric.get("icon")
            )
