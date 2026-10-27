package com.maidbooking.payment;

import java.math.BigDecimal;
import java.util.UUID;

// Simulated gateway: succeeds for well-formed instruments, declines anything starting with "fail".
public abstract class MockPaymentProcessor implements PaymentProcessor {

    protected abstract boolean isWellFormed(String instrument);

    @Override
    public ChargeResult charge(BigDecimal amount, String instrument) {
        if (instrument == null || !isWellFormed(instrument)) {
            return ChargeResult.failed("Invalid " + method() + " details");
        }
        if (instrument.startsWith("fail")) {
            return ChargeResult.failed(method() + " payment declined");
        }
        return ChargeResult.ok(method() + "-" + UUID.randomUUID());
    }

    @Override
    public void refund(String gatewayReference, BigDecimal amount) {
        // Mock gateway: refunds always succeed.
    }
}
