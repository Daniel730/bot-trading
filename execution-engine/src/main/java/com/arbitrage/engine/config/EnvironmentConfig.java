package com.arbitrage.engine.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class EnvironmentConfig {
    private static final Logger logger = LoggerFactory.getLogger(EnvironmentConfig.class);
    private static final String DRY_RUN_ENV = "DRY_RUN";
    private static final String LIVE_CAPITAL_DANGER_ENV = "LIVE_CAPITAL_DANGER";
    private static final boolean isDryRun;
    private static final boolean isLiveCapitalDanger;

    static {
        String envVal = System.getenv(DRY_RUN_ENV);
        isDryRun = Boolean.parseBoolean(envVal);
        
        String dangerVal = System.getenv(LIVE_CAPITAL_DANGER_ENV);
        isLiveCapitalDanger = Boolean.parseBoolean(dangerVal);
        
        if (isDryRun) {
            logger.warn("!!! SHADOW MODE ACTIVE: DRY_RUN=true !!!");
            logger.warn("BrokerageRouter will intercept all live trades and route to MockBroker.");
        } else {
            logger.error("Live Mode requested (DRY_RUN=false), but Java live brokerage is not implemented.");
        }

        if (isLiveCapitalDanger) {
            logger.warn("!!! LIVE_CAPITAL_DANGER ACTIVE: REAL CAPITAL AT RISK !!!");
        }
    }

    public static boolean isDryRun() {
        return isDryRun;
    }

    public static boolean isLiveCapitalDanger() {
        return isLiveCapitalDanger;
    }
}
