package com.maidbooking.booking;

import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.TimeSlot;
import java.time.LocalDateTime;
import java.util.List;

// One implementation per booking type; a new type is a new @Component, no existing code changes.
public interface BookingStrategy {
    BookingType type();

    List<TimeSlot> resolveSlots(BookingCommand command, LocalDateTime now);
}
