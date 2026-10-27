package com.maidbooking.booking;

import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.ServiceType;
import java.time.LocalDateTime;

public record BookingCommand(String customerId, String maidId, ServiceType serviceType, BookingType bookingType,
                             int durationMinutes, LocalDateTime startDateTime, RecurrenceRule recurrence) {
}
