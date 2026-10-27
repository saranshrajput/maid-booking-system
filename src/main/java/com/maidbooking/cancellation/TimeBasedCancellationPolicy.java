package com.maidbooking.cancellation;

import com.maidbooking.domain.BookingOccurrence;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDateTime;
import org.springframework.stereotype.Component;

// 24h+ before start: full refund; 2h+: half; later: none.
@Component
public class TimeBasedCancellationPolicy implements CancellationPolicy {

    @Override
    public BigDecimal refundFraction(BookingOccurrence occurrence, LocalDateTime now) {
        Duration untilStart = Duration.between(now, occurrence.getSlot().start());
        if (untilStart.compareTo(Duration.ofHours(24)) >= 0) return BigDecimal.ONE;
        if (untilStart.compareTo(Duration.ofHours(2)) >= 0) return new BigDecimal("0.5");
        return BigDecimal.ZERO;
    }
}
