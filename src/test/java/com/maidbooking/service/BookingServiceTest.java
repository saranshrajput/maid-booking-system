package com.maidbooking.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.maidbooking.booking.BookingCommand;
import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingStatus;
import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.exception.SlotUnavailableException;
import com.maidbooking.support.TestContext;
import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class BookingServiceTest {
    private static final LocalDateTime TOMORROW_10 = LocalDateTime.of(2030, 1, 8, 10, 0);

    private TestContext ctx;
    private Maid maid;

    @BeforeEach
    void setUp() {
        ctx = new TestContext();
        maid = ctx.defaultMaid();
    }

    @Test
    void scheduledBookingIsPricedByDurationAndAwaitsPayment() {
        Booking booking = ctx.bookScheduled(maid, TOMORROW_10, 90);
        assertEquals(BookingStatus.AWAITING_PAYMENT, booking.status());
        assertEquals(new BigDecimal("300.00"), booking.getOccurrences().get(0).getPrice());
    }

    @Test
    void instantBookingStartsNow() {
        Booking booking = ctx.bookingService.book(new BookingCommand("c", maid.getId(), ServiceType.CLEANING,
                BookingType.INSTANT, 60, null, null));
        assertEquals(TestContext.NOW, booking.getOccurrences().get(0).getSlot().start());
    }

    @Test
    void overlappingSlotIsRejectedButBackToBackIsAllowed() {
        ctx.bookScheduled(maid, TOMORROW_10, 60);
        assertThrows(SlotUnavailableException.class, () -> ctx.bookScheduled(maid, TOMORROW_10.plusMinutes(30), 60));
        ctx.bookScheduled(maid, TOMORROW_10.plusHours(1), 60);
    }

    @Test
    void slotOutsideWorkingHoursIsRejected() {
        assertThrows(SlotUnavailableException.class, () -> ctx.bookScheduled(maid, TOMORROW_10.withHour(6), 60));
        assertThrows(SlotUnavailableException.class, () -> ctx.bookScheduled(maid, TOMORROW_10.withHour(19), 120));
    }

    @Test
    void recurringBookingCreatesAllOccurrencesAndBlocksEach() {
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.SUNDAY), LocalDate.of(2030, 1, 7), LocalTime.of(9, 0), 4);
        Booking booking = ctx.bookingService.book(new BookingCommand("c", maid.getId(), ServiceType.CLEANING,
                BookingType.RECURRING, 60, null, rule));
        assertEquals(4, booking.getOccurrences().size());
        assertThrows(SlotUnavailableException.class,
                () -> ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 20, 9, 30), 60));
    }

    @Test
    void recurringBookingIsAllOrNothingWhenOneOccurrenceConflicts() {
        ctx.bookScheduled(maid, LocalDateTime.of(2030, 1, 20, 9, 0), 60);
        RecurrenceRule rule = new RecurrenceRule(Set.of(DayOfWeek.SUNDAY), LocalDate.of(2030, 1, 7), LocalTime.of(9, 0), 4);
        assertThrows(SlotUnavailableException.class, () -> ctx.bookingService.book(new BookingCommand("c",
                maid.getId(), ServiceType.CLEANING, BookingType.RECURRING, 60, null, rule)));
        assertEquals(1, ctx.bookingRepository.findByMaidId(maid.getId()).size());
    }

    @Test
    void rejectsServiceTheMaidDoesNotOffer() {
        assertThrows(InvalidRequestException.class, () -> ctx.bookingService.book(new BookingCommand("c",
                maid.getId(), ServiceType.COOKING, BookingType.SCHEDULED, 60, TOMORROW_10, null)));
    }

    @Test
    void rejectsInvalidDuration() {
        assertThrows(InvalidRequestException.class, () -> ctx.bookScheduled(maid, TOMORROW_10, 0));
        assertThrows(InvalidRequestException.class, () -> ctx.bookScheduled(maid, TOMORROW_10, 13 * 60));
    }

    @Test
    void concurrentRequestsForSameSlotYieldExactlyOneBooking() throws Exception {
        int threads = 16;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            Callable<Boolean> task = () -> {
                start.await();
                try {
                    ctx.bookScheduled(maid, TOMORROW_10, 60);
                    return true;
                } catch (SlotUnavailableException e) {
                    return false;
                }
            };
            results.add(pool.submit(task));
        }
        start.countDown();
        long successes = 0;
        for (Future<Boolean> f : results) if (f.get()) successes++;
        pool.shutdown();

        assertEquals(1, successes);
        assertTrue(ctx.bookingRepository.findByMaidId(maid.getId()).size() == 1);
    }
}
