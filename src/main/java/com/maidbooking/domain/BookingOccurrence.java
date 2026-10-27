package com.maidbooking.domain;

import com.maidbooking.exception.InvalidStateException;
import java.math.BigDecimal;

// One bookable slot; Instant/Scheduled bookings have one, Recurring bookings have many.
public class BookingOccurrence {
    private final String id;
    private final TimeSlot slot;
    private final BigDecimal price;
    private volatile OccurrenceStatus status = OccurrenceStatus.PENDING_PAYMENT;

    public BookingOccurrence(String id, TimeSlot slot, BigDecimal price) {
        this.id = id;
        this.slot = slot;
        this.price = price;
    }

    public void confirm() {
        if (status != OccurrenceStatus.PENDING_PAYMENT) {
            throw new InvalidStateException("Occurrence " + id + " cannot be confirmed from " + status);
        }
        status = OccurrenceStatus.CONFIRMED;
    }

    public void cancel() {
        if (status == OccurrenceStatus.CANCELLED) {
            throw new InvalidStateException("Occurrence " + id + " is already cancelled");
        }
        status = OccurrenceStatus.CANCELLED;
    }

    // Active occurrences hold the maid's slot.
    public boolean isActive() {
        return status != OccurrenceStatus.CANCELLED;
    }

    public String getId() { return id; }
    public TimeSlot getSlot() { return slot; }
    public BigDecimal getPrice() { return price; }
    public OccurrenceStatus getStatus() { return status; }
}
