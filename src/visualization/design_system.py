"""
@category: production
@impact: moderate
@description: Sistema de Design Canônico - Define paleta de cores, tipografia e espaçamento para UI consistente
"""

# ============================================================================
# PALETA DE CORES - DARK TRADING THEME
# ============================================================================

COLORS = {
    # === Backgrounds ===
    "background_primary": "#0e0e0e",      # Preto profundo (fundo principal)
    "background_secondary": "#1a1a1a",    # Cinza escuro (cards, containers)
    "background_tertiary": "#2a2a2a",     # Cinza médio (hover states)
    
    # === Texto ===
    "text_primary": "#ffffff",            # Branco puro (títulos, labels principais)
    "text_secondary": "#b0b0b0",          # Cinza claro (texto descritivo)
    "text_muted": "#6b6b6b",              # Cinza médio (legendas, disabled)
    
    # === Financeiro (Candlesticks) ===
    "bull": "#26a69a",                    # Verde água (compra, candle positivo)
    "bear": "#ef5350",                    # Vermelho (venda, candle negativo)
    
    # === Status ===
    "success": "#4caf50",                 # Verde (operação bem-sucedida)
    "warning": "#ff9800",                 # Laranja (atenção, alerta)
    "error": "#f44336",                   # Vermelho (erro, falha)
    "info": "#2196f3",                    # Azul (informação neutra)
    
    # === Estrutura ===
    "grid": "#2a2a2a",                    # Linhas de grid nos gráficos
    "border": "#3a3a3a",                  # Bordas de containers
    "divider": "#1f1f1f",                 # Separadores de seção
    
    # === Accent (Features Experimentais) ===
    "accent": "#bb86fc",                  # Roxo (destaque, beta features)
    "accent_secondary": "#03dac6",        # Cyan (links, interações)
}

# ============================================================================
# TIPOGRAFIA
# ============================================================================

FONTS = {
    # Fonte primária (UI geral)
    "primary": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    
    # Fonte monospaced (números, códigos, preços)
    "monospace": "'Fira Code', 'Courier New', monospace",
}

FONT_SIZES = {
    "h1": "36px",         # ↑ Título principal do dashboard
    "h2": "28px",         # ↑ Subtítulos de seção
    "h3": "20px",         # Títulos de componentes
    "metric_large": "32px",  # NOVO: Para preços principais (Best Bid/Ask)
    "metric_small": "18px",  # NOVO: Para métricas secundárias
    "body": "15px",       # ↑ Texto padrão (melhor legibilidade)
    "caption": "13px",    # ↑ Legendas, timestamps
    "code": "14px",       # ↑ Código, números monospaced (Order Book)
}

FONT_WEIGHTS = {
    "light": 300,
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
}

# ============================================================================
# ESPAÇAMENTO (8pt Grid System)
# ============================================================================

def spacing(multiplier: int) -> int:
    """
    Retorna espaçamento baseado em múltiplos de 8px.
    
    Args:
        multiplier: Multiplicador (1 = 8px, 2 = 16px, 3 = 24px, etc.)
    
    Returns:
        int: Pixels (8 * multiplier)
    
    Examples:
        spacing(1)  # 8px
        spacing(2)  # 16px
        spacing(3)  # 24px
    """
    return 8 * multiplier

SPACING = {
    "xs": spacing(1),    # 8px  - Padding interno mínimo
    "sm": spacing(2),    # 16px - Margin entre componentes pequenos
    "md": spacing(3),    # 24px - Padding de seções
    "lg": spacing(4),    # 32px - Margin entre seções principais
    "xl": spacing(6),    # 48px - Separação de blocos grandes
}

# ============================================================================
# BORDER RADIUS
# ============================================================================

BORDER_RADIUS = {
    "sm": "4px",    # Botões, inputs pequenos
    "md": "8px",    # Cards, containers
    "lg": "12px",   # Modals, panels grandes
    "round": "50%", # Elementos circulares (badges)
}

# ============================================================================
# SHADOWS (Elevação de Componentes)
# ============================================================================

