package com.arbitrage.engine.core.models;

import java.math.BigDecimal;

public record ExecutionLeg(
    String ticker,
    Side side,
    BigDecimal quantity,
    BigDecimal targetPrice
) {
    public enum Side {
        BUY, SELL
    }
}
