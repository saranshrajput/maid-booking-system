package com.maidbooking.domain;

import com.maidbooking.exception.InvalidRequestException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.Set;

// Repeats on the given weekdays at startTime from startDate until `occurrences` slots are generated.
public record RecurrenceRule(Set<DayOfWeek> daysOfWeek, LocalDate startDate, LocalTime startTime, int occurrences) {

    public static final int MAX_OCCURRENCES = 52;

    public RecurrenceRule {
        if (daysOfWeek == null || daysOfWeek.isEmpty() || startDate == null || startTime == null) {
            throw new InvalidRequestException("Recurrence needs days of week, a start date and a start time");
        }
        if (occurrences < 1 || occurrences > MAX_OCCURRENCES) {
            throw new InvalidRequestException("Recurrence occurrences must be between 1 and " + MAX_OCCURRENCES);
        }
        daysOfWeek = Set.copyOf(daysOfWeek);
    }
}
