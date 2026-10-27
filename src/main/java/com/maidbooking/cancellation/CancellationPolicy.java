package com.maidbooking.cancellation;

import com.maidbooking.domain.BookingOccurrence;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public interface CancellationPolicy {
    // Fraction of the paid amount to refund, between 0 and 1.
    BigDecimal refundFraction(BookingOccurrence occurrence, LocalDateTime now);
}
