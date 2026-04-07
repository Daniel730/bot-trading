package com.arbitrage.engine.api;

import io.grpc.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LatencyInterceptor implements ServerInterceptor {
    private static final Logger logger = LoggerFactory.getLogger(LatencyInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        long arrivalNs = System.nanoTime();
        String sentNsStr = headers.get(Metadata.Key.of("x-sent-ns", Metadata.ASCII_STRING_MARSHALLER));

        return next.startCall(new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(call) {
            @Override
            public void sendMessage(RespT message) {
                super.sendMessage(message);
            }

            @Override
            public void close(Status status, Metadata trailers) {
                long processedNs = System.nanoTime();
                
                // Add server-side timestamps to trailers for client to read
                trailers.put(Metadata.Key.of("x-received-ns", Metadata.ASCII_STRING_MARSHALLER), String.valueOf(arrivalNs));
                trailers.put(Metadata.Key.of("x-processed-ns", Metadata.ASCII_STRING_MARSHALLER), String.valueOf(processedNs));
                trailers.put(Metadata.Key.of("x-metric-version", Metadata.ASCII_STRING_MARSHALLER), "1");
                
                if (sentNsStr != null) {
                    long sentNs = Long.parseLong(sentNsStr);
                    long transportDelay = arrivalNs - sentNs;
                    long processingDelay = processedNs - arrivalNs;
                    logger.info("Latency Profile: Transport={}us, Processing={}us", 
                            transportDelay / 1000, processingDelay / 1000);
                }
                
                super.close(status, trailers);
            }
        }, headers);
    }
}
