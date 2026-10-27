package com.maidbooking.booking;

import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.TimeSlot;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class InstantBookingStrategy implements BookingStrategy {

    @Override
    public BookingType type() {
        return BookingType.INSTANT;
    }

    @Override
    public List<TimeSlot> resolveSlots(BookingCommand command, LocalDateTime now) {
        return List.of(TimeSlot.of(now.truncatedTo(ChronoUnit.MINUTES), command.durationMinutes()));
    }
}
