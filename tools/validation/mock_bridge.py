"""
@category: tool
@impact: low
@description: Mock do MT5 Bridge Service para validação visual do Dashboard em ambiente Linux
"""
from fastapi import FastAPI
import uvicorn
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

app = FastAPI()

@app.get("/candles/{symbol}")
def get_candles(symbol: str, timeframe: str = "H1", count: int = 100):
    # Gera dados sintéticos (Simulando Bridge API)
    dates = [datetime.now() - timedelta(hours=i) for i in range(count)]
    dates.reverse()
    
    # Random walk simulation
    price = 1.1000
    data = []
    for d in dates:
        change = np.random.normal(0, 0.001)
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.0005))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.0005))
        price = close_p
        
        data.append({
            "time": d.isoformat(),
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "tick_volume": int(np.random.randint(100, 1000)),
            "spread": 10,
            "real_volume": 0
        })
    
    return data

@app.get("/tick/{symbol}")
def get_tick(symbol: str):
    return {
        "symbol": symbol,
        "time": datetime.now().isoformat(),
        "bid": 1.1000,
        "ask": 1.1001,
        "last": 1.1000,
        "volume": 100,
        "flags": 0
    }

@app.get("/health")
def health():
    return {"status": "healthy", "mt5_connected": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
