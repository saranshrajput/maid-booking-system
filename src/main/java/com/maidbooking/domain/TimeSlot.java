package com.maidbooking.domain;

import com.maidbooking.exception.InvalidRequestException;
import java.time.LocalDateTime;

public record TimeSlot(LocalDateTime start, LocalDateTime end) {

    public TimeSlot {
        if (start == null || end == null || !end.isAfter(start)) {
            throw new InvalidRequestException("Time slot must have an end after its start");
        }
    }

    public static TimeSlot of(LocalDateTime start, int durationMinutes) {
        if (durationMinutes <= 0) {
            throw new InvalidRequestException("Duration must be positive");
        }
        return new TimeSlot(start, start.plusMinutes(durationMinutes));
    }

    // Half-open interval overlap, so back-to-back slots do not conflict.
    public boolean overlaps(TimeSlot other) {
        return start.isBefore(other.end) && other.start.isBefore(end);
    }

    public long minutes() {
        return java.time.Duration.between(start, end).toMinutes();
    }
}
