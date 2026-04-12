package com.arbitrage.engine.risk;

import com.arbitrage.engine.core.models.ExecutionLeg;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import static org.junit.jupiter.api.Assertions.*;

class SlippageGuardTest {

    private final SlippageGuard guard = new SlippageGuard();

    @Test
    void validateSlippage_BuyUnderLimit_Success() {
        assertDoesNotThrow(() -> {
            guard.validateSlippage(ExecutionLeg.Side.BUY, new BigDecimal("100.05"), new BigDecimal("100.00"), new BigDecimal("0.001"));
        });
    }

    @Test
    void validateSlippage_BuyOverLimit_ThrowsException() {
        assertThrows(SlippageGuard.SlippageViolationException.class, () -> {
            guard.validateSlippage(ExecutionLeg.Side.BUY, new BigDecimal("100.115"), new BigDecimal("100.00"), new BigDecimal("0.001"));
        });
    }

    @Test
    void validateSlippage_SellAboveFloor_Success() {
        assertDoesNotThrow(() -> {
            guard.validateSlippage(ExecutionLeg.Side.SELL, new BigDecimal("99.95"), new BigDecimal("100.00"), new BigDecimal("0.001"));
        });
    }

    @Test
    void validateSlippage_SellBelowFloor_ThrowsException() {
        assertThrows(SlippageGuard.SlippageViolationException.class, () -> {
            guard.validateSlippage(ExecutionLeg.Side.SELL, new BigDecimal("99.85"), new BigDecimal("100.00"), new BigDecimal("0.001"));
        });
    }
}
