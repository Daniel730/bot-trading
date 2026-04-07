package com.arbitrage.engine.core;

import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.core.models.L2OrderBook;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class VwapCalculator {

    public static class InsufficientMarketDepthException extends RuntimeException {
        public InsufficientMarketDepthException(String message) {
            super(message);
        }
    }

    public BigDecimal calculateVwap(L2OrderBook book, ExecutionLeg.Side side, BigDecimal requestedQuantity) {
        List<L2OrderBook.Level> levels = (side == ExecutionLeg.Side.BUY) ? book.asks() : book.bids();

        BigDecimal remainingQuantity = requestedQuantity;
        BigDecimal totalCost = BigDecimal.ZERO;

        for (L2OrderBook.Level level : levels) {
            BigDecimal levelQuantity = level.quantity();
            BigDecimal levelPrice = level.price();

            if (remainingQuantity.compareTo(levelQuantity) <= 0) {
                // Consume only what's needed from this level
                totalCost = totalCost.add(remainingQuantity.multiply(levelPrice));
                remainingQuantity = BigDecimal.ZERO;
                break;
            } else {
                // Consume the whole level
                totalCost = totalCost.add(levelQuantity.multiply(levelPrice));
                remainingQuantity = remainingQuantity.subtract(levelQuantity);
            }
        }

        if (remainingQuantity.compareTo(BigDecimal.ZERO) > 0) {
            throw new InsufficientMarketDepthException("Insufficient market depth for ticker " + book.ticker());
        }

        return totalCost.divide(requestedQuantity, 10, RoundingMode.HALF_UP);
    }
}
