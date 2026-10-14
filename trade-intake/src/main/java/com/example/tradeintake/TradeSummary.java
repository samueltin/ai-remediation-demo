package com.example.tradeintake;

import java.util.Map;

import org.apache.commons.text.StringSubstitutor;

/** One line description of a trade, written to the log when the trade is accepted. */
public final class TradeSummary {

    private static final String TEMPLATE =
            "Trade ${tradeId}: pay fixed ${fixedRate}% on ${currency} ${notional}"
                    + " from ${startDate} to ${maturityDate} with ${counterparty}";

    private TradeSummary() {
    }

    public static String format(Trade trade) {
        Map<String, Object> values = Map.of(
                "tradeId", trade.tradeId(),
                "fixedRate", trade.fixedRate().toPlainString(),
                "currency", trade.currency(),
                "notional", trade.notional().toPlainString(),
                "startDate", trade.startDate(),
                "maturityDate", trade.maturityDate(),
                "counterparty", trade.counterparty());
        return StringSubstitutor.replace(TEMPLATE, values);
    }
}
