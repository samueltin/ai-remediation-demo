package com.example.tradeintake;

import java.util.List;

/**
 * Static reference data used by trade validation, loaded from reference-data.yml.
 *
 * A JavaBean rather than a record, because SnakeYAML fills objects through a
 * no argument constructor and setters.
 */
public class ReferenceData {

    private List<String> supportedCurrencies;

    public List<String> getSupportedCurrencies() {
        return supportedCurrencies;
    }

    public void setSupportedCurrencies(List<String> supportedCurrencies) {
        this.supportedCurrencies = supportedCurrencies;
    }
}
