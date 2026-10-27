package com.maidbooking.repository;

import com.maidbooking.domain.Booking;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryBookingRepository implements BookingRepository {
    private final Map<String, Booking> store = new ConcurrentHashMap<>();

    @Override
    public Booking save(Booking booking) {
        store.put(booking.getId(), booking);
        return booking;
    }

    @Override
    public Optional<Booking> findById(String id) {
        return Optional.ofNullable(store.get(id));
    }

    @Override
    public List<Booking> findByMaidId(String maidId) {
        return store.values().stream().filter(b -> b.getMaidId().equals(maidId)).toList();
    }
}
