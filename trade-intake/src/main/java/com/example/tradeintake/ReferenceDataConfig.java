package com.example.tradeintake;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.Constructor;

@Configuration
public class ReferenceDataConfig {

    static final String RESOURCE = "reference-data.yml";

    @Bean
    public ReferenceData referenceData() {
        Yaml yaml = new Yaml(new Constructor(ReferenceData.class));
        ReferenceData data;
        try (InputStream in = new ClassPathResource(RESOURCE).getInputStream()) {
            data = yaml.load(in);
        } catch (IOException e) {
            throw new UncheckedIOException("Cannot read " + RESOURCE, e);
        }
        if (data == null || data.getSupportedCurrencies() == null || data.getSupportedCurrencies().isEmpty()) {
            throw new IllegalStateException(RESOURCE + " must list at least one supported currency");
        }
        return data;
    }
}
