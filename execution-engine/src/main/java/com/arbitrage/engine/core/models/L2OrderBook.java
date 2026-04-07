package com.arbitrage.engine.core.models;

import java.math.BigDecimal;
import java.util.List;

public record L2OrderBook(
    String ticker,
    long timestamp,
    List<Level> asks,
    List<Level> bids
) {
    public record Level(
        BigDecimal price,
        BigDecimal quantity
    ) {}
}
