package com.arbitrage.engine.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class EnvironmentConfig {
    private static final Logger logger = LoggerFactory.getLogger(EnvironmentConfig.class);
    private static final String DRY_RUN_ENV = "DRY_RUN";
    private static final boolean isDryRun;

    static {
        String envVal = System.getenv(DRY_RUN_ENV);
        isDryRun = Boolean.parseBoolean(envVal);
        
        if (isDryRun) {
            logger.warn("!!! SHADOW MODE ACTIVE: DRY_RUN=true !!!");
            logger.warn("BrokerageRouter will intercept all live trades and route to MockBroker.");
        } else {
            logger.info("Live Mode Active (DRY_RUN=false). Trades will hit external APIs.");
        }
    }

    public static boolean isDryRun() {
        return isDryRun;
    }
}
