package com.arbitrage.engine.integration;

import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.broker.Broker;
import com.arbitrage.engine.broker.BrokerageRouter;
import com.arbitrage.engine.broker.MockBroker;
import com.arbitrage.engine.config.EnvironmentConfig;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ShadowModeIntegrationTest {

    @Test
    void testBrokerageRouterRouting() {
        L2FeedService mockFeed = Mockito.mock(L2FeedService.class);
        Broker broker = BrokerageRouter.getBroker(mockFeed);
        
        if (EnvironmentConfig.isDryRun()) {
            assertTrue(broker instanceof MockBroker, "Should return MockBroker when in Shadow Mode");
        } else {
            // Live mode logic might depend on how LiveBroker is implemented
            // For now, it returns LiveBroker placeholder
            assertTrue(broker.getClass().getSimpleName().contains("LiveBroker"), "Should return LiveBroker in Live Mode");
        }
    }
}
