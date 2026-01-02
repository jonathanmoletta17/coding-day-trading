"""
MT5 Bridge Service - API Gateway para acesso ao MetaTrader 5
Roda no Windows e expõe API REST/WebSocket para acesso do WSL/Linux

Endpoints:
- GET /health - Health check
- GET /account - Informações da conta
- GET /symbols - Lista símbolos disponíveis
- GET /tick/{symbol} - Último tick de um símbolo
- GET /candles/{symbol} - OHLCV histórico
- WebSocket /ws/ticks - Stream de ticks em tempo real
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import MetaTrader5 as mt5
import uvicorn
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
import json
from pydantic import BaseModel
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configuração da aplicação
app = FastAPI(
    title="MT5 Bridge API",
    description="Gateway para acesso ao MetaTrader 5 via REST/WebSocket",
    version="1.0.0"
)

# CORS para permitir acesso do WSL
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# MODELS
# =============================================================================

class AccountInfo(BaseModel):
    login: int
    server: str
    name: str
    currency: str
    leverage: int
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    profit: float

class SymbolInfo(BaseModel):
    symbol: str
    description: str
    base_currency: str
    profit_currency: str
    digits: int
    point: float
    spread: int
    trade_contract_size: float
    min_lot: float
    max_lot: float
    lot_step: float

class Tick(BaseModel):
    symbol: str
    time: datetime
    bid: float
    ask: float
    last: float
    volume: int
    flags: int

class Candle(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

# =============================================================================
# MT5 CONNECTION
# =============================================================================

def initialize_mt5():
    """Inicializa conexão com MT5"""
    mt5_path = os.getenv("MT5_PATH")
    mt5_login = os.getenv("MT5_LOGIN")
    mt5_password = os.getenv("MT5_PASSWORD")
    mt5_server = os.getenv("MT5_SERVER")
    
    init_kwargs = {}
    if mt5_path:
        init_kwargs['path'] = mt5_path
    
    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        raise RuntimeError(f"Falha ao inicializar MT5: {error}")
    
    # Login se credenciais fornecidas
    if mt5_login and mt5_password and mt5_server:
        if not mt5.login(int(mt5_login), password=mt5_password, server=mt5_server):
            error = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"Falha no login MT5: {error}")
    
    print("[✓] MT5 inicializado e conectado")
    return True

@app.on_event("startup")
async def startup_event():
    """Inicializa MT5 quando API inicia"""
    try:
        initialize_mt5()
    except Exception as e:
        print(f"[✗] Erro na inicialização: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Finaliza MT5 quando API termina"""
    mt5.shutdown()
    print("[ ] MT5 desconectado")

# =============================================================================
# ENDPOINTS REST
# =============================================================================

@app.get("/")
async def root():
    """Endpoint raiz com informações da API"""
    return {
        "service": "MT5 Bridge API",
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "account": "/account",
            "symbols": "/symbols",
            "tick": "/tick/{symbol}",
            "candles": "/candles/{symbol}",
            "websocket": "/ws/ticks"
        }
    }

@app.get("/health")
async def health_check():
    """Health check - verifica se MT5 está conectado"""
    terminal_info = mt5.terminal_info()
    account_info = mt5.account_info()
    
    if terminal_info is None or account_info is None:
        raise HTTPException(status_code=503, detail="MT5 não está conectado")
    
    return {
        "status": "healthy",
        "mt5_connected": terminal_info.connected,
        "terminal_build": terminal_info.build,
        "account_login": account_info.login,
        "server": account_info.server
    }

@app.get("/account", response_model=AccountInfo)
async def get_account_info():
    """Retorna informações da conta MT5"""
    account = mt5.account_info()
    
    if account is None:
        raise HTTPException(status_code=500, detail="Falha ao obter informações da conta")
    
    return AccountInfo(
        login=account.login,
        server=account.server,
        name=account.name,
        currency=account.currency,
        leverage=account.leverage,
        balance=account.balance,
        equity=account.equity,
        margin=account.margin,
        margin_free=account.margin_free,
        margin_level=account.margin_level if account.margin > 0 else 0,
        profit=account.profit
    )

@app.get("/symbols", response_model=List[str])
async def get_symbols(visible_only: bool = False):
    """Lista todos os símbolos disponíveis"""
    if visible_only:
        symbols = mt5.symbols_get()
        if symbols is None:
            raise HTTPException(status_code=500, detail="Falha ao obter símbolos")
        return [s.name for s in symbols if s.visible]
    else:
        total = mt5.symbols_total()
        symbols = mt5.symbols_get()
        if symbols is None:
            return []
        return [s.name for s in symbols]

