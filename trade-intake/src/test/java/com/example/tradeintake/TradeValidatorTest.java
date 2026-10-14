package com.example.tradeintake;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.Test;

// Plain JUnit test: the validator has no Spring dependencies, so no application context is needed.
class TradeValidatorTest {

    private static final BigDecimal NOTIONAL = new BigDecimal("10000000");
    private static final BigDecimal RATE = new BigDecimal("3.25");
    private static final LocalDate START = LocalDate.of(2026, 1, 15);
    private static final LocalDate MATURITY = LocalDate.of(2031, 1, 15);

    private final TradeValidator validator = new TradeValidator();

    private static Trade trade(BigDecimal notional, String currency, BigDecimal fixedRate,
                               LocalDate startDate, LocalDate maturityDate) {
        return new Trade("T-1001", notional, currency, fixedRate, startDate, maturityDate, "CPTY-A");
    }

    @Test
    void validTradeHasNoErrors() {
        List<String> errors = validator.validate(trade(NOTIONAL, "EUR", RATE, START, MATURITY));

        assertThat(errors).isEmpty();
    }

    @Test
    void unsupportedCurrencyIsRejected() {
        List<String> errors = validator.validate(trade(NOTIONAL, "XYZ", RATE, START, MATURITY));

        assertThat(errors).containsExactly("currency XYZ is not supported");
    }

    @Test
    void zeroNotionalIsRejected() {
        List<String> errors = validator.validate(trade(BigDecimal.ZERO, "EUR", RATE, START, MATURITY));

        assertThat(errors).containsExactly("notional must be positive");
    }

    @Test
    void negativeNotionalIsRejected() {
        List<String> errors = validator.validate(trade(new BigDecimal("-500"), "EUR", RATE, START, MATURITY));

        assertThat(errors).containsExactly("notional must be positive");
    }

    @Test
    void maturityBeforeStartIsRejected() {
        List<String> errors = validator.validate(trade(NOTIONAL, "EUR", RATE, START, START.minusDays(1)));

        assertThat(errors).containsExactly("maturityDate must be after startDate");
    }

    @Test
    void maturityOnStartDateIsRejected() {
        List<String> errors = validator.validate(trade(NOTIONAL, "EUR", RATE, START, START));

        assertThat(errors).containsExactly("maturityDate must be after startDate");
    }

    @Test
    void rateAboveRangeIsRejected() {
        List<String> errors = validator.validate(trade(NOTIONAL, "EUR", new BigDecimal("20.01"), START, MATURITY));

        assertThat(errors).containsExactly("fixedRate must be between -1.00 and 20.00 percent");
    }

    @Test
    void smallNegativeRateIsAccepted() {
        List<String> errors = validator.validate(trade(NOTIONAL, "CHF", new BigDecimal("-0.75"), START, MATURITY));

        assertThat(errors).isEmpty();
    }

    @Test
    void missingFieldsAreReportedWithoutException() {
        Trade empty = new Trade(null, null, null, null, null, null, " ");

        List<String> errors = validator.validate(empty);

        assertThat(errors).containsExactly(
                "tradeId is required",
                "counterparty is required",
                "notional is required",
                "currency is required",
                "fixedRate is required",
                "startDate is required",
                "maturityDate is required");
    }

    @Test
    void allErrorsAreReportedTogether() {
        List<String> errors = validator.validate(
                trade(new BigDecimal("-1"), "XYZ", new BigDecimal("25"), START, START));

        assertThat(errors).hasSize(4);
    }
}
