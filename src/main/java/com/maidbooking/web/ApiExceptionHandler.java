package com.maidbooking.web;

import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.exception.InvalidStateException;
import com.maidbooking.exception.NotFoundException;
import com.maidbooking.exception.PaymentFailedException;
import com.maidbooking.exception.SlotUnavailableException;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiExceptionHandler {

    public record ErrorResponse(String code, String message) {
    }

    @ExceptionHandler(NotFoundException.class)
    ResponseEntity<ErrorResponse> notFound(NotFoundException e) {
        return error(HttpStatus.NOT_FOUND, "NOT_FOUND", e.getMessage());
    }

    @ExceptionHandler(InvalidRequestException.class)
    ResponseEntity<ErrorResponse> invalid(InvalidRequestException e) {
        return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", e.getMessage());
    }

    @ExceptionHandler(SlotUnavailableException.class)
    ResponseEntity<ErrorResponse> slotUnavailable(SlotUnavailableException e) {
        return error(HttpStatus.CONFLICT, "SLOT_UNAVAILABLE", e.getMessage());
    }

    @ExceptionHandler(InvalidStateException.class)
    ResponseEntity<ErrorResponse> invalidState(InvalidStateException e) {
        return error(HttpStatus.CONFLICT, "INVALID_STATE", e.getMessage());
    }

    @ExceptionHandler(PaymentFailedException.class)
    ResponseEntity<ErrorResponse> paymentFailed(PaymentFailedException e) {
        return error(HttpStatus.PAYMENT_REQUIRED, "PAYMENT_FAILED", e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ErrorResponse> validation(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + " " + f.getDefaultMessage()).collect(Collectors.joining("; "));
        return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", message);
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    ResponseEntity<ErrorResponse> unreadable(Exception e) {
        return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "Malformed request: " + e.getMessage());
    }

    private ResponseEntity<ErrorResponse> error(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(new ErrorResponse(code, message));
    }
}
