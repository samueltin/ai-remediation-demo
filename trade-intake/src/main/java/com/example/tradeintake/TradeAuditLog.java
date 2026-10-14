package com.example.tradeintake;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.google.common.eventbus.Subscribe;

// demo-shortcut: audit entries are kept in memory and written to the log. Production: an append-only audit store.
@Component
public class TradeAuditLog {

    private static final Logger log = LoggerFactory.getLogger(TradeAuditLog.class);

    // Written on the event thread and read on request threads.
    private final List<String> entries = new CopyOnWriteArrayList<>();

    @Subscribe
    public void onTradeAccepted(Trade trade) {
        String entry = TradeSummary.format(trade);
        entries.add(entry);
        log.info("Accepted {}", entry);
    }

    public List<String> entries() {
        return List.copyOf(entries);
    }
}
