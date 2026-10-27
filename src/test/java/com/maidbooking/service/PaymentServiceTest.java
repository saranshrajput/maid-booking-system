package com.maidbooking.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingStatus;
import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.OccurrenceStatus;
import com.maidbooking.domain.Payment;
import com.maidbooking.domain.PaymentMethodType;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.booking.BookingCommand;
import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.exception.InvalidStateException;
import com.maidbooking.exception.PaymentFailedException;
import com.maidbooking.support.TestContext;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PaymentServiceTest {
    private static final String CARD = "4111111111111111";

    private TestContext ctx;
    private Maid maid;

    @BeforeEach
    void setUp() {
        ctx = new TestContext();
        maid = ctx.defaultMaid();
    }

    private Booking recurring(int occurrences) {
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.SUNDAY), LocalDate.of(2030, 1, 7),
                LocalTime.of(9, 0), occurrences);
        return ctx.bookingService.book(new BookingCommand("c", maid.getId(), ServiceType.CLEANING,
                BookingType.RECURRING, 60, null, rule));
    }

    @Test
    void successfulPaymentConfirmsBooking() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 8, 10, 0), 60);
        List<Payment> payments = ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.CARD, CARD, null), null);
        assertEquals(1, payments.size());
        assertEquals(BookingStatus.CONFIRMED, booking.status());
    }

    @Test
    void failedPaymentLeavesBookingAwaitingPayment() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 8, 10, 0), 60);
        assertThrows(PaymentFailedException.class,
                () -> ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.UPI, "fail@upi", null), null));
        assertEquals(BookingStatus.AWAITING_PAYMENT, booking.status());
    }

    @Test
    void malformedInstrumentIsDeclined() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 8, 10, 0), 60);
        assertThrows(PaymentFailedException.class,
                () -> ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.UPI, "no-handle", null), null));
    }

    @Test
    void recurringBookingCanBePaidPerOccurrence() {
        Booking booking = recurring(3);
        String first = booking.getOccurrences().get(0).getId();
        ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.WALLET, "wallet-1", first), null);

        assertEquals(OccurrenceStatus.CONFIRMED, booking.getOccurrences().get(0).getStatus());
        assertEquals(OccurrenceStatus.PENDING_PAYMENT, booking.getOccurrences().get(1).getStatus());
        assertEquals(BookingStatus.AWAITING_PAYMENT, booking.status());

        List<Payment> rest = ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.WALLET, "wallet-1", null), null);
        assertEquals(2, rest.size());
        assertEquals(BookingStatus.CONFIRMED, booking.status());
    }

    @Test
    void payingAnAlreadyPaidOccurrenceIsAnInvalidTransition() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 8, 10, 0), 60);
        ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.CARD, CARD, null), null);
        assertThrows(InvalidStateException.class,
                () -> ctx.paymentService.pay(booking.getId(), new PayCommand(PaymentMethodType.CARD, CARD, null), null));
    }

    @Test
    void sameIdempotencyKeyReturnsOriginalResultWithoutChargingTwice() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 8, 10, 0), 60);
        PayCommand command = new PayCommand(PaymentMethodType.CARD, CARD, null);
        List<Payment> first = ctx.paymentService.pay(booking.getId(), command, "key-1");
        List<Payment> retry = ctx.paymentService.pay(booking.getId(), command, "key-1");
        assertEquals(first.get(0).getId(), retry.get(0).getId());
    }

    @Test
    void missingMethodIsRejected() {
        Booking booking = ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 8, 10, 0), 60);
        assertThrows(InvalidRequestException.class,
                () -> ctx.paymentService.pay(booking.getId(), new PayCommand(null, CARD, null), null));
    }
}
