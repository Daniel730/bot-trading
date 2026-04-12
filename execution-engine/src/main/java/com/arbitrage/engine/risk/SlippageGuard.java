package com.arbitrage.engine.risk;

import com.arbitrage.engine.core.models.ExecutionLeg;
import java.math.BigDecimal;
import java.math.RoundingMode;

public class SlippageGuard {

    public static class SlippageViolationException extends RuntimeException {
        public SlippageViolationException(String message) {
            super(message);
        }
    }

    public void validateSlippage(ExecutionLeg.Side side, BigDecimal actualVwap, BigDecimal targetPrice, BigDecimal maxSlippagePct) {
        if (actualVwap == null || targetPrice == null || maxSlippagePct == null) {
            throw new SlippageViolationException("Slippage validation failed: Missing required pricing data (null)");
        }
        
        if (side == ExecutionLeg.Side.BUY) {
            BigDecimal ceiling = targetPrice.multiply(BigDecimal.ONE.add(maxSlippagePct));
            if (actualVwap.compareTo(ceiling) > 0) {
                throw new SlippageViolationException(
                    String.format("BUY Slippage exceeded. Actual: %s, Ceiling: %s", actualVwap, ceiling));
            }
        } else {
            BigDecimal floor = targetPrice.multiply(BigDecimal.ONE.subtract(maxSlippagePct));
            if (actualVwap.compareTo(floor) < 0) {
                throw new SlippageViolationException(
                    String.format("SELL Slippage exceeded. Actual: %s, Floor: %s", actualVwap, floor));
            }
        }
    }
}
