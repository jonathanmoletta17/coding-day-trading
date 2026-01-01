from streamlit.testing.v1 import AppTest


def validate_dashboard():
    at = AppTest.from_file("src/visualization/dashboard.py").run()

    titles = [t.value for t in at.title]
    assert "Day Trading Dashboard" in titles

    assert at.sidebar.radio
    mode_radio = at.sidebar.radio[0]
    assert "Crypto (Binance)" in mode_radio.options

    assert len(at.metric) == 3
    assert at.dataframe

    assert at.sidebar.button
    button_labels = [b.label for b in at.sidebar.button]
    assert "▶️ Iniciar Stream" in button_labels
    assert "⏹️ Parar Stream" in button_labels

if __name__ == "__main__":
    validate_dashboard()
