package com.maidbooking.service;

import com.maidbooking.domain.Booking;
import java.math.BigDecimal;
import java.util.List;

public record CancellationResult(Booking booking, List<String> cancelledOccurrenceIds, BigDecimal totalRefund) {
}
