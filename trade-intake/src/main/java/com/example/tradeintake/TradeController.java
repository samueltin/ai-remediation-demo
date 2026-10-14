package com.example.tradeintake;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.google.common.eventbus.EventBus;

@RestController
@RequestMapping("/trades")
public class TradeController {

    private final TradeValidator validator;
    private final TradeStore store;
    private final EventBus tradeEvents;

    public TradeController(TradeValidator validator, TradeStore store, EventBus tradeEvents) {
        this.validator = validator;
        this.store = store;
        this.tradeEvents = tradeEvents;
    }

    @PostMapping
    public ResponseEntity<?> create(@RequestBody Trade trade) {
        List<String> errors = validator.validate(trade);
        if (!errors.isEmpty()) {
            return ResponseEntity.badRequest().body(new ValidationErrors(errors));
        }
        store.save(trade);
        tradeEvents.post(trade);
        return ResponseEntity.status(HttpStatus.CREATED).body(trade);
    }
}
