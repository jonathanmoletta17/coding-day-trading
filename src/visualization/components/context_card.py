"""
@category: production
@impact: low
@description: Componente de card visual para exibir contexto DSL com destaque e hierarquia visual
"""
import streamlit as st
from src.visualization.design_system import COLORS, SPACING, BORDER_RADIUS, FONT_SIZES

def render_context_card(stability: str, liquidity: str, activity: str, do_not_operate: bool):
    """
    Renderiza card visual melhorado para Contexto DSL v0.1.
    
    Args:
        stability: Nível de estabilidade (HIGH, MEDIUM, LOW)
        liquidity: Nível de liquidez
        activity: Nível de atividade
        do_not_operate: Flag de veto operacional
    """
    card_color = COLORS["error"] if do_not_operate else COLORS["success"]
    veto_status = "🚫 VETO ATIVO" if do_not_operate else "✅ OK"
    
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {COLORS['background_secondary']} 0%, {COLORS['background_tertiary']} 100%);
        border-left: 4px solid {card_color};
        padding: {SPACING['md']}px;
        border-radius: {BORDER_RADIUS['md']};
        margin-bottom: {SPACING['sm']}px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: {SPACING['sm']}px;">
            <h3 style="margin:0; color:{COLORS['text_primary']}; font-size:{FONT_SIZES['h3']};">
                Market Context (DSL v0.1)
            </h3>
            <span style="
                color: {card_color};
                font-weight: 700;
                font-size: {FONT_SIZES['body']};
                padding: 4px 12px;
                background: {card_color}20;
                border-radius: {BORDER_RADIUS['sm']};
            ">
                {veto_status}
            </span>
        </div>
        
        <div style="
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: {SPACING['md']}px;
            margin-top: {SPACING['md']}px;
        ">
            <div>
                <span style="
                    color: {COLORS['text_muted']};
                    font-size: {FONT_SIZES['caption']};
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                ">Stability</span>
                <p style="
                    font-size: {FONT_SIZES['metric_small']};
                    margin: 4px 0 0 0;
                    font-weight: 700;
                    color: {COLORS['accent']};
                ">{stability}</p>
            </div>
            <div>
                <span style="
                    color: {COLORS['text_muted']};
                    font-size: {FONT_SIZES['caption']};
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                ">Liquidity</span>
                <p style="
                    font-size: {FONT_SIZES['metric_small']};
                    margin: 4px 0 0 0;
                    font-weight: 700;
                    color: {COLORS['accent']};
                ">{liquidity}</p>
            </div>
            <div>
                <span style="
                    color: {COLORS['text_muted']};
                    font-size: {FONT_SIZES['caption']};
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                ">Activity</span>
                <p style="
                    font-size: {FONT_SIZES['metric_small']};
                    margin: 4px 0 0 0;
                    font-weight: 700;
                    color: {COLORS['accent']};
                ">{activity}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
