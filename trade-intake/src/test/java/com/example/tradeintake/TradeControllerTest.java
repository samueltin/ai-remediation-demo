package com.example.tradeintake;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

// @WebMvcTest loads only the web layer, so the real validator, reference data and store
// are imported rather than mocked: the test then covers the actual rules end to end.
@WebMvcTest(TradeController.class)
@Import({TradeValidator.class, ReferenceDataConfig.class, TradeStore.class})
class TradeControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private TradeStore store;

    @Test
    void validTradeReturns201AndIsStored() throws Exception {
        String json = """
                {
                  "tradeId": "T-2001",
                  "notional": 25000000,
                  "currency": "USD",
                  "fixedRate": 4.10,
                  "startDate": "2026-03-01",
                  "maturityDate": "2036-03-01",
                  "counterparty": "CPTY-B"
                }
                """;

        mockMvc.perform(post("/trades").contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tradeId").value("T-2001"))
                .andExpect(jsonPath("$.startDate").value("2026-03-01"));

        assertThat(store.findById("T-2001")).isPresent();
    }

    @Test
    void invalidTradeReturns400WithErrors() throws Exception {
        String json = """
                {
                  "tradeId": "T-2002",
                  "notional": -5,
                  "currency": "XYZ",
                  "fixedRate": 4.10,
                  "startDate": "2026-03-01",
                  "maturityDate": "2036-03-01",
                  "counterparty": "CPTY-B"
                }
                """;

        mockMvc.perform(post("/trades").contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors").value(hasItems(
                        "notional must be positive",
                        "currency XYZ is not supported")));

        assertThat(store.findById("T-2002")).isEmpty();
    }

    @Test
    void unreadableDateReturns400() throws Exception {
        String json = """
                {
                  "tradeId": "T-2003",
                  "notional": 1000000,
                  "currency": "EUR",
                  "fixedRate": 2.5,
                  "startDate": "not-a-date",
                  "maturityDate": "2030-01-01",
                  "counterparty": "CPTY-C"
                }
                """;

        mockMvc.perform(post("/trades").contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isBadRequest());

        assertThat(store.findById("T-2003")).isEmpty();
    }
}
