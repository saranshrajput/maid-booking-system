package com.maidbooking.service;

import com.maidbooking.cancellation.CancellationPolicy;
import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingOccurrence;
import com.maidbooking.domain.Payment;
import com.maidbooking.exception.InvalidStateException;
import com.maidbooking.exception.NotFoundException;
import com.maidbooking.payment.PaymentProcessorRegistry;
import com.maidbooking.repository.BookingRepository;
import com.maidbooking.repository.PaymentRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CancellationService {
    private final BookingRepository bookingRepository;
    private final PaymentRepository paymentRepository;
    private final PaymentProcessorRegistry processors;
    private final CancellationPolicy policy;
    private final MaidLockManager lockManager;
    private final Clock clock;

    public CancellationService(BookingRepository bookingRepository, PaymentRepository paymentRepository,
                               PaymentProcessorRegistry processors, CancellationPolicy policy,
                               MaidLockManager lockManager, Clock clock) {
        this.bookingRepository = bookingRepository;
        this.paymentRepository = paymentRepository;
        this.processors = processors;
        this.policy = policy;
        this.lockManager = lockManager;
        this.clock = clock;
    }

    // occurrenceId == null cancels every cancellable occurrence of the booking (the whole series).
    public CancellationResult cancel(String bookingId, String occurrenceId) {
        Booking booking = bookingRepository.findById(bookingId)
                .orElseThrow(() -> new NotFoundException("Booking not found: " + bookingId));

        return lockManager.withLock(booking.getMaidId(), () -> {
            LocalDateTime now = LocalDateTime.now(clock);
            List<BookingOccurrence> targets = targets(booking, occurrenceId, now);
            BigDecimal totalRefund = BigDecimal.ZERO;
            for (BookingOccurrence occurrence : targets) {
                totalRefund = totalRefund.add(refund(occurrence, now));
                occurrence.cancel();
            }
            bookingRepository.save(booking);
            return new CancellationResult(booking, targets.stream().map(BookingOccurrence::getId).toList(), totalRefund);
        });
    }

    private List<BookingOccurrence> targets(Booking booking, String occurrenceId, LocalDateTime now) {
        if (occurrenceId == null) {
            List<BookingOccurrence> all = booking.getOccurrences().stream().filter(o -> isCancellable(o, now)).toList();
            if (all.isEmpty()) throw new InvalidStateException("Booking " + booking.getId() + " has nothing left to cancel");
            return all;
        }
        BookingOccurrence target = booking.getOccurrences().stream()
                .filter(o -> o.getId().equals(occurrenceId)).findFirst()
                .orElseThrow(() -> new NotFoundException("Occurrence not found: " + occurrenceId));
        if (!isCancellable(target, now)) {
            throw new InvalidStateException("Occurrence " + occurrenceId + " cannot be cancelled (" + target.getStatus() + ")");
        }
        return List.of(target);
    }

    // Cancellable while active and not yet finished.
    private boolean isCancellable(BookingOccurrence occurrence, LocalDateTime now) {
        return occurrence.isActive() && occurrence.getSlot().end().isAfter(now);
    }

    private BigDecimal refund(BookingOccurrence occurrence, LocalDateTime now) {
        return paymentRepository.findCapturedByOccurrenceId(occurrence.getId()).map(payment -> {
            BigDecimal amount = payment.getAmount().multiply(policy.refundFraction(occurrence, now))
                    .setScale(2, RoundingMode.HALF_UP);
            if (amount.signum() > 0) {
                processors.get(payment.getMethod()).refund(payment.getGatewayReference(), amount);
                recordRefund(payment, amount);
            }
            return amount;
        }).orElse(BigDecimal.ZERO);
    }

    private void recordRefund(Payment payment, BigDecimal amount) {
        payment.recordRefund(amount);
        paymentRepository.save(payment);
    }
}
