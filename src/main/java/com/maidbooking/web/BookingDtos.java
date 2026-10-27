package com.maidbooking.web;

import com.maidbooking.domain.Booking;
import com.maidbooking.domain.BookingOccurrence;
import com.maidbooking.domain.BookingStatus;
import com.maidbooking.domain.BookingType;
import com.maidbooking.domain.OccurrenceStatus;
import com.maidbooking.domain.Payment;
import com.maidbooking.domain.PaymentMethodType;
import com.maidbooking.domain.PaymentStatus;
import com.maidbooking.domain.RecurrenceRule;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.service.CancellationResult;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.List;
import java.util.Set;

public final class BookingDtos {
    private BookingDtos() {
    }

    public record RecurrenceDto(@NotEmpty Set<DayOfWeek> daysOfWeek, @NotNull LocalDate startDate,
                                @NotNull LocalTime startTime, @Positive int occurrences) {
        RecurrenceRule toDomain() {
            return new RecurrenceRule(daysOfWeek, startDate, startTime, occurrences);
        }
    }

    public record CreateBookingRequest(@NotBlank String customerId, @NotBlank String maidId,
                                       @NotNull ServiceType serviceType, @NotNull BookingType bookingType,
                                       @NotNull @Positive Integer durationMinutes, LocalDateTime startDateTime,
                                       @Valid RecurrenceDto recurrence) {
    }

    public record PayRequest(@NotNull PaymentMethodType method, @NotBlank String instrument, String occurrenceId) {
    }

    public record OccurrenceResponse(String id, LocalDateTime start, LocalDateTime end, BigDecimal price,
                                     OccurrenceStatus status) {
        static OccurrenceResponse from(BookingOccurrence o) {
            return new OccurrenceResponse(o.getId(), o.getSlot().start(), o.getSlot().end(), o.getPrice(), o.getStatus());
        }
    }

    public record BookingResponse(String id, String customerId, String maidId, ServiceType serviceType,
                                  BookingType bookingType, BookingStatus status, List<OccurrenceResponse> occurrences) {
        static BookingResponse from(Booking b) {
            return new BookingResponse(b.getId(), b.getCustomerId(), b.getMaidId(), b.getServiceType(),
                    b.getBookingType(), b.status(), b.getOccurrences().stream().map(OccurrenceResponse::from).toList());
        }
    }

    public record PaymentResponse(String id, String occurrenceId, BigDecimal amount, PaymentMethodType method,
                                  PaymentStatus status, BigDecimal refundedAmount) {
        static PaymentResponse from(Payment p) {
            return new PaymentResponse(p.getId(), p.getOccurrenceId(), p.getAmount(), p.getMethod(),
                    p.getStatus(), p.getRefundedAmount());
        }
    }

    public record CancellationResponse(BookingResponse booking, List<String> cancelledOccurrenceIds,
                                       BigDecimal totalRefund) {
        static CancellationResponse from(CancellationResult r) {
            return new CancellationResponse(BookingResponse.from(r.booking()), r.cancelledOccurrenceIds(), r.totalRefund());
        }
    }
}
