-- Schema para armazenamento de dados do MetaTrader 5
-- Database: market_data

-- =============================================================================
-- 1. TABELA DE SÍMBOLOS (Instrumentos Financeiros)
-- =============================================================================
CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    base_currency VARCHAR(10),
    quote_currency VARCHAR(10),
    digits INT,
    point DOUBLE PRECISION,
    trade_contract_size DOUBLE PRECISION,
    min_lot DOUBLE PRECISION,
    max_lot DOUBLE PRECISION,
    lot_step DOUBLE PRECISION,
    exchange VARCHAR(100),
    sector VARCHAR(100),
    industry VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_symbols_symbol ON symbols(symbol);
CREATE INDEX idx_symbols_exchange ON symbols(exchange);

-- =============================================================================
-- 2. TABELA DE TICKS (Dados em Tempo Real)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ticks (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    time TIMESTAMP NOT NULL,
    bid DOUBLE PRECISION NOT NULL,
    ask DOUBLE PRECISION NOT NULL,
    last DOUBLE PRECISION,
    volume BIGINT,
    flags INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para performance
CREATE INDEX idx_ticks_symbol_time ON ticks(symbol_id, time DESC);
CREATE INDEX idx_ticks_time ON ticks(time DESC);

-- Particionamento por tempo (otimização para grandes volumes)
-- CREATE TABLE ticks_2026_01 PARTITION OF ticks FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- =============================================================================
-- 3. TABELA DE CANDLES/BARRAS (OHLCV)
-- =============================================================================
CREATE TABLE IF NOT EXISTS candles (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    timeframe VARCHAR(10) NOT NULL, -- M1, M5, M15, M30, H1, H4, D1, W1, MN1
    time TIMESTAMP NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    tick_volume BIGINT NOT NULL,
    spread INT,
    real_volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol_id, timeframe, time)
);

-- Índices para queries rápidas
CREATE INDEX idx_candles_symbol_tf_time ON candles(symbol_id, timeframe, time DESC);
CREATE INDEX idx_candles_time ON candles(time DESC);
CREATE INDEX idx_candles_symbol_tf ON candles(symbol_id, timeframe);

