package com.maidbooking.payment;

import com.maidbooking.domain.PaymentMethodType;
import java.math.BigDecimal;

// Our own gateway abstraction; a real PSP integration would implement this per method.
public interface PaymentProcessor {
    PaymentMethodType method();

    ChargeResult charge(BigDecimal amount, String instrument);

    void refund(String gatewayReference, BigDecimal amount);
}
