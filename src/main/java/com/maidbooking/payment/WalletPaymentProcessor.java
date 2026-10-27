package com.maidbooking.payment;

import com.maidbooking.domain.PaymentMethodType;
import org.springframework.stereotype.Component;

@Component
public class WalletPaymentProcessor extends MockPaymentProcessor {

    @Override
    public PaymentMethodType method() {
        return PaymentMethodType.WALLET;
    }

    @Override
    protected boolean isWellFormed(String instrument) {
        return !instrument.isBlank();
    }
}
