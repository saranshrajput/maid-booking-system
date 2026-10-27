package com.maidbooking.repository;

import com.maidbooking.domain.Payment;
import java.util.List;
import java.util.Optional;

public interface IdempotencyStore {
    Optional<List<Payment>> find(String key);

    void save(String key, List<Payment> result);
}
