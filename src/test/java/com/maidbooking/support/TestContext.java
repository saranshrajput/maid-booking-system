package com.maidbooking.support;

import com.maidbooking.booking.BookingCommand;
import com.maidbooking.booking.BookingStrategyRegistry;
import com.maidbooking.booking.InstantBookingStrategy;
import com.maidbooking.booking.RecurringBookingStrategy;
import com.maidbooking.booking.ScheduledBookingStrategy;
import com.maidbooking.cancellation.TimeBasedCancellationPolicy;
import com.maidbooking.domain.AvailabilityWindow;
import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.Gender;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.payment.CardPaymentProcessor;
import com.maidbooking.payment.PaymentProcessorRegistry;
import com.maidbooking.payment.UpiPaymentProcessor;
import com.maidbooking.payment.WalletPaymentProcessor;
import com.maidbooking.pricing.HourlyPricingStrategy;
import com.maidbooking.repository.InMemoryBookingRepository;
import com.maidbooking.repository.InMemoryIdempotencyStore;
import com.maidbooking.repository.InMemoryMaidRepository;
import com.maidbooking.repository.InMemoryPaymentRepository;
import com.maidbooking.service.AvailabilityService;
import com.maidbooking.service.BookingService;
import com.maidbooking.service.CancellationService;
import com.maidbooking.service.MaidLockManager;
import com.maidbooking.service.MaidService;
import com.maidbooking.service.OnboardMaidCommand;
import com.maidbooking.service.PaymentService;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;

// Wires the real services over in-memory repositories with a fixed clock: Monday 2030-01-07 10:00.
public class TestContext {
    public static final LocalDateTime NOW = LocalDateTime.of(2030, 1, 7, 10, 0);

    public final Clock clock = Clock.fixed(Instant.parse("2030-01-07T10:00:00Z"), ZoneOffset.UTC);
    public final InMemoryMaidRepository maidRepository = new InMemoryMaidRepository();
    public final InMemoryBookingRepository bookingRepository = new InMemoryBookingRepository();
    public final InMemoryPaymentRepository paymentRepository = new InMemoryPaymentRepository();
    public final MaidService maidService = new MaidService(maidRepository);
    public final AvailabilityService availabilityService = new AvailabilityService(bookingRepository);
    public final MaidLockManager lockManager = new MaidLockManager();
    public final PaymentProcessorRegistry processors = new PaymentProcessorRegistry(
            List.of(new CardPaymentProcessor(), new UpiPaymentProcessor(), new WalletPaymentProcessor()));
    public final BookingService bookingService = new BookingService(maidService, bookingRepository,
            new BookingStrategyRegistry(List.of(new InstantBookingStrategy(), new ScheduledBookingStrategy(),
                    new RecurringBookingStrategy())),
            availabilityService, new HourlyPricingStrategy(), lockManager, clock);
    public final PaymentService paymentService = new PaymentService(bookingRepository, paymentRepository,
            new InMemoryIdempotencyStore(), processors, lockManager);
    public final CancellationService cancellationService = new CancellationService(bookingRepository,
            paymentRepository, processors, new TimeBasedCancellationPolicy(), lockManager, clock);

    // Works 08:00-20:00 every day, CLEANING at 200/h.
    public Maid maid(String name, String locality, Gender gender, double rating, BigDecimal cleaningRate, String... skills) {
        List<AvailabilityWindow> windows = Arrays.stream(DayOfWeek.values())
                .map(d -> new AvailabilityWindow(d, LocalTime.of(8, 0), LocalTime.of(20, 0))).toList();
        return maidService.onboard(new OnboardMaidCommand(name, locality, gender, rating,
                Map.of(ServiceType.CLEANING, cleaningRate), Set.of(skills), windows));
    }

    public Maid defaultMaid() {
        return maid("Asha", "Koramangala", Gender.FEMALE, 4.5, new BigDecimal("200"), "deep-cleaning");
    }

    public Booking bookScheduled(Maid maid, LocalDateTime start, int minutes) {
        return bookingService.book(new BookingCommand("cust-1", maid.getId(), ServiceType.CLEANING,
                BookingType.SCHEDULED, minutes, start, null));
    }
}
