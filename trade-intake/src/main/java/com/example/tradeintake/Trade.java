package com.example.tradeintake;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * A simplified interest rate swap trade as received on POST /trades.
 *
 * Amounts and rates use BigDecimal because double cannot represent values
 * like 0.1 exactly. fixedRate is a percentage, so 3.25 means 3.25%.
 */
public record Trade(
        String tradeId,
        BigDecimal notional,
        String currency,
        BigDecimal fixedRate,
        LocalDate startDate,
        LocalDate maturityDate,
        String counterparty) {
}
