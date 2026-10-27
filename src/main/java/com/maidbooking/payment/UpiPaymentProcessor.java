package com.maidbooking.payment;

import com.maidbooking.domain.PaymentMethodType;
import org.springframework.stereotype.Component;

@Component
public class UpiPaymentProcessor extends MockPaymentProcessor {

    @Override
    public PaymentMethodType method() {
        return PaymentMethodType.UPI;
    }

    @Override
    protected boolean isWellFormed(String instrument) {
        return instrument.contains("@") || instrument.startsWith("fail");
    }
}
