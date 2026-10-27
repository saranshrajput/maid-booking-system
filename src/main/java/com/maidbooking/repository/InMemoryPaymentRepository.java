package com.maidbooking.repository;

import com.maidbooking.domain.Payment;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryPaymentRepository implements PaymentRepository {
    private final Map<String, Payment> store = new ConcurrentHashMap<>();

    @Override
    public Payment save(Payment payment) {
        store.put(payment.getId(), payment);
        return payment;
    }

    @Override
    public Optional<Payment> findCapturedByOccurrenceId(String occurrenceId) {
        return store.values().stream()
                .filter(p -> p.getOccurrenceId().equals(occurrenceId) && p.isCaptured())
                .findFirst();
    }
}
