package com.maidbooking.service;

import com.maidbooking.domain.Maid;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.repository.BookingRepository;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityService {
    private final BookingRepository bookingRepository;

    public AvailabilityService(BookingRepository bookingRepository) {
        this.bookingRepository = bookingRepository;
    }

    public boolean isAvailable(Maid maid, TimeSlot slot) {
        return maid.worksDuring(slot) && !isBooked(maid.getId(), slot);
    }

    private boolean isBooked(String maidId, TimeSlot slot) {
        return bookingRepository.findByMaidId(maidId).stream()
                .flatMap(b -> b.getOccurrences().stream())
                .anyMatch(o -> o.isActive() && o.getSlot().overlaps(slot));
    }
}
