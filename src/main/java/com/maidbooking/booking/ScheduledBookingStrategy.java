package com.maidbooking.booking;

import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.exception.InvalidRequestException;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class ScheduledBookingStrategy implements BookingStrategy {

    @Override
    public BookingType type() {
        return BookingType.SCHEDULED;
    }

    @Override
    public List<TimeSlot> resolveSlots(BookingCommand command, LocalDateTime now) {
        LocalDateTime start = command.startDateTime();
        if (start == null || !start.isAfter(now)) {
            throw new InvalidRequestException("Scheduled booking needs a start date-time in the future");
        }
        return List.of(TimeSlot.of(start, command.durationMinutes()));
    }
}
