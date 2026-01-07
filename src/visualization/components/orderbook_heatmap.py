"""
@category: production
@impact: low
@description: Componente de Order Book com heatmap visual usando gradientes de cores
"""
import streamlit as st
from src.visualization.design_system import COLORS, FONTS, FONT_SIZES

def render_orderbook_heatmap(bids: list, asks: list, top_n: int = 10):
    """
    Renderiza Order Book com heatmap de intensidade em background.
    
    Args:
        bids: Lista de bids [(price, volume), ...]
        asks: Lista de asks [(price, volume), ...]
        top_n: Número de níveis a exibir
    """
    if len(bids) == 0 or len(asks) == 0:
        st.warning("Order Book vazio")
        return
    
    top_n = min(top_n, len(bids), len(asks))
    
    # Calcular intensidades
    bid_volumes = [float(b[1]) for b in bids[:top_n]]
    ask_volumes = [float(a[1]) for a in asks[:top_n]]
    
    max_bid_vol = max(bid_volumes) if bid_volumes else 1
    max_ask_vol = max(ask_volumes) if ask_volumes else 1
    
    html = f"""
    <div style="
        font-family: {FONTS['monospace']};
        font-size: {FONT_SIZES['code']};
        overflow-y: auto;
        max-height: 400px;
    ">
        <table style="width: 100%; border-collapse: collapse;">
            <thead style="position: sticky; top: 0; background: {COLORS['background_secondary']}; z-index: 1;">
                <tr style="color: {COLORS['text_muted']}; text-transform: uppercase; font-size: {FONT_SIZES['caption']};">
                    <th style="padding: 8px; text-align: right;">Bid Price</th>
                    <th style="padding: 8px; text-align: left;">Bid Vol</th>
                    <th style="padding: 8px; text-align: right;">Ask Price</th>
                    <th style="padding: 8px; text-align: left;">Ask Vol</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for i in range(top_n):
        bid_price = float(bids[i][0])
        bid_vol = float(bids[i][1])
        ask_price = float(asks[i][0])
        ask_vol = float(asks[i][1])
        
        bid_intensity = (bid_vol / max_bid_vol) * 100
        ask_intensity = (ask_vol / max_ask_vol) * 100
        
        html += f"""
        <tr style="border-bottom: 1px solid {COLORS['divider']};">
            <td style="
                background: linear-gradient(90deg, transparent {100-bid_intensity}%, {COLORS['bull']}25 100%);
                padding: 8px 12px;
                text-align: right;
                color: {COLORS['bull']};
                font-weight: 600;
            ">{bid_price:.2f}</td>
            <td style="
                padding: 8px 12px;
                text-align: left;
                color: {COLORS['text_secondary']};
            ">{bid_vol:.4f}</td>
            <td style="
                background: linear-gradient(90deg, {COLORS['bear']}25 0%, transparent {ask_intensity}%);
                padding: 8px 12px;
                text-align: right;
                color: {COLORS['bear']};
                font-weight: 600;
            ">{ask_price:.2f}</td>
            <td style="
                padding: 8px 12px;
                text-align: left;
                color: {COLORS['text_secondary']};
            ">{ask_vol:.4f}</td>
        </tr>
        """
    
    html += """
            </tbody>
        </table>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)
