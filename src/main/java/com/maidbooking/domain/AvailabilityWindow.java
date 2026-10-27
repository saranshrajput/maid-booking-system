package com.maidbooking.domain;

import com.maidbooking.exception.InvalidRequestException;
import java.time.DayOfWeek;
import java.time.LocalTime;

// A recurring weekly working window, e.g. MONDAY 09:00-17:00.
public record AvailabilityWindow(DayOfWeek day, LocalTime start, LocalTime end) {

    public AvailabilityWindow {
        if (day == null || start == null || end == null || !end.isAfter(start)) {
            throw new InvalidRequestException("Availability window needs a day and an end time after its start");
        }
    }

    public boolean covers(TimeSlot slot) {
        if (!slot.start().toLocalDate().equals(slot.end().toLocalDate())) {
            return false;
        }
        return slot.start().getDayOfWeek() == day
                && !slot.start().toLocalTime().isBefore(start)
                && !slot.end().toLocalTime().isAfter(end);
    }
}
