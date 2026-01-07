"""
@category: experiment
@impact: none
@description: Protótipo standalone de trading bot com IA local (Ollama) e MT5
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Optional
import threading
import logging
import sys
import io
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
# Carrega variáveis de ambiente
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(project_root, ".env"))

# Força encoding UTF-8 no console Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Setup de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# CONFIGURAÇÃO DO SISTEMA
# ============================================================================

class TradingConfig:
    """Configurações do sistema de trading"""
    
    # ===== MODELO DE IA LOCAL =====
    OLLAMA_MODEL = "qwen2.5:14b"
    OLLAMA_URL = "http://localhost:11434/api/generate"
    
    # ===== CONFIGURAÇÕES DE RISCO =====
    MAX_RISK_PER_TRADE = 0.01  # 1% do capital por operação
    MAX_DAILY_LOSS = 0.03  # 3% do capital por dia
    MAX_POSITIONS = 3  # Máximo de posições simultâneas
    
    # ===== STOP LOSS E TAKE PROFIT =====
    DEFAULT_STOP_LOSS = 0.015  # 1.5%
    DEFAULT_TAKE_PROFIT = 0.03  # 3%
    
    # ===== ATIVOS PARA OPERAR =====
    # Nota: No MT5 Demo, os sufixos podem variar (ex: PETR4, PETR4F, PETR4.SA)
    ASSETS = {
        'PETR4': {'min_volume': 100, 'spread_max': 0.05},
        'VALE3': {'min_volume': 100, 'spread_max': 0.05},
        'ITUB4': {'min_volume': 100, 'spread_max': 0.05},
        'BBDC4': {'min_volume': 100, 'spread_max': 0.05},
        'WEGE3': {'min_volume': 100, 'spread_max': 0.05},
    }
    
    # ===== DATABASE =====
    DB_HOST = os.getenv("POSTGRES_HOST")
    DB_PORT = os.getenv("POSTGRES_PORT")
    DB_NAME = os.getenv("POSTGRES_DB")
    DB_USER = os.getenv("POSTGRES_USER")
    DB_PASS = os.getenv("POSTGRES_PASSWORD")

    # ===== MT5 =====
    MT5_LOGIN = int(os.getenv("MT5_LOGIN", 0))
    MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER = os.getenv("MT5_SERVER", "")
    MT5_PATH = os.getenv("MT5_PATH", "")

config = TradingConfig()

# ============================================================================
# MÓDULO 0: DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Gerencia conexão com Postgres"""
    def __init__(self):
        try:
            import psycopg2
            self.conn = psycopg2.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASS
            )
            self._init_db()
            logging.info("✓ Database conectado")
        except Exception as e:
            logging.error(f"❌ Erro no Database: {e}")
            self.conn = None

    def _init_db(self):
        """Cria tabelas se não existirem"""
        if not self.conn: return
        query = """
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            action VARCHAR(10),
            price DECIMAL,
            quantity INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            profit DECIMAL,
            strategy VARCHAR(50)
        );
        """
        with self.conn.cursor() as cur:
            cur.execute(query)
            self.conn.commit()

    def log_trade(self, symbol, action, price, quantity, profit=0):
        """Salva trade no banco"""
        if not self.conn: return
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO trades (symbol, action, price, quantity, profit) VALUES (%s, %s, %s, %s, %s)",
                    (symbol, action, float(price), int(quantity), float(profit))
                )
                self.conn.commit()
        except Exception as e:
            logging.error(f"Erro ao salvar trade: {e}")

# ============================================================================
# MÓDULO 1: ANÁLISE COM IA LOCAL
# ============================================================================

class AIAnalyzer:
    """Analisador de mercado usando LLM local (Ollama)"""
    def __init__(self):
        self.model = config.OLLAMA_MODEL
        self.url = config.OLLAMA_URL
    
    def analyze_opportunity(self, asset_data: dict) -> dict:
        prompt = f"""
Você é um trader especialista. Analise:
ATIVO: {asset_data['symbol']} PRICE: {asset_data['price']} CHANGE: {asset_data['change_pct']}%
DECISÃO JSON (should_trade: bool, action: BUY/SELL/HOLD, confidence: 0-100):
"""
        try:
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 100, "temperature": 0.1}
                },
                timeout=20
            )
            if response.status_code == 200:
                text = response.json().get('response', '')
                if '{' in text:
                    json_str = text[text.find('{'):text.rfind('}')+1]
                    return json.loads(json_str)
        except Exception as e:
            logging.error(f"IA Error: {e}")
        
        return {'should_trade': False, 'action': 'HOLD', 'confidence': 0}

