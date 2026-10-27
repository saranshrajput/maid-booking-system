package com.maidbooking.payment;

public record ChargeResult(boolean success, String reference, String failureReason) {

    public static ChargeResult ok(String reference) {
        return new ChargeResult(true, reference, null);
    }

    public static ChargeResult failed(String reason) {
        return new ChargeResult(false, null, reason);
    }
}
