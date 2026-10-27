package com.maidbooking.booking;

import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.exception.InvalidRequestException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class RecurringBookingStrategy implements BookingStrategy {

    @Override
    public BookingType type() {
        return BookingType.RECURRING;
    }

    @Override
    public List<TimeSlot> resolveSlots(BookingCommand command, LocalDateTime now) {
        RecurrenceRule rule = command.recurrence();
        if (rule == null) {
            throw new InvalidRequestException("Recurring booking needs a recurrence rule");
        }
        List<TimeSlot> slots = new ArrayList<>();
        for (LocalDate date = rule.startDate(); slots.size() < rule.occurrences(); date = date.plusDays(1)) {
            LocalDateTime start = date.atTime(rule.startTime());
            if (rule.daysOfWeek().contains(date.getDayOfWeek()) && start.isAfter(now)) {
                slots.add(TimeSlot.of(start, command.durationMinutes()));
            }
        }
        return slots;
    }
}
