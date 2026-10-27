package com.maidbooking.repository;

import com.maidbooking.domain.Payment;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryIdempotencyStore implements IdempotencyStore {
    private final Map<String, List<Payment>> store = new ConcurrentHashMap<>();

    @Override
    public Optional<List<Payment>> find(String key) {
        return Optional.ofNullable(store.get(key));
    }

    @Override
    public void save(String key, List<Payment> result) {
        store.put(key, List.copyOf(result));
    }
}
