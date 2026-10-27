package com.maidbooking.service;

import com.maidbooking.booking.BookingCommand;
import com.maidbooking.booking.BookingStrategyRegistry;
import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingOccurrence;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.exception.NotFoundException;
import com.maidbooking.exception.SlotUnavailableException;
import com.maidbooking.pricing.PricingStrategy;
import com.maidbooking.repository.BookingRepository;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class BookingService {
    private static final int MAX_DURATION_MINUTES = 12 * 60;

    private final MaidService maidService;
    private final BookingRepository bookingRepository;
    private final BookingStrategyRegistry strategies;
    private final AvailabilityService availabilityService;
    private final PricingStrategy pricingStrategy;
    private final MaidLockManager lockManager;
    private final Clock clock;

    public BookingService(MaidService maidService, BookingRepository bookingRepository,
                          BookingStrategyRegistry strategies, AvailabilityService availabilityService,
                          PricingStrategy pricingStrategy, MaidLockManager lockManager, Clock clock) {
        this.maidService = maidService;
        this.bookingRepository = bookingRepository;
        this.strategies = strategies;
        this.availabilityService = availabilityService;
        this.pricingStrategy = pricingStrategy;
        this.lockManager = lockManager;
        this.clock = clock;
    }

    public Booking book(BookingCommand command) {
        validate(command);
        Maid maid = maidService.get(command.maidId());
        if (!maid.offers(command.serviceType())) {
            throw new InvalidRequestException(maid.getName() + " does not offer " + command.serviceType());
        }
        List<TimeSlot> slots = strategies.get(command.bookingType()).resolveSlots(command, LocalDateTime.now(clock));

        // Check-then-save is atomic per maid, so concurrent requests cannot double-book.
        return lockManager.withLock(maid.getId(), () -> {
            slots.stream().filter(s -> !availabilityService.isAvailable(maid, s)).findFirst().ifPresent(s -> {
                throw new SlotUnavailableException(maid.getName() + " is not available for " + s.start() + " - " + s.end());
            });
            List<BookingOccurrence> occurrences = slots.stream()
                    .map(s -> new BookingOccurrence(UUID.randomUUID().toString(), s,
                            pricingStrategy.price(maid, command.serviceType(), s)))
                    .toList();
            return bookingRepository.save(new Booking(UUID.randomUUID().toString(), command.customerId(),
                    maid.getId(), command.serviceType(), command.bookingType(), occurrences));
        });
    }

    public Booking get(String bookingId) {
        return bookingRepository.findById(bookingId)
                .orElseThrow(() -> new NotFoundException("Booking not found: " + bookingId));
    }

    private void validate(BookingCommand c) {
        if (c.customerId() == null || c.customerId().isBlank()) throw new InvalidRequestException("customerId is required");
        if (c.maidId() == null || c.serviceType() == null || c.bookingType() == null) {
            throw new InvalidRequestException("maidId, serviceType and bookingType are required");
        }
        if (c.durationMinutes() <= 0 || c.durationMinutes() > MAX_DURATION_MINUTES) {
            throw new InvalidRequestException("Duration must be between 1 and " + MAX_DURATION_MINUTES + " minutes");
        }
    }
}
