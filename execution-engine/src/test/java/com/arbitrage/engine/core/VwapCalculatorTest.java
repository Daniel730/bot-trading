package com.arbitrage.engine.core;

import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.core.models.L2OrderBook;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class VwapCalculatorTest {

    private final VwapCalculator calculator = new VwapCalculator();

    @Test
    void calculateVwap_BuyMultipleLevels_Success() {
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis(), List.of(
            new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("10")),
            new L2OrderBook.Level(new BigDecimal("50.10"), new BigDecimal("20"))
        ), List.of());

        BigDecimal result = calculator.calculateVwap(book, ExecutionLeg.Side.BUY, new BigDecimal("15"));
        
        // Expected: (10 * 50.00 + 5 * 50.10) / 15 = 750.50 / 15 = 50.0333333333
        assertEquals(0, new BigDecimal("50.0333333333").compareTo(result));
    }

    @Test
    void calculateVwap_SellMultipleLevels_Success() {
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis(), List.of(), List.of(
            new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("10")),
            new L2OrderBook.Level(new BigDecimal("49.90"), new BigDecimal("20"))
        ));

        BigDecimal result = calculator.calculateVwap(book, ExecutionLeg.Side.SELL, new BigDecimal("15"));
        
        // Expected: (10 * 50.00 + 5 * 49.90) / 15 = (500 + 249.50) / 15 = 749.50 / 15 = 49.9666666667
        assertEquals(0, new BigDecimal("49.9666666667").compareTo(result));
    }

    @Test
    void calculateVwap_InsufficientDepth_ThrowsException() {
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis(), List.of(
            new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("10"))
        ), List.of());

        assertThrows(VwapCalculator.InsufficientMarketDepthException.class, () -> {
            calculator.calculateVwap(book, ExecutionLeg.Side.BUY, new BigDecimal("15"));
        });
    }
}
