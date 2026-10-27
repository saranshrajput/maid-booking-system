package com.maidbooking.service;

import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingOccurrence;
import com.maidbooking.domain.OccurrenceStatus;
import com.maidbooking.domain.Payment;
import com.maidbooking.domain.PaymentStatus;
import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.exception.InvalidStateException;
import com.maidbooking.exception.NotFoundException;
import com.maidbooking.exception.PaymentFailedException;
import com.maidbooking.payment.ChargeResult;
import com.maidbooking.payment.PaymentProcessor;
import com.maidbooking.payment.PaymentProcessorRegistry;
import com.maidbooking.repository.BookingRepository;
import com.maidbooking.repository.IdempotencyStore;
import com.maidbooking.repository.PaymentRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private final BookingRepository bookingRepository;
    private final PaymentRepository paymentRepository;
    private final IdempotencyStore idempotencyStore;
    private final PaymentProcessorRegistry processors;
    private final MaidLockManager lockManager;

    public PaymentService(BookingRepository bookingRepository, PaymentRepository paymentRepository,
                          IdempotencyStore idempotencyStore, PaymentProcessorRegistry processors,
                          MaidLockManager lockManager) {
        this.bookingRepository = bookingRepository;
        this.paymentRepository = paymentRepository;
        this.idempotencyStore = idempotencyStore;
        this.processors = processors;
        this.lockManager = lockManager;
    }

    public List<Payment> pay(String bookingId, PayCommand command, String idempotencyKey) {
        if (command.method() == null) throw new InvalidRequestException("Payment method is required");
        Booking booking = bookingRepository.findById(bookingId)
                .orElseThrow(() -> new NotFoundException("Booking not found: " + bookingId));
        PaymentProcessor processor = processors.get(command.method());
        String key = idempotencyKey == null || idempotencyKey.isBlank() ? null : bookingId + ":" + idempotencyKey;

        // Same lock as booking/cancel, so the key lookup and the charge are atomic per maid.
        return lockManager.withLock(booking.getMaidId(), () -> {
            if (key != null) {
                var previous = idempotencyStore.find(key);
                if (previous.isPresent()) return previous.get();
            }
            List<Payment> payments = new ArrayList<>();
            for (BookingOccurrence occurrence : payableOccurrences(booking, command.occurrenceId())) {
                payments.add(charge(booking, occurrence, command, processor));
            }
            if (key != null) idempotencyStore.save(key, payments);
            return payments;
        });
    }

    private Payment charge(Booking booking, BookingOccurrence occurrence, PayCommand command, PaymentProcessor processor) {
        ChargeResult result = processor.charge(occurrence.getPrice(), command.instrument());
        PaymentStatus status = result.success() ? PaymentStatus.SUCCESS : PaymentStatus.FAILED;
        Payment payment = paymentRepository.save(new Payment(UUID.randomUUID().toString(), booking.getId(),
                occurrence.getId(), occurrence.getPrice(), command.method(), status,
                result.reference(), result.failureReason()));
        if (!result.success()) {
            throw new PaymentFailedException(result.failureReason());
        }
        occurrence.confirm();
        bookingRepository.save(booking);
        return payment;
    }

    private List<BookingOccurrence> payableOccurrences(Booking booking, String occurrenceId) {
        List<BookingOccurrence> unpaid = booking.getOccurrences().stream()
                .filter(o -> o.getStatus() == OccurrenceStatus.PENDING_PAYMENT).toList();
        if (occurrenceId != null) {
            BookingOccurrence target = booking.getOccurrences().stream()
                    .filter(o -> o.getId().equals(occurrenceId)).findFirst()
                    .orElseThrow(() -> new NotFoundException("Occurrence not found: " + occurrenceId));
            if (target.getStatus() != OccurrenceStatus.PENDING_PAYMENT) {
                throw new InvalidStateException("Occurrence " + occurrenceId + " is " + target.getStatus() + ", not payable");
            }
            return List.of(target);
        }
        if (unpaid.isEmpty()) throw new InvalidStateException("Nothing to pay for booking " + booking.getId());
        return unpaid;
    }
}
