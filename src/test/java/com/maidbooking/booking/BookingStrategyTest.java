package com.maidbooking.booking;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.exception.InvalidRequestException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class BookingStrategyTest {
    private static final LocalDateTime NOW = LocalDateTime.of(2030, 1, 7, 10, 0, 30); // Monday

    private BookingCommand command(BookingType type, LocalDateTime start, RecurrenceRule rule) {
        return new BookingCommand("c", "m", ServiceType.CLEANING, type, 60, start, rule);
    }

    @Test
    void instantStartsNowTruncatedToTheMinute() {
        List<TimeSlot> slots = new InstantBookingStrategy().resolveSlots(command(BookingType.INSTANT, null, null), NOW);
        assertEquals(List.of(TimeSlot.of(LocalDateTime.of(2030, 1, 7, 10, 0), 60)), slots);
    }

    @Test
    void scheduledRejectsPastOrMissingStart() {
        ScheduledBookingStrategy strategy = new ScheduledBookingStrategy();
        assertThrows(InvalidRequestException.class,
                () -> strategy.resolveSlots(command(BookingType.SCHEDULED, NOW.minusHours(1), null), NOW));
        assertThrows(InvalidRequestException.class,
                () -> strategy.resolveSlots(command(BookingType.SCHEDULED, null, null), NOW));
    }

    @Test
    void recurringGeneratesRequestedOccurrencesOnMatchingDays() {
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.SUNDAY), LocalDate.of(2030, 1, 7), LocalTime.of(9, 0), 3);
        List<TimeSlot> slots = new RecurringBookingStrategy().resolveSlots(command(BookingType.RECURRING, null, rule), NOW);
        assertEquals(List.of(LocalDateTime.of(2030, 1, 13, 9, 0), LocalDateTime.of(2030, 1, 20, 9, 0),
                LocalDateTime.of(2030, 1, 27, 9, 0)), slots.stream().map(TimeSlot::start).toList());
    }

    @Test
    void recurringSkipsTodaysSlotThatAlreadyPassed() {
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.MONDAY), LocalDate.of(2030, 1, 7), LocalTime.of(9, 0), 2);
        List<TimeSlot> slots = new RecurringBookingStrategy().resolveSlots(command(BookingType.RECURRING, null, rule), NOW);
        assertEquals(LocalDateTime.of(2030, 1, 14, 9, 0), slots.get(0).start());
    }

    @Test
    void recurrenceRuleRejectsBadInput() {
        assertThrows(InvalidRequestException.class,
                () -> new RecurrenceRule(Set.of(), LocalDate.now(), LocalTime.NOON, 3));
        assertThrows(InvalidRequestException.class,
                () -> new RecurrenceRule(Set.of(DayOfWeek.MONDAY), LocalDate.now(), LocalTime.NOON, 0));
    }
}
