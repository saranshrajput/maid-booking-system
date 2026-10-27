package com.maidbooking.booking;

import com.maidbooking.domain.BookingType;
import com.maidbooking.exception.InvalidRequestException;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class BookingStrategyRegistry {
    private final Map<BookingType, BookingStrategy> strategies = new EnumMap<>(BookingType.class);

    public BookingStrategyRegistry(List<BookingStrategy> all) {
        all.forEach(s -> strategies.put(s.type(), s));
    }

    public BookingStrategy get(BookingType type) {
        BookingStrategy strategy = strategies.get(type);
        if (strategy == null) throw new InvalidRequestException("Unsupported booking type: " + type);
        return strategy;
    }
}
