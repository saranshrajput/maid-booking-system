package com.maidbooking.service;

import com.maidbooking.domain.PaymentMethodType;

// occurrenceId == null means "pay every unpaid occurrence of the booking".
public record PayCommand(PaymentMethodType method, String instrument, String occurrenceId) {
}
