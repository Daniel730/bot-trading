CREATE TABLE IF NOT EXISTS trade_ledger (
    id SERIAL PRIMARY KEY,
    signal_id UUID NOT NULL,
    pair_id VARCHAR(20),
    ticker VARCHAR(10),
    side VARCHAR(10),
    requested_qty DECIMAL(18,10),
    requested_price DECIMAL(18,10),
    actual_vwap DECIMAL(18,10),
    status VARCHAR(50),
    latency_ms BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trade_ledger_signal_id ON trade_ledger(signal_id);
