package com.example.tradeintake;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.google.common.eventbus.AsyncEventBus;
import com.google.common.eventbus.EventBus;

// demo-shortcut: accepted trades go on an in-process Guava event bus. Production: a message broker topic,
// so downstream systems receive them durably.
@Configuration
public class TradeEventsConfig {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService tradeEventExecutor() {
        return Executors.newSingleThreadExecutor();
    }

    @Bean
    public EventBus tradeEvents(ExecutorService tradeEventExecutor, TradeAuditLog auditLog) {
        EventBus bus = new AsyncEventBus("trade-events", tradeEventExecutor);
        bus.register(auditLog);
        return bus;
    }
}