SHADOWS = {
    "none": "none",
    "sm": "0 2px 4px rgba(0, 0, 0, 0.3)",           # Hover em cards
    "md": "0 4px 8px rgba(0, 0, 0, 0.4)",           # Cards elevados
    "lg": "0 8px 16px rgba(0, 0, 0, 0.5)",          # Modals, dropdowns
    "glow_success": "0 0 12px rgba(76, 175, 80, 0.4)",  # Glow verde (sucesso)
    "glow_error": "0 0 12px rgba(244, 67, 54, 0.4)",    # Glow vermelho (erro)
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_plotly_theme():
    """
    Retorna configuração de tema para Plotly.
    
    Returns:
        dict: Layout configuration para plotly.graph_objects
    """
    return {
        "template": "plotly_dark",
        "paper_bgcolor": COLORS["background_primary"],
        "plot_bgcolor": COLORS["background_secondary"],
        "font": {
            "family": FONTS["primary"],
            "size": int(FONT_SIZES["body"].replace("px", "")),
            "color": COLORS["text_primary"]
        },
        "xaxis": {
            "gridcolor": COLORS["grid"],
            "linecolor": COLORS["border"]
        },
        "yaxis": {
            "gridcolor": COLORS["grid"],
            "linecolor": COLORS["border"]
        }
    }

def get_tradingview_theme():
    """
    Retorna configuração de tema para TradingView Lightweight Charts.
    
    Returns:
        dict: Layout options para lightweight_charts_v5
    """
    return {
        "layout": {
            "background": {"color": COLORS["background_primary"]},
            "textColor": COLORS["text_primary"]
        },
        "grid": {
            "vertLines": {"color": COLORS["grid"]},
            "horzLines": {"color": COLORS["grid"]}
        },
        "crosshair": {
            "mode": 1,  # Magnet mode
            "vertLine": {
                "color": COLORS["accent_secondary"],
                "labelBackgroundColor": COLORS["accent"]
            },
            "horzLine": {
                "color": COLORS["accent_secondary"],
                "labelBackgroundColor": COLORS["accent"]
            }
        },
        "priceScale": {
            "borderColor": COLORS["border"]
        },
        "timeScale": {
            "borderColor": COLORS["border"],
            "timeVisible": True,
            "secondsVisible": False
        }
    }

def get_streamlit_custom_css():
    """
    Retorna CSS customizado para injeção no Streamlit.
    
    Returns:
        str: CSS para aplicar via st.markdown(unsafe_allow_html=True)
    """
    return f"""
    <style>
        /* === Global Resets === */
        .block-container {{
            padding-top: {SPACING['md']}px;
            padding-bottom: {SPACING['sm']}px;
            max-width: 100%;
        }}
        
        /* === Sidebar === */
        section[data-testid="stSidebar"] {{
            background-color: {COLORS['background_secondary']};
            width: 250px !important;
        }}
        
        section[data-testid="stSidebar"] .css-1d391kg {{
            padding: {SPACING['md']}px;
        }}
        
        /* === Headers === */
        h1 {{
            font-family: {FONTS['primary']};
            font-size: {FONT_SIZES['h1']};
            font-weight: {FONT_WEIGHTS['bold']};
            color: {COLORS['text_primary']};
            margin-bottom: {SPACING['md']}px;
        }}
        
        h2 {{
            font-family: {FONTS['primary']};
            font-size: {FONT_SIZES['h2']};
            font-weight: {FONT_WEIGHTS['semibold']};
            color: {COLORS['text_primary']};
            margin-bottom: {SPACING['sm']}px;
        }}
        
        h3 {{
            font-family: {FONTS['primary']};
            font-size: {FONT_SIZES['h3']};
            font-weight: {FONT_WEIGHTS['medium']};
            color: {COLORS['text_secondary']};
            margin-bottom: {SPACING['sm']}px;
        }}
        
        /* === Body Text === */
        p, span, div {{
            font-family: {FONTS['primary']};
            font-size: {FONT_SIZES['body']};
            color: {COLORS['text_primary']};
        }}
        
        /* === Code/Monospace === */
        code {{
            font-family: {FONTS['monospace']};
            font-size: {FONT_SIZES['code']};
            background-color: {COLORS['background_tertiary']};
            padding: 2px 6px;
            border-radius: {BORDER_RADIUS['sm']};
        }}
        
        /* === Buttons === */
        .stButton > button {{
            background-color: {COLORS['accent']};
            color: {COLORS['text_primary']};
            border: none;
            border-radius: {BORDER_RADIUS['sm']};
            padding: {SPACING['xs']}px {SPACING['sm']}px;
            font-family: {FONTS['primary']};
            font-weight: {FONT_WEIGHTS['medium']};
            transition: all 0.2s ease;
        }}
        
        .stButton > button:hover {{
            background-color: {COLORS['accent_secondary']};
            box-shadow: {SHADOWS['sm']};
            transform: translateY(-2px);
        }}
        
        /* === Metrics Cards === */
        [data-testid="stMetricValue"] {{
            font-family: {FONTS['monospace']};
            font-size: {FONT_SIZES['h2']};
            font-weight: {FONT_WEIGHTS['bold']};
        }}
        
        /* === Dividers === */
        hr {{
            border-color: {COLORS['divider']};
            margin: {SPACING['md']}px 0;
        }}
    </style>
    """

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "COLORS",
    "FONTS",
    "FONT_SIZES",
    "FONT_WEIGHTS",
    "SPACING",
    "BORDER_RADIUS",
    "SHADOWS",
    "spacing",
    "get_plotly_theme",
    "get_tradingview_theme",
    "get_streamlit_custom_css"
]
