-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Tabela de Ticks (Negócios Realizados / L1)
CREATE TABLE IF NOT EXISTS market_ticks (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    price DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION
);

-- Converte em Hypertable (Particionamento Automático)
SELECT create_hypertable('market_ticks', 'time', if_not_exists => TRUE);

-- Tabela de Order Book Snapshots (L2 - Profundidade)
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    bids JSONB, -- Array de [price, volume]
    asks JSONB  -- Array de [price, volume]
);

-- Converte em Hypertable
SELECT create_hypertable('orderbook_snapshots', 'time', if_not_exists => TRUE);

-- Índices para Performance
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON market_ticks (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_book_symbol_time ON orderbook_snapshots (symbol, time DESC);
