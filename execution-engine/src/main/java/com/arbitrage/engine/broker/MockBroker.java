package com.arbitrage.engine.broker;

import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.core.VwapCalculator;
import com.arbitrage.engine.core.models.L2OrderBook;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class MockBroker implements Broker {
    private static final Logger logger = LoggerFactory.getLogger(MockBroker.class);
    private final L2FeedService l2FeedService;
    private final VwapCalculator vwapCalculator = new VwapCalculator();
    private static final long STALE_DATA_THRESHOLD_MS = 100;

    public MockBroker(L2FeedService l2FeedService) {
        this.l2FeedService = l2FeedService;
    }

    @Override
    public Mono<BrokerExecutionResponse> execute(BrokerExecutionRequest request) {
        return Mono.fromCallable(() -> {
            logger.info("Executing MOCK trade for signal {}", request.signalId());
            List<BigDecimal> fillPrices = new ArrayList<>();
            
            try {
                for (BrokerLeg leg : request.legs()) {
                    L2OrderBook book = l2FeedService.getLatestBook(leg.ticker());
                    if (book == null) {
                        logger.error("NO L2 DATA for {}", leg.ticker());
                        return new BrokerExecutionResponse(false, "No L2 book for " + leg.ticker(), null);
                    }
                    
                    // T008: Stale Data Check
                    long ageMs = System.currentTimeMillis() - book.timestamp();
                    if (ageMs > STALE_DATA_THRESHOLD_MS) {
                        logger.error("STALE L2 DATA for {}: {}ms old (Limit: {}ms)", 
                                leg.ticker(), ageMs, STALE_DATA_THRESHOLD_MS);
                        return new BrokerExecutionResponse(false, "Stale market data for " + leg.ticker(), null);
                    }

                    BigDecimal fillPrice = vwapCalculator.calculateVwap(book, leg.side(), leg.quantity());
                    fillPrices.add(fillPrice);
                    
                    logger.info("MOCK FILL: {} {} @ {}", leg.side(), leg.ticker(), fillPrice);
                }
                
                return new BrokerExecutionResponse(true, "Shadow Trade Executed Successfully", fillPrices);
            } catch (VwapCalculator.InsufficientMarketDepthException e) {
                logger.error("MOCK EXECUTION FAILED: {}", e.getMessage());
                return new BrokerExecutionResponse(false, e.getMessage(), null);
            } catch (Exception e) {
                logger.error("Unexpected error during mock execution", e);
                return new BrokerExecutionResponse(false, "Internal simulation error: " + e.getMessage(), null);
            }
        });
    }

    @Override
    public int cancelAllOrders() {
        logger.info("MOCK: All orders cancelled.");
        return 0;
    }

    @Override
    public int liquidateAllPositions() {
        logger.info("MOCK: All positions liquidated.");
        return 0;
    }
}
