package com.arbitrage.engine.broker;

import com.arbitrage.engine.config.EnvironmentConfig;
import com.arbitrage.engine.api.L2FeedService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BrokerageRouter {
    private static final Logger logger = LoggerFactory.getLogger(BrokerageRouter.class);

    public static Broker getBroker(L2FeedService l2FeedService) {
        if (EnvironmentConfig.isDryRun()) {
            logger.warn("BrokerageRouter: SHADOW MODE ACTIVE. Routing to MockBroker.");
            return new MockBroker(l2FeedService);
        }
        throw new IllegalStateException(
                "Execution engine live brokerage is not implemented. Set DRY_RUN=true or wire a real LiveBroker before enabling live mode."
        );
    }
}