-- =============================================================================
-- 4. TABELA DE ORDENS (Orders)
-- =============================================================================
CREATE TABLE IF NOT EXISTS orders (
    ticket BIGINT PRIMARY KEY,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    type INT NOT NULL, -- 0=BUY, 1=SELL, etc
    state INT NOT NULL,
    magic BIGINT,
    time_setup TIMESTAMP NOT NULL,
    time_done TIMESTAMP,
    time_expiration TIMESTAMP,
    volume_initial DOUBLE PRECISION,
    volume_current DOUBLE PRECISION,
    price_open DOUBLE PRECISION,
    price_current DOUBLE PRECISION,
    price_stoploss DOUBLE PRECISION,
    price_takeprofit DOUBLE PRECISION,
    comment TEXT,
    external_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_symbol ON orders(symbol_id);
CREATE INDEX idx_orders_time_setup ON orders(time_setup DESC);
CREATE INDEX idx_orders_magic ON orders(magic);

-- =============================================================================
-- 5. TABELA DE POSIÇÕES (Positions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS positions (
    ticket BIGINT PRIMARY KEY,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    type INT NOT NULL, -- 0=BUY, 1=SELL
    magic BIGINT,
    time_create TIMESTAMP NOT NULL,
    time_update TIMESTAMP,
    volume DOUBLE PRECISION NOT NULL,
    price_open DOUBLE PRECISION NOT NULL,
    price_current DOUBLE PRECISION,
    swap DOUBLE PRECISION,
    profit DOUBLE PRECISION,
    stoploss DOUBLE PRECISION,
    takeprofit DOUBLE PRECISION,
    comment TEXT,
    external_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_positions_symbol ON positions(symbol_id);
CREATE INDEX idx_positions_time_create ON positions(time_create DESC);
CREATE INDEX idx_positions_magic ON positions(magic);

-- =============================================================================
-- 6. TABELA DE DEALS (Histórico de Negociações)
-- =============================================================================
CREATE TABLE IF NOT EXISTS deals (
    ticket BIGINT PRIMARY KEY,
    order_ticket BIGINT,
    position_ticket BIGINT,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    type INT NOT NULL,
    entry INT NOT NULL, -- 0=IN, 1=OUT, 2=INOUT
    magic BIGINT,
    time TIMESTAMP NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    commission DOUBLE PRECISION,
    swap DOUBLE PRECISION,
    profit DOUBLE PRECISION,
    fee DOUBLE PRECISION,
    comment TEXT,
    external_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deals_symbol ON deals(symbol_id);
CREATE INDEX idx_deals_time ON deals(time DESC);
CREATE INDEX idx_deals_position ON deals(position_ticket);
CREATE INDEX idx_deals_order ON deals(order_ticket);
CREATE INDEX idx_deals_magic ON deals(magic);

-- =============================================================================
-- 7. TABELA DE INDICADORES TÉCNICOS (Pré-calculados)
-- =============================================================================
CREATE TABLE IF NOT EXISTS indicators (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    timeframe VARCHAR(10) NOT NULL,
    time TIMESTAMP NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    indicator_params JSONB, -- Parâmetros do indicador
    value DOUBLE PRECISION,
    values JSONB, -- Para indicadores com múltiplos valores
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol_id, timeframe, time, indicator_name, indicator_params)
);

CREATE INDEX idx_indicators_symbol_tf_time ON indicators(symbol_id, timeframe, time DESC);
CREATE INDEX idx_indicators_name ON indicators(indicator_name);

-- =============================================================================
-- 8. TABELA DE SINAIS DE TRADING (Gerados por estratégias)
-- =============================================================================
CREATE TABLE IF NOT EXISTS trade_signals (
    id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol_id INT REFERENCES symbols(id) ON DELETE CASCADE,
    timeframe VARCHAR(10) NOT NULL,
    signal_time TIMESTAMP NOT NULL,
    signal_type VARCHAR(20) NOT NULL, -- BUY, SELL, CLOSE
    strength DOUBLE PRECISION, -- 0.0 a 1.0
    entry_price DOUBLE PRECISION,
    stop_loss DOUBLE PRECISION,
    take_profit DOUBLE PRECISION,
    risk_reward_ratio DOUBLE PRECISION,
    metadata JSONB, -- Dados adicionais da estratégia
    executed BOOLEAN DEFAULT FALSE,
    execution_time TIMESTAMP,
    execution_price DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_signals_symbol_time ON trade_signals(symbol_id, signal_time DESC);
CREATE INDEX idx_signals_strategy ON trade_signals(strategy_name);
CREATE INDEX idx_signals_executed ON trade_signals(executed);

-- =============================================================================
-- 9. TABELA DE BACKTESTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS backtests (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    initial_balance DOUBLE PRECISION NOT NULL,
    final_balance DOUBLE PRECISION,
    total_trades INT,
    winning_trades INT,
    losing_trades INT,
    win_rate DOUBLE PRECISION,
    profit_factor DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    parameters JSONB,
    metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backtests_strategy ON backtests(strategy_name);
CREATE INDEX idx_backtests_symbol ON backtests(symbol);
CREATE INDEX idx_backtests_created ON backtests(created_at DESC);

-- =============================================================================
-- 10. VIEWS ÚTEIS
-- =============================================================================

-- View para últimos ticks com nome do símbolo
CREATE OR REPLACE VIEW v_latest_ticks AS
SELECT 
    t.id,
    s.symbol,
    t.time,
    t.bid,
    t.ask,
    (t.ask - t.bid) as spread,
    t.volume,
    t.created_at
FROM ticks t
JOIN symbols s ON t.symbol_id = s.id
ORDER BY t.time DESC;

-- View para últimas candles
CREATE OR REPLACE VIEW v_latest_candles AS
SELECT 
    c.id,
    s.symbol,
    c.timeframe,
    c.time,
    c.open,
    c.high,
    c.low,
    c.close,
    c.tick_volume,
    c.spread,
    c.created_at
FROM candles c
JOIN symbols s ON c.symbol_id = s.id
ORDER BY c.time DESC;

-- View para posições abertas
CREATE OR REPLACE VIEW v_open_positions AS
SELECT 
    p.ticket,
    s.symbol,
    CASE p.type 
        WHEN 0 THEN 'BUY'
        WHEN 1 THEN 'SELL'
        ELSE 'UNKNOWN'
    END as position_type,
    p.volume,
    p.price_open,
    p.price_current,
    p.profit,
    p.swap,
    (p.profit + p.swap) as total_pnl,
    p.stoploss,
    p.takeprofit,
    p.time_create,
    p.comment
FROM positions p
JOIN symbols s ON p.symbol_id = s.id;

-- =============================================================================
-- 11. FUNÇÕES ÚTEIS
-- =============================================================================

-- Função para obter ou criar símbolo
CREATE OR REPLACE FUNCTION get_or_create_symbol(p_symbol VARCHAR(50))
RETURNS INT AS $$
DECLARE
    v_symbol_id INT;
BEGIN
    SELECT id INTO v_symbol_id FROM symbols WHERE symbol = p_symbol;
    
    IF v_symbol_id IS NULL THEN
        INSERT INTO symbols (symbol) VALUES (p_symbol) RETURNING id INTO v_symbol_id;
    END IF;
    
    RETURN v_symbol_id;
END;
$$ LANGUAGE plpgsql;

-- Função para limpar dados antigos (manutenção)
CREATE OR REPLACE FUNCTION cleanup_old_data(days_to_keep INT DEFAULT 90)
RETURNS TABLE(deleted_ticks BIGINT, deleted_candles BIGINT) AS $$
DECLARE
    v_deleted_ticks BIGINT;
    v_deleted_candles BIGINT;
    v_cutoff_date TIMESTAMP;
BEGIN
    v_cutoff_date := NOW() - INTERVAL '1 day' * days_to_keep;
    
    DELETE FROM ticks WHERE time < v_cutoff_date;
    GET DIAGNOSTICS v_deleted_ticks = ROW_COUNT;
    
    DELETE FROM candles WHERE time < v_cutoff_date;
    GET DIAGNOSTICS v_deleted_candles = ROW_COUNT;
    
    deleted_ticks := v_deleted_ticks;
    deleted_candles := v_deleted_candles;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- COMENTÁRIOS E METADATA
-- =============================================================================

COMMENT ON TABLE symbols IS 'Catálogo de instrumentos financeiros (pares de moedas, ações, etc)';
COMMENT ON TABLE ticks IS 'Dados de ticks em tempo real (bid/ask)';
COMMENT ON TABLE candles IS 'Dados OHLCV (Open, High, Low, Close, Volume) por timeframe';
COMMENT ON TABLE orders IS 'Ordens de trading (pendentes e executadas)';
COMMENT ON TABLE positions IS 'Posições abertas atualmente';
COMMENT ON TABLE deals IS 'Histórico completo de negociações executadas';
COMMENT ON TABLE indicators IS 'Valores de indicadores técnicos pré-calculados';
COMMENT ON TABLE trade_signals IS 'Sinais de trading gerados por estratégias';
COMMENT ON TABLE backtests IS 'Resultados de backtests de estratégias';
