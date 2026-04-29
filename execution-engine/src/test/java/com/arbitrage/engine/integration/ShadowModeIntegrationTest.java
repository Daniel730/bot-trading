package com.arbitrage.engine.integration;

import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.broker.Broker;
import com.arbitrage.engine.broker.BrokerageRouter;
import com.arbitrage.engine.broker.MockBroker;
import com.arbitrage.engine.config.EnvironmentConfig;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShadowModeIntegrationTest {

    @Test
    void testBrokerageRouterRouting() {
        L2FeedService mockFeed = Mockito.mock(L2FeedService.class);
        
        if (EnvironmentConfig.isDryRun()) {
            Broker broker = BrokerageRouter.getBroker(mockFeed);
            assertTrue(broker instanceof MockBroker, "Should return MockBroker when in Shadow Mode");
        } else {
            assertThrows(IllegalStateException.class, () -> BrokerageRouter.getBroker(mockFeed));
        }
    }
}
