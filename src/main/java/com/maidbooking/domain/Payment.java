package com.maidbooking.domain;

import java.math.BigDecimal;

public class Payment {
    private final String id;
    private final String bookingId;
    private final String occurrenceId;
    private final BigDecimal amount;
    private final PaymentMethodType method;
    private final String gatewayReference;
    private final String failureReason;
    private PaymentStatus status;
    private BigDecimal refundedAmount = BigDecimal.ZERO;

    public Payment(String id, String bookingId, String occurrenceId, BigDecimal amount, PaymentMethodType method,
                   PaymentStatus status, String gatewayReference, String failureReason) {
        this.id = id;
        this.bookingId = bookingId;
        this.occurrenceId = occurrenceId;
        this.amount = amount;
        this.method = method;
        this.status = status;
        this.gatewayReference = gatewayReference;
        this.failureReason = failureReason;
    }

    public synchronized void recordRefund(BigDecimal refund) {
        refundedAmount = refundedAmount.add(refund);
        status = refundedAmount.compareTo(amount) >= 0 ? PaymentStatus.REFUNDED : PaymentStatus.PARTIALLY_REFUNDED;
    }

    public boolean isCaptured() {
        return status != PaymentStatus.FAILED;
    }

    public String getId() { return id; }
    public String getBookingId() { return bookingId; }
    public String getOccurrenceId() { return occurrenceId; }
    public BigDecimal getAmount() { return amount; }
    public PaymentMethodType getMethod() { return method; }
    public String getGatewayReference() { return gatewayReference; }
    public String getFailureReason() { return failureReason; }
    public synchronized PaymentStatus getStatus() { return status; }
    public synchronized BigDecimal getRefundedAmount() { return refundedAmount; }
}
