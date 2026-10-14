package com.example.tradeintake;

import java.util.List;

/** Response body for a rejected trade, serialised as {"errors": [...]}. */
public record ValidationErrors(List<String> errors) {
}
