package com.maidbooking.payment;

import com.maidbooking.domain.PaymentMethodType;
import org.springframework.stereotype.Component;

@Component
public class CardPaymentProcessor extends MockPaymentProcessor {

    @Override
    public PaymentMethodType method() {
        return PaymentMethodType.CARD;
    }

    @Override
    protected boolean isWellFormed(String instrument) {
        return instrument.matches("\\d{12,19}") || instrument.startsWith("fail");
    }
}