@app.get("/symbol/{symbol}", response_model=SymbolInfo)
async def get_symbol_info(symbol: str):
    """Retorna informações detalhadas de um símbolo"""
    info = mt5.symbol_info(symbol)
    
    if info is None:
        raise HTTPException(status_code=404, detail=f"Símbolo '{symbol}' não encontrado")
    
    return SymbolInfo(
        symbol=info.name,
        description=info.description,
        base_currency=info.currency_base,
        profit_currency=info.currency_profit,
        digits=info.digits,
        point=info.point,
        spread=info.spread,
        trade_contract_size=info.trade_contract_size,
        min_lot=info.volume_min,
        max_lot=info.volume_max,
        lot_step=info.volume_step
    )

@app.get("/tick/{symbol}", response_model=Tick)
async def get_tick(symbol: str):
    """Retorna o último tick de um símbolo"""
    tick = mt5.symbol_info_tick(symbol)
    
    if tick is None:
        raise HTTPException(status_code=404, detail=f"Não foi possível obter tick de '{symbol}'")
    
    return Tick(
        symbol=symbol,
        time=datetime.fromtimestamp(tick.time),
        bid=tick.bid,
        ask=tick.ask,
        last=tick.last,
        volume=tick.volume,
        flags=tick.flags
    )

@app.get("/candles/{symbol}", response_model=List[Candle])
async def get_candles(
    symbol: str,
    timeframe: str = "H1",
    count: int = Query(default=100, le=50000),
    from_date: Optional[str] = None
):
    """
    Retorna candles (OHLCV) de um símbolo
    
    Timeframes disponíveis: M1, M5, M15, M30, H1, H4, D1, W1, MN1
    """
    # Mapeia timeframe string para constante MT5
    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }
    
    tf = timeframe_map.get(timeframe.upper())
    if tf is None:
        raise HTTPException(status_code=400, detail=f"Timeframe inválido: {timeframe}")
    
    # Obtém candles
    if from_date:
        from_dt = datetime.fromisoformat(from_date)
        rates = mt5.copy_rates_from(symbol, tf, from_dt, count)
    else:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=404, detail=f"Não foi possível obter candles de '{symbol}'")
    
    return [
        Candle(
            time=datetime.fromtimestamp(r['time']),
            open=r['open'],
            high=r['high'],
            low=r['low'],
            close=r['close'],
            tick_volume=r['tick_volume'],
            spread=r['spread'],
            real_volume=r['real_volume']
        )
        for r in rates
    ]

# =============================================================================
# WEBSOCKET ENDPOINTS (Streaming de dados)
# =============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscriptions: dict = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    def subscribe(self, websocket: WebSocket, symbol: str):
        if websocket not in self.subscriptions:
            self.subscriptions[websocket] = set()
        self.subscriptions[websocket].add(symbol)

    def unsubscribe(self, websocket: WebSocket, symbol: str):
        if websocket in self.subscriptions:
            self.subscriptions[websocket].discard(symbol)

manager = ConnectionManager()

@app.websocket("/ws/ticks")
async def websocket_ticks(websocket: WebSocket):
    """WebSocket para streaming de ticks em tempo real"""
    await manager.connect(websocket)
    subscribed_symbols = set()
    
    try:
        # Loop principal de streaming
        while True:
            # Recebe mensagens do cliente (subscrições)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                message = json.loads(data)
                
                if message.get('action') == 'subscribe':
                    symbol = message.get('symbol')
                    if symbol:
                        subscribed_symbols.add(symbol)
                        await websocket.send_json({
                            "type": "subscribed",
                            "symbol": symbol,
                            "timestamp": datetime.now().isoformat()
                        })
                
                elif message.get('action') == 'unsubscribe':
                    symbol = message.get('symbol')
                    if symbol:
                        subscribed_symbols.discard(symbol)
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "symbol": symbol,
                            "timestamp": datetime.now().isoformat()
                        })
            
            except asyncio.TimeoutError:
                pass  # Sem mensagens do cliente
            
            # Envia ticks dos símbolos subscritos
            for symbol in subscribed_symbols:
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    await websocket.send_json({
                        "type": "tick",
                        "symbol": symbol,
                        "time": datetime.fromtimestamp(tick.time).isoformat(),
                        "bid": tick.bid,
                        "ask": tick.ask,
                        "last": tick.last,
                        "volume": tick.volume,
                        "spread": tick.ask - tick.bid
                    })
            
            await asyncio.sleep(0.1)  # 10 updates/segundo
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Erro no WebSocket: {e}")
        manager.disconnect(websocket)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MT5 BRIDGE API - Starting...")
    print("=" * 70)
    
    uvicorn.run(
        app,
        host="0.0.0.0",  # Permite acesso do WSL
        port=8000,
        log_level="info"
    )
