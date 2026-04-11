package com.arbitrage.engine.core.models;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.util.List;

public record L2OrderBook(
    String ticker,
    long timestamp,
    List<Level> asks,
    List<Level> bids
) {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public record Level(
        BigDecimal price,
        BigDecimal quantity
    ) {}

    public String toJson() {
        try {
            return MAPPER.writeValueAsString(this);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
