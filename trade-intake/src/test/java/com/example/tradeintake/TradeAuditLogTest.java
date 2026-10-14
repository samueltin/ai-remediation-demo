package com.example.tradeintake;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import com.google.common.eventbus.AsyncEventBus;
import com.google.common.eventbus.EventBus;
import com.google.common.util.concurrent.MoreExecutors;

class TradeAuditLogTest {

    @Test
    void acceptedTradeIsRecordedAsOneLineSummary() {
        TradeAuditLog auditLog = new TradeAuditLog();
        // Delivers events on the calling thread, so the assertion needs no waiting.
        EventBus tradeEvents = new AsyncEventBus(MoreExecutors.sameThreadExecutor());
        tradeEvents.register(auditLog);

        tradeEvents.post(new Trade("T-3001", new BigDecimal("50000000"), "GBP", new BigDecimal("4.25"),
                LocalDate.of(2026, 11, 1), LocalDate.of(2031, 11, 1), "CPTY-X"));

        assertThat(auditLog.entries()).containsExactly(
                "Trade T-3001: pay fixed 4.25% on GBP 50000000 from 2026-11-01 to 2031-11-01 with CPTY-X");
    }
}
