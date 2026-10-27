package com.maidbooking.search;

import com.maidbooking.domain.Gender;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.domain.TimeSlot;
import java.math.BigDecimal;
import java.util.Set;

// Every field is optional; a null field means "don't filter on this".
public record MaidSearchCriteria(String locality, ServiceType serviceType, TimeSlot requestedSlot,
                                 Double minRating, BigDecimal maxHourlyRate, Gender gender, Set<String> skills) {
}
