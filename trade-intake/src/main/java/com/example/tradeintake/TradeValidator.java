package com.example.tradeintake;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.stereotype.Component;

/**
 * Checks a trade against simple intake rules and returns every problem found,
 * so the caller can fix them all in one go. An empty list means the trade is valid.
 */
@Component
public class TradeValidator {

    // Below zero is allowed because EUR, CHF and JPY swaps traded at negative fixed rates from about 2015 to 2021.
    static final BigDecimal MIN_FIXED_RATE = new BigDecimal("-1.00");
    static final BigDecimal MAX_FIXED_RATE = new BigDecimal("20.00");

    private final Set<String> supportedCurrencies;

    public TradeValidator(ReferenceData referenceData) {
        this.supportedCurrencies = Set.copyOf(referenceData.getSupportedCurrencies());
    }

    public List<String> validate(Trade trade) {
        List<String> errors = new ArrayList<>();

        if (isBlank(trade.tradeId())) {
            errors.add("tradeId is required");
        }
        if (isBlank(trade.counterparty())) {
            errors.add("counterparty is required");
        }

        if (trade.notional() == null) {
            errors.add("notional is required");
        } else if (trade.notional().signum() <= 0) {
            errors.add("notional must be positive");
        }

        if (trade.currency() == null) {
            errors.add("currency is required");
        } else if (!supportedCurrencies.contains(trade.currency())) {
            errors.add("currency " + trade.currency() + " is not supported");
        }

        if (trade.fixedRate() == null) {
            errors.add("fixedRate is required");
        } else if (trade.fixedRate().compareTo(MIN_FIXED_RATE) < 0
                || trade.fixedRate().compareTo(MAX_FIXED_RATE) > 0) {
            errors.add("fixedRate must be between " + MIN_FIXED_RATE + " and " + MAX_FIXED_RATE + " percent");
        }

        if (trade.startDate() == null) {
            errors.add("startDate is required");
        }
        if (trade.maturityDate() == null) {
            errors.add("maturityDate is required");
        }
        if (trade.startDate() != null && trade.maturityDate() != null
                && !trade.maturityDate().isAfter(trade.startDate())) {
            errors.add("maturityDate must be after startDate");
        }

        return errors;
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
