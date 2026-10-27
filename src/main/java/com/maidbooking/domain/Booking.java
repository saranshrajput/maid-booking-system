package com.maidbooking.domain;

import java.util.List;

public class Booking {
    private final String id;
    private final String customerId;
    private final String maidId;
    private final ServiceType serviceType;
    private final BookingType bookingType;
    private final List<BookingOccurrence> occurrences;

    public Booking(String id, String customerId, String maidId, ServiceType serviceType,
                   BookingType bookingType, List<BookingOccurrence> occurrences) {
        this.id = id;
        this.customerId = customerId;
        this.maidId = maidId;
        this.serviceType = serviceType;
        this.bookingType = bookingType;
        this.occurrences = List.copyOf(occurrences);
    }

    // Derived from occurrences so it can never drift out of sync.
    public BookingStatus status() {
        if (occurrences.stream().noneMatch(BookingOccurrence::isActive)) return BookingStatus.CANCELLED;
        boolean unpaid = occurrences.stream().anyMatch(o -> o.getStatus() == OccurrenceStatus.PENDING_PAYMENT);
        return unpaid ? BookingStatus.AWAITING_PAYMENT : BookingStatus.CONFIRMED;
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public String getMaidId() { return maidId; }
    public ServiceType getServiceType() { return serviceType; }
    public BookingType getBookingType() { return bookingType; }
    public List<BookingOccurrence> getOccurrences() { return occurrences; }
}
