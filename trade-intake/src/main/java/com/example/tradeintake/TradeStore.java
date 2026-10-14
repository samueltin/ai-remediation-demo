package com.example.tradeintake;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;

// demo-shortcut: trades are kept in memory and lost on restart. Production: a database table with audit columns.
@Repository
public class TradeStore {

    // Spring beans are singletons shared by all request threads, so the map must be thread safe.
    private final Map<String, Trade> trades = new ConcurrentHashMap<>();

    public void save(Trade trade) {
        trades.put(trade.tradeId(), trade);
    }

    public Optional<Trade> findById(String tradeId) {
        return Optional.ofNullable(trades.get(tradeId));
    }
}
