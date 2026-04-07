package com.arbitrage.engine.api;

import com.arbitrage.engine.core.models.L2OrderBook;

public interface L2FeedService {
    L2OrderBook getLatestBook(String ticker);
}
