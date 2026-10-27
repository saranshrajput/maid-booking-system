package com.maidbooking.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.maidbooking.booking.BookingCommand;
import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingStatus;
import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.OccurrenceStatus;
import com.maidbooking.domain.PaymentMethodType;
import com.maidbooking.domain.PaymentStatus;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.exception.InvalidStateException;
import com.maidbooking.support.TestContext;
import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CancellationServiceTest {
    private static final PayCommand PAY = new PayCommand(PaymentMethodType.WALLET, "wallet-1", null);

    private TestContext ctx;
    private Maid maid;

    @BeforeEach
    void setUp() {
        ctx = new TestContext();
        maid = ctx.defaultMaid();
    }

    private Booking paidScheduled(LocalDateTime start) {
        Booking booking = ctx.bookScheduled(maid, start, 60);
        ctx.paymentService.pay(booking.getId(), PAY, null);
        return booking;
    }

    @Test
    void moreThan24HoursBeforeStartRefundsInFull() {
        Booking booking = paidScheduled(LocalDateTime.of(2030, 1, 9, 12, 0));
        CancellationResult result = ctx.cancellationService.cancel(booking.getId(), null);
        assertEquals(new BigDecimal("200.00"), result.totalRefund());
        assertEquals(BookingStatus.CANCELLED, booking.status());
        assertEquals(PaymentStatus.REFUNDED,
                ctx.paymentRepository.findCapturedByOccurrenceId(booking.getOccurrences().get(0).getId()).orElseThrow().getStatus());
    }

    @Test
    void between2And24HoursRefundsHalf() {
        Booking booking = paidScheduled(LocalDateTime.of(2030, 1, 8, 9, 0));
        assertEquals(new BigDecimal("100.00"), ctx.cancellationService.cancel(booking.getId(), null).totalRefund());
    }

    @Test
    void lessThan2HoursRefundsNothing() {
        Booking booking = paidScheduled(LocalDateTime.of(2030, 1, 7, 11, 0));
        assertEquals(new BigDecimal("0.00"), ctx.cancellationService.cancel(booking.getId(), null).totalRefund());
    }

    @Test
    void unpaidBookingCancelsWithoutRefund() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 9, 12, 0), 60);
        assertEquals(BigDecimal.ZERO, ctx.cancellationService.cancel(booking.getId(), null).totalRefund());
    }

    @Test
    void cancellationFreesTheSlotForRebooking() {
        LocalDateTime start = LocalDateTime.of(2030, 1, 9, 12, 0);
        Booking booking = ctx.bookScheduled(maid, start, 60);
        ctx.cancellationService.cancel(booking.getId(), null);
        ctx.bookScheduled(maid, start, 60);
    }

    @Test
    void cancellingTwiceIsAnInvalidTransition() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 9, 12, 0), 60);
        ctx.cancellationService.cancel(booking.getId(), null);
        assertThrows(InvalidStateException.class, () -> ctx.cancellationService.cancel(booking.getId(), null));
    }

    @Test
    void recurringSingleOccurrenceCancelLeavesTheRestActive() {
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.SUNDAY), LocalDate.of(2030, 1, 7), LocalTime.of(9, 0), 3);
        Booking booking = ctx.bookingService.book(new BookingCommand("c", maid.getId(), ServiceType.CLEANING,
                BookingType.RECURRING, 60, null, rule));
        ctx.paymentService.pay(booking.getId(), PAY, null);

        String second = booking.getOccurrences().get(1).getId();
        CancellationResult result = ctx.cancellationService.cancel(booking.getId(), second);

        assertEquals(1, result.cancelledOccurrenceIds().size());
        assertEquals(OccurrenceStatus.CANCELLED, booking.getOccurrences().get(1).getStatus());
        assertEquals(OccurrenceStatus.CONFIRMED, booking.getOccurrences().get(0).getStatus());
        assertEquals(BookingStatus.CONFIRMED, booking.status());
    }

    @Test
    void recurringWholeSeriesCancelRefundsEveryPaidOccurrence() {
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.SUNDAY), LocalDate.of(2030, 1, 7), LocalTime.of(9, 0), 3);
        Booking booking = ctx.bookingService.book(new BookingCommand("c", maid.getId(), ServiceType.CLEANING,
                BookingType.RECURRING, 60, null, rule));
        ctx.paymentService.pay(booking.getId(), PAY, null);

        CancellationResult result = ctx.cancellationService.cancel(booking.getId(), null);

        assertEquals(3, result.cancelledOccurrenceIds().size());
        assertEquals(new BigDecimal("600.00"), result.totalRefund());
        assertEquals(BookingStatus.CANCELLED, booking.status());
        assertTrue(ctx.availabilityService.isAvailable(maid, booking.getOccurrences().get(0).getSlot()));
    }
}
