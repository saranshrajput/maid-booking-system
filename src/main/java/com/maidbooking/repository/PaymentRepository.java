package com.maidbooking.repository;

import com.maidbooking.domain.Payment;
import java.util.Optional;

public interface PaymentRepository {
    Payment save(Payment payment);

    Optional<Payment> findCapturedByOccurrenceId(String occurrenceId);
}