# ============================================================================
# MÓDULO 2 e 3: GESTOR DE RISCO e EXECUTOR MT5
# ============================================================================

class TradingBot:
    """Sistema principal"""
    
    def __init__(self, mode='SIMULATION'):
        self.mode = mode
        self.ai = AIAnalyzer()
        self.db = DatabaseManager()
        self.running = False
        
        # Inicializa MT5 se produção
        if self.mode == 'PRODUCTION':
            self._init_mt5()
        
        self.positions = {}

    def _init_mt5(self):
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            
            if not mt5.initialize(path=config.MT5_PATH):
                logging.error(f"MT5 Init falhou: {mt5.last_error()}")
                sys.exit(1)
                
            logging.info(f"✓ MT5 Inicializado: {mt5.version()}")
            
            # Login
            authorized = mt5.login(
                login=config.MT5_LOGIN, 
                password=config.MT5_PASSWORD, 
                server=config.MT5_SERVER
            )
            
            if authorized:
                logging.info(f"✓ MT5 Logado: {config.MT5_LOGIN}")
            else:
                logging.error(f"❌ MT5 Login falhou: {mt5.last_error()}")
                sys.exit(1)
                
        except ImportError:
            logging.error("❌ Biblioteca MetaTrader5 não instalada")
            sys.exit(1)

    def get_market_data(self, symbol):
        if self.mode == 'PRODUCTION':
            # Dados reais do MT5
            tick = self.mt5.symbol_info_tick(symbol)
            if tick is None:
                # Tenta adicionar ativo se nao visivel
                self.mt5.symbol_select(symbol, True)
                tick = self.mt5.symbol_info_tick(symbol)
            
            if tick:
                rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_D1, 0, 1)
                change = 0
                if rates is not None and len(rates) > 0:
                    open_price = rates[0]['open']
                    change = ((tick.last - open_price) / open_price) * 100
                    
                return {
                    'symbol': symbol,
                    'price': tick.last,
                    'bid': tick.bid,
                    'ask': tick.ask,
                    'change_pct': change,
                    'volume': tick.volume_real
                }
            return None
        else:
            # Simulação
            return {
                'symbol': symbol,
                'price': 100.0,
                'change_pct': 0.5,
                'volume': 1000000
            }

    def execute_trade(self, symbol, action, quantity, price):
        logging.info(f"🚀 ORDEM: {action} {quantity} {symbol} @ {price}")
        
        if self.mode == 'PRODUCTION':
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(quantity),
                "type": self.mt5.ORDER_TYPE_BUY if action == 'BUY' else self.mt5.ORDER_TYPE_SELL,
                "price": price,
                "deviation": 20,
                "magic": 234000,
                "comment": "IA Bot",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_RETURN,
            }
            
            result = self.mt5.order_send(request)
            
            if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                logging.error(f"❌ Erro MT5: {result.comment}")
            else:
                logging.info(f"✅ Ordem Executada: {result.order}")
                self.db.log_trade(symbol, action, price, quantity)
        else:
            logging.info("✅ Trade Simulado")
            self.db.log_trade(symbol, action, price, quantity)

    def run(self, duration_minutes=5):
        logging.info(f"🤖 BOT INICIADO ({self.mode})")
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        while datetime.now() < end_time:
            for symbol in config.ASSETS:
                data = self.get_market_data(symbol)
                if not data:
                    logging.warning(f"Sem dados para {symbol}")
                    continue
                
                # Análise IA (Simplificada para teste E2E)
                # Em produção real, você usaria self.ai.analyze_opportunity(data)
                # Para este teste, vamos forçar uma execução se o preço for > 0
                
                # Vamos tentar comprar 100 açoes se nao tiver posição
                # (Lógica simplificada para validação de infraestrutura)
                
                logging.info(f"Analisando {symbol}: R$ {data['price']:.2f}")
                
                # Teste IA
                analysis = self.ai.analyze_opportunity(data)
                if analysis.get('should_trade'):
                     self.execute_trade(symbol, analysis['action'], 100, data['ask' if analysis['action'] == 'BUY' else 'bid'])
                
            time.sleep(10)
            
        if self.mode == 'PRODUCTION':
            self.mt5.shutdown()
        logging.info("🤖 BOT FINALIZADO")

if __name__ == "__main__":
    # Modo padrão PRODUCTION para teste E2E pois o usuário pediu "teste ponta a ponta"
    bot = TradingBot(mode='PRODUCTION')
    bot.run(duration_minutes=2)
