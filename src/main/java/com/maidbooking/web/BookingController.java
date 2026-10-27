package com.maidbooking.web;

import com.maidbooking.booking.BookingCommand;
import com.maidbooking.service.BookingService;
import com.maidbooking.service.CancellationService;
import com.maidbooking.service.PayCommand;
import com.maidbooking.service.PaymentService;
import com.maidbooking.web.BookingDtos.BookingResponse;
import com.maidbooking.web.BookingDtos.CancellationResponse;
import com.maidbooking.web.BookingDtos.CreateBookingRequest;
import com.maidbooking.web.BookingDtos.PayRequest;
import com.maidbooking.web.BookingDtos.PaymentResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {
    private final BookingService bookingService;
    private final PaymentService paymentService;
    private final CancellationService cancellationService;

    public BookingController(BookingService bookingService, PaymentService paymentService,
                             CancellationService cancellationService) {
        this.bookingService = bookingService;
        this.paymentService = paymentService;
        this.cancellationService = cancellationService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public BookingResponse book(@Valid @RequestBody CreateBookingRequest r) {
        BookingCommand command = new BookingCommand(r.customerId(), r.maidId(), r.serviceType(), r.bookingType(),
                r.durationMinutes(), r.startDateTime(), r.recurrence() == null ? null : r.recurrence().toDomain());
        return BookingResponse.from(bookingService.book(command));
    }

    @GetMapping("/{id}")
    public BookingResponse get(@PathVariable String id) {
        return BookingResponse.from(bookingService.get(id));
    }

    @PostMapping("/{id}/payments")
    @ResponseStatus(HttpStatus.CREATED)
    public List<PaymentResponse> pay(@PathVariable String id, @Valid @RequestBody PayRequest r,
                                     @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        return paymentService.pay(id, new PayCommand(r.method(), r.instrument(), r.occurrenceId()), idempotencyKey)
                .stream().map(PaymentResponse::from).toList();
    }

    @PostMapping("/{id}/cancel")
    public CancellationResponse cancel(@PathVariable String id, @RequestParam(required = false) String occurrenceId) {
        return CancellationResponse.from(cancellationService.cancel(id, occurrenceId));
    }
}
