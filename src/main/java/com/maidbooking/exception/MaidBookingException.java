package com.maidbooking.exception;

public abstract class MaidBookingException extends RuntimeException {
    protected MaidBookingException(String message) {
        super(message);
    }
}
