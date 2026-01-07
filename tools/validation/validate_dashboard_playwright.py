"""
@category: tool
@impact: low
@description: Teste automatizado da UI do dashboard
"""

from streamlit.testing.v1 import AppTest


def validate_dashboard():
    at = AppTest.from_file("src/visualization/dashboard.py").run()

    titles = [t.value for t in at.title]
    assert "Day Trading Dashboard" in titles

    assert at.sidebar.radio
    mode_radio = at.sidebar.radio[0]
    assert "Crypto (Binance)" in mode_radio.options

    # Custom metrics are rendered via markdown
    markdown_content = " ".join([m.value for m in at.markdown])
    assert "Best Bid" in markdown_content
    assert "Best Ask" in markdown_content
    assert "Spread" in markdown_content

    assert len(at.dataframe) >= 1

    assert at.sidebar.button
    button_labels = [b.label for b in at.sidebar.button]
    assert "📊 Order Book" in button_labels
    assert "⏹️ Stop OB" in button_labels

if __name__ == "__main__":
    validate_dashboard()
